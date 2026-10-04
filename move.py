#!/usr/bin/env python3
"""
move.py — Move a DockerSeed project.

Usage:
    ./move.py <project> <target> [--force]

Move a DockerSeed project directory. A target ending in `/` is treated as an
existing destination directory; otherwise it is the exact destination path.
When the destination name changes, Docker volumes and images are migrated to
the new project prefix and .env COMPOSE_PROJECT_NAME is updated.

If a failure happens after changes begin, move.py automatically rolls back the
steps that already succeeded. If any undo step also fails, it writes a
MOVE-ROLLBACK-<old>-to-<new>-<timestamp>.txt file with a full summary and
manual recovery commands.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

HELPER_IMAGE: str = "alpine"
VALID_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")

type UndoFn = Callable[[], None]

type RollbackEntry = tuple[str, UndoFn]

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
GREY = "\033[37m"
RESET = "\033[0m"

USAGE = """\
Usage:
    ./move.py <project> <target> [--force]

Move a DockerSeed project directory. A target ending in `/` is an existing
destination directory; otherwise the target is the exact destination path.
When the destination name changes, copy project volumes, retag project images,
and update .env COMPOSE_PROJECT_NAME.

--force skips the running-container preflight and permits existing
<new>_* volumes and <new>-* image tags to be reused. This is unsafe if the
new name already belongs to another project. It never overwrites the target
directory.
"""


class RollbackLedger:
    def __init__(self) -> None:
        self.entries: list[RollbackEntry] = []

    def append(self, description: str, undo_fn: UndoFn) -> None:
        self.entries.append((description, undo_fn))

    def rollback(self) -> list[str]:
        failures: list[str] = []
        for description, undo_fn in reversed(self.entries):
            try:
                undo_fn()
            except Exception as exc:  # pragma: no cover - exercised in tests
                failures.append(f"{description}: {exc}")
        return failures


def fail(message: str) -> None:
    print(f"{RED}✗{RESET} {message}", file=sys.stderr)
    sys.exit(1)


def warn(message: str) -> None:
    print(f"{YELLOW}⚠{RESET} {message}")


def load_env(env_file: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_file.exists():
        return env

    with open(env_file) as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, _, value = stripped.partition("=")
            env[name] = value
    return env


def compose_project_name(work_dir: Path, env: dict[str, str]) -> str:
    if project := env.get("COMPOSE_PROJECT_NAME"):
        return project
    return work_dir.name.lower()


def run_docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def require_docker() -> None:
    if shutil.which("docker") is None:
        fail("`docker` is not installed or not in PATH.")


def docker_detail(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"


def ensure_docker_success(args: list[str], action: str) -> subprocess.CompletedProcess[str]:
    result = run_docker(args)
    if result.returncode != 0:
        raise RuntimeError(f"{action}: {docker_detail(result)}")
    return result


def normalize_project_name(name: str) -> str:
    normalized = name.lower()
    if not VALID_PROJECT_RE.fullmatch(normalized):
        raise ValueError(
            "new project name is invalid after lowercasing: "
            f"{normalized!r} (must match {VALID_PROJECT_RE.pattern})"
        )
    return normalized


class MoveError(Exception):
    pass


def resolve_project_directory(project: str) -> Path:
    project_path = Path(project).expanduser()
    try:
        project_path = project_path.resolve(strict=True)
    except OSError as exc:
        raise MoveError(f"Project directory does not exist: {project}") from exc
    if not project_path.is_dir() or not (project_path / "containers.json").is_file():
        raise MoveError(
            f"Not a DockerSeed project directory: {project_path} "
            "(missing containers.json)."
        )
    return project_path


def resolve_target(project_path: Path, target: str) -> Path:
    if not target:
        raise MoveError("Target path cannot be empty.")

    is_directory_target = target.endswith(os.sep)
    target_path = Path(target).expanduser()
    if is_directory_target:
        try:
            target_path = target_path.resolve(strict=True)
        except OSError as exc:
            raise MoveError(
                f"Target directory does not exist: {target}"
            ) from exc
        if not target_path.is_dir():
            raise MoveError(f"Target is not a directory: {target_path}")
        new_path = target_path / project_path.name
    else:
        try:
            target_parent = target_path.parent.resolve(strict=True)
        except OSError as exc:
            raise MoveError(
                f"Target parent directory does not exist: {target_path.parent}"
            ) from exc
        if not target_parent.is_dir():
            raise MoveError(
                f"Target parent directory does not exist: {target_parent}"
            )
        new_path = target_parent / target_path.name

    if new_path.exists() or new_path.is_symlink():
        raise MoveError(f"Target already exists: {new_path}")
    if new_path == project_path or project_path in new_path.parents:
        raise MoveError(f"Cannot move a project into itself: {new_path}")
    return new_path


def split_line_ending(line: str) -> tuple[str, str]:
    for ending in ("\r\n", "\n", "\r"):
        if line.endswith(ending):
            return line[: -len(ending)], ending
    return line, ""


def rewrite_env_text(original_text: str, new_name: str) -> str:
    lines = original_text.splitlines(keepends=True)
    replaced = False
    rewritten: list[str] = []

    for line in lines:
        body, ending = split_line_ending(line)
        if body.startswith("COMPOSE_PROJECT_NAME="):
            rewritten.append(f"COMPOSE_PROJECT_NAME={new_name}{ending}")
            replaced = True
        else:
            rewritten.append(line)

    if replaced:
        return "".join(rewritten)

    prefix = original_text
    if prefix and not prefix.endswith(("\n", "\r")):
        prefix += "\n"
    return f"{prefix}COMPOSE_PROJECT_NAME={new_name}\n"


def volume_suffix(name: str, project: str) -> str | None:
    prefix = f"{project}_"
    if not name.startswith(prefix):
        return None
    return name[len(prefix) :]


def image_suffix(image: str, project: str) -> str | None:
    repository = image.partition(":")[0]
    prefix = f"{project}-"
    if not repository.startswith(prefix):
        return None
    return repository[len(prefix) :]


def rename_image_reference(image: str, old_project: str, new_project: str) -> str:
    repository, sep, tag = image.partition(":")
    suffix = image_suffix(image, old_project)
    if suffix is None:
        raise ValueError(f"image does not belong to project '{old_project}': {image}")
    new_repository = f"{new_project}-{suffix}"
    if not sep:
        return new_repository
    return f"{new_repository}:{tag}"


def list_project_volumes(project: str) -> list[str]:
    result = run_docker(["volume", "ls", "--format", "{{.Name}}"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list Docker volumes: {docker_detail(result)}")

    prefix = f"{project}_"
    return sorted(name for name in result.stdout.splitlines() if name.startswith(prefix))


def list_project_images(project: str) -> list[str]:
    result = run_docker(["images", "--format", "{{.Repository}}:{{.Tag}}"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list Docker images: {docker_detail(result)}")

    images: list[str] = []
    base_repo = f"{project}-base"
    for line in result.stdout.splitlines():
        image = line.strip()
        if not image:
            continue
        repository = image.partition(":")[0]
        if repository.startswith(f"{project}-") or repository == base_repo:
            images.append(image)
    return sorted(set(images))


def list_running_project_containers(project: str) -> list[str]:
    result = run_docker(["ps", "--format", "{{.Names}}"])
    if result.returncode != 0:
        raise RuntimeError(f"Failed to list running containers: {docker_detail(result)}")

    prefix = f"{project}-"
    return sorted(name for name in result.stdout.splitlines() if name.startswith(prefix))


def parse_args(argv: list[str] | None = None) -> tuple[str, str, bool]:
    if argv is None:
        argv = sys.argv[1:]

    force = False
    positional: list[str] = []
    for arg in argv:
        if arg == "--force":
            force = True
            continue
        if arg in {"-h", "--help"}:
            print(USAGE)
            sys.exit(0)
        positional.append(arg)

    if len(positional) != 2:
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    return positional[0], positional[1], force


def check_docker_daemon() -> None:
    result = run_docker(["info"])
    if result.returncode != 0:
        fail(f"Docker daemon is not reachable: {docker_detail(result)}")


def preflight(
    force: bool, project: str, target: str
) -> tuple[str, str, Path, Path, bool]:
    try:
        old_path = resolve_project_directory(project)
        new_path = resolve_target(old_path, target)
    except MoveError as exc:
        fail(str(exc))

    old_project = compose_project_name(old_path, load_env(old_path / ".env"))
    if target.endswith(os.sep):
        new_project = old_project
    else:
        try:
            new_project = normalize_project_name(new_path.name)
        except ValueError as exc:
            fail(str(exc))
    identity_changed = old_project != new_project

    if identity_changed:
        require_docker()
        check_docker_daemon()
        if force:
            warn("--force: skipping the running-container preflight.")
        else:
            try:
                running = list_running_project_containers(old_project)
            except RuntimeError as exc:
                fail(str(exc))
            if running:
                names = ", ".join(running)
                fail(
                    f"Running containers still use the '{old_project}-' prefix: {names}. "
                    "Stop them first with docker-compose down."
                )

        try:
            existing_volumes = list_project_volumes(new_project)
            existing_images = list_project_images(new_project)
        except RuntimeError as exc:
            fail(str(exc))
        if (existing_volumes or existing_images) and not force:
            details: list[str] = []
            if existing_volumes:
                details.append(f"volumes: {', '.join(existing_volumes)}")
            if existing_images:
                details.append(f"images: {', '.join(existing_images)}")
            fail(
                f"Resources already exist for '{new_project}'. Use --force only if this "
                f"collision is intentional ({'; '.join(details)})."
            )

        if force and (existing_volumes or existing_images):
            details = []
            if existing_volumes:
                details.append(f"volumes: {', '.join(existing_volumes)}")
            if existing_images:
                details.append(f"images: {', '.join(existing_images)}")
            warn(f"--force: reusing existing target resources ({'; '.join(details)}).")

    return old_project, new_project, old_path, new_path, identity_changed


def current_project_dir(old_path: Path, new_path: Path) -> Path:
    if old_path.exists():
        return old_path
    return new_path


def restore_env_file(old_path: Path, new_path: Path, original_text: str | None) -> None:
    target_env = current_project_dir(old_path, new_path) / ".env"
    if original_text is None:
        target_env.unlink(missing_ok=True)
        return
    target_env.write_text(original_text)


def write_rollback_report(
    *,
    old_project: str,
    new_project: str,
    old_path: Path,
    new_path: Path,
    attempted_at: datetime,
    succeeded_steps: list[str],
    failed_step: str,
    rollback_failures: list[str],
    created_volumes: list[str],
    tagged_images: list[str],
    original_env_text: str | None,
) -> Path:
    timestamp = attempted_at.strftime("%Y%m%d%H%M%S")
    base_dir = old_path if old_path.exists() else old_path.parent
    report_path = base_dir / f"MOVE-ROLLBACK-{old_project}-to-{new_project}-{timestamp}.txt"
    directory_still_renamed = new_path.exists() and not old_path.exists()

    lines = [
        "DockerSeed move rollback report",
        f"Attempted move: {old_path} -> {new_path}",
        f"Attempted at: {attempted_at.isoformat()}",
        "",
        "Succeeded steps:",
    ]
    if succeeded_steps:
        lines.extend(f"- {step}" for step in succeeded_steps)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Failure that triggered rollback:",
            f"- {failed_step}",
            "",
            "Automatic undo failures:",
        ]
    )
    if rollback_failures:
        lines.extend(f"- {failure}" for failure in rollback_failures)
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "Manual rollback commands:",
        ]
    )
    if created_volumes:
        for volume in created_volumes:
            lines.append(f"docker volume rm -f {shlex.quote(volume)}")
    else:
        lines.append("# No new volumes were recorded.")

    if tagged_images:
        for image in tagged_images:
            lines.append(f"docker rmi {shlex.quote(image)}")
    else:
        lines.append("# No new image tags were recorded.")

    if directory_still_renamed:
        lines.append(f"mv {shlex.quote(str(new_path))} {shlex.quote(str(old_path))}")
    else:
        lines.append("# Directory name already points back to the old path.")

    lines.extend(
        [
            "",
            "Restore .env to its original content:",
            "----- BEGIN ORIGINAL .env -----",
        ]
    )
    if original_env_text is None:
        lines.append("# .env did not exist before move.py ran")
    else:
        lines.append(original_env_text)
    lines.extend(
        [
            "----- END ORIGINAL .env -----",
            "",
            "If .env existed before, write the block above back to .env exactly.",
            "If it did not exist before, remove the generated .env file.",
        ]
    )

    report_path.write_text("\n".join(lines))
    return report_path


def format_rollback_summary(
    *,
    old_project: str,
    new_project: str,
    failed_step: str,
    rollback_failures: list[str],
    report_path: Path | None,
) -> str:
    lines = [
        f"move.py failed while moving {old_project} -> {new_project}.",
        f"Failure: {failed_step}",
    ]
    if rollback_failures:
        lines.append("Automatic rollback also failed for:")
        lines.extend(f"  - {failure}" for failure in rollback_failures)
    else:
        lines.append("Automatic rollback completed.")
    if report_path is not None:
        lines.append(f"Manual recovery instructions: {report_path}")
    return "\n".join(lines)


def move_project(
    old_project: str,
    new_project: str,
    old_path: Path,
    new_path: Path,
    identity_changed: bool,
) -> None:
    if not identity_changed:
        if new_path.exists() or new_path.is_symlink():
            fail(f"Target already exists: {new_path}")
        try:
            os.rename(old_path, new_path)
        except OSError as exc:
            fail(f"Failed to move project directory: {exc}")
        print(f"{GREEN}✓{RESET} Move complete: {old_path} → {new_path}")
        return

    ledger = RollbackLedger()
    attempted_at = datetime.now()
    succeeded_steps: list[str] = []
    created_volumes: list[str] = []
    tagged_images: list[str] = []
    old_volumes: list[str] = []
    old_images: list[str] = []
    env_file = old_path / ".env"
    original_env_text = env_file.read_text() if env_file.exists() else None

    print(f"{BLUE}⚙{RESET} Moving project {old_project} → {new_project}")

    try:
        old_volumes = list_project_volumes(old_project)
        old_images = list_project_images(old_project)

        if old_volumes:
            print(f"{BLUE}⚙{RESET} Copying Docker volumes:")
        else:
            print(f"{GREY}◦{RESET} No Docker volumes found with prefix {old_project}_")
        for old_volume in old_volumes:
            suffix = volume_suffix(old_volume, old_project)
            if suffix is None:
                continue
            new_volume = f"{new_project}_{suffix}"
            ensure_docker_success(
                ["volume", "create", new_volume],
                f"Failed to create Docker volume {new_volume}",
            )
            ensure_docker_success(
                [
                    "run",
                    "--rm",
                    "-v",
                    f"{old_volume}:/from:ro",
                    "-v",
                    f"{new_volume}:/to",
                    HELPER_IMAGE,
                    "sh",
                    "-c",
                    "cp -a /from/. /to/",
                ],
                f"Failed to copy Docker volume {old_volume} into {new_volume}",
            )
            created_volumes.append(new_volume)
            ledger.append(
                f"Remove copied volume {new_volume}",
                lambda volume=new_volume: ensure_docker_success(
                    ["volume", "rm", "-f", volume],
                    f"Failed to remove Docker volume {volume}",
                ),
            )
            step = f"Copied volume {old_volume} → {new_volume}"
            succeeded_steps.append(step)
            print(f"{GREEN}✓{RESET} {step}")

        if old_images:
            print(f"{BLUE}⚙{RESET} Retagging Docker images:")
        else:
            print(f"{GREY}◦{RESET} No Docker images found with prefix {old_project}-")
        for old_image in old_images:
            new_image = rename_image_reference(old_image, old_project, new_project)
            ensure_docker_success(
                ["tag", old_image, new_image],
                f"Failed to retag Docker image {old_image} as {new_image}",
            )
            tagged_images.append(new_image)
            ledger.append(
                f"Remove retagged image {new_image}",
                lambda image=new_image: ensure_docker_success(
                    ["rmi", image],
                    f"Failed to remove Docker image tag {image}",
                ),
            )
            step = f"Retagged image {old_image} → {new_image}"
            succeeded_steps.append(step)
            print(f"{GREEN}✓{RESET} {step}")

        rewritten_env = rewrite_env_text(original_env_text or "", new_project)
        env_file.write_text(rewritten_env)
        ledger.append(
            "Restore original .env",
            lambda: restore_env_file(old_path, new_path, original_env_text),
        )
        succeeded_steps.append(f"Updated {env_file} COMPOSE_PROJECT_NAME to {new_project}")
        print(f"{GREEN}✓{RESET} Updated {env_file}")

        if new_path.exists() or new_path.is_symlink():
            raise FileExistsError(f"Target already exists: {new_path}")
        os.rename(old_path, new_path)
        ledger.append(
            f"Move directory back to {old_path}",
            lambda: os.rename(new_path, old_path),
        )
        succeeded_steps.append(f"Moved directory {old_path} → {new_path}")
        print(f"{GREEN}✓{RESET} Moved directory to {new_path}")
    except Exception as exc:
        failed_step = str(exc)
        rollback_failures = ledger.rollback()
        report_path: Path | None = None
        if rollback_failures:
            report_path = write_rollback_report(
                old_project=old_project,
                new_project=new_project,
                old_path=old_path,
                new_path=new_path,
                attempted_at=attempted_at,
                succeeded_steps=succeeded_steps,
                failed_step=failed_step,
                rollback_failures=rollback_failures,
                created_volumes=created_volumes,
                tagged_images=tagged_images,
                original_env_text=original_env_text,
            )
        summary = format_rollback_summary(
            old_project=old_project,
            new_project=new_project,
            failed_step=failed_step,
            rollback_failures=rollback_failures,
            report_path=report_path,
        )
        print(f"{RED}✗{RESET} {summary}", file=sys.stderr)
        sys.exit(1)

    if old_volumes:
        print(f"{BLUE}⚙{RESET} Removing old Docker volumes:")
    for old_volume in old_volumes:
        result = run_docker(["volume", "rm", old_volume])
        if result.returncode == 0:
            print(f"{GREEN}✓{RESET} Removed {old_volume}")
        else:
            warn(
                f"Could not remove old volume {old_volume}: {docker_detail(result)}"
            )

    if old_images:
        print(f"{BLUE}⚙{RESET} Removing old Docker image tags:")
    for old_image in old_images:
        result = run_docker(["rmi", old_image])
        if result.returncode == 0:
            print(f"{GREEN}✓{RESET} Removed {old_image}")
        else:
            warn(f"Could not remove old image {old_image}: {docker_detail(result)}")

    print(f"{GREEN}✓{RESET} Move complete: {old_path} → {new_path}")
    print(f"{GREEN}✓{RESET} Volumes copied, images retagged, .env updated, and directory moved to {new_path}")
    print(
        f"{GREY}◦{RESET} If any old resources could not be removed, clean them up with cleanup.py or docker manually."
    )


def main(argv: list[str] | None = None) -> None:
    project, target, force = parse_args(argv)
    old_project, new_project, old_path, new_path, identity_changed = preflight(
        force, project, target
    )
    move_project(old_project, new_project, old_path, new_path, identity_changed)


if __name__ == "__main__":
    main()
