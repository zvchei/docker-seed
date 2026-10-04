#!/usr/bin/env python3
"""
restore.py — Recreate a DockerSeed project from a backup.py archive.

Usage:
    ./restore.py <archive.tar[.gz]> [directory] [--name NEW_NAME] [--force]

Accepts both the plain .tar archives produced by backup.py and gzip-
compressed .tar.gz archives (e.g. from `pv backup.tar | gzip > backup.tar.gz`
or an older backup.py that still gzipped its output).

Consumes the exact archive layout produced by backup.py:

  metadata/backup.json      # manifest: format_version, project_name,
                             # created_at, volumes, included_secrets
  metadata/containers.json  # required
  metadata/.env             # optional
  metadata/assets.json      # optional
  metadata/templates/       # optional local cwd overlay
  metadata/secrets/         # optional
  volumes/<suffix>.tar      # one tar per Docker volume

Behaviour:
  - <directory> defaults to the current working directory. If it does not
    exist, restore.py offers to create it (like till.py).
  - The restored project keeps the archive's original project name unless
    --name is given, which pins a new COMPOSE_PROJECT_NAME in the restored
    .env (this does not rename the target directory itself; use move.py
    afterwards if you also want the directory renamed).
  - Docker volumes are recreated under <project>_<suffix> and their tar
    contents are restored via a disposable alpine helper container.
  - sow.py then harvest.py are run in the target directory to regenerate
    services/ and the root docker-compose.yaml.

Every step is preflight-checked before anything is written, and every
mutation is tracked so a failure rolls back everything already done. If an
automatic rollback step itself fails, restore.py writes a
RESTORE-ROLLBACK-<project>-<timestamp>.txt file with the exact manual
commands needed to finish undoing the restore, and prints the same summary.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR: Path = Path(__file__).resolve().parent
CWD: Path = Path.cwd()
HELPER_IMAGE: str = "alpine"

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
    ./restore.py <archive.tar[.gz]> [directory] [--name NEW_NAME] [--force]

Restore a backup.py archive into <directory> (default: current directory).
Both plain .tar and gzip-compressed .tar.gz archives are accepted.

--name NEW_NAME  pin the restored project under a different name instead of
                 the archive's original project name.
--force          allow restoring into a non-empty directory that already has
                 containers.json/.env, and reuse an existing Docker
                 volume/image prefix if one already matches the target name.
"""

VALID_PROJECT_RE_SOURCE = r"^[a-z0-9][a-z0-9_.-]*$"


class RestoreError(Exception):
    pass


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
            except Exception as exc:  # pragma: no cover - defensive
                failures.append(f"{description}: {exc}")
        return failures


def fail(message: str) -> None:
    print(f"{RED}✗{RESET} {message}", file=sys.stderr)
    sys.exit(1)


def warn(message: str) -> None:
    print(f"{YELLOW}⚠{RESET} {message}")


def run_docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def docker_detail(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"


def ensure_docker_success(args: list[str], action: str) -> subprocess.CompletedProcess[str]:
    result = run_docker(args)
    if result.returncode != 0:
        raise RestoreError(f"{action}: {docker_detail(result)}")
    return result


def require_docker_daemon() -> None:
    if shutil.which("docker") is None:
        raise RestoreError("`docker` is not installed or not in PATH.")
    result = run_docker(["info"])
    if result.returncode != 0:
        raise RestoreError(f"Docker daemon is not reachable: {docker_detail(result)}")


def normalize_project_name(name: str) -> str:
    import re

    normalized = name.lower()
    if not re.fullmatch(VALID_PROJECT_RE_SOURCE, normalized):
        raise RestoreError(
            f"project name is invalid after lowercasing: {normalized!r} "
            f"(must match {VALID_PROJECT_RE_SOURCE})"
        )
    return normalized


def list_project_volumes(project: str) -> list[str]:
    result = run_docker(["volume", "ls", "--format", "{{.Name}}"])
    if result.returncode != 0:
        raise RestoreError(f"Failed to list Docker volumes: {docker_detail(result)}")
    prefix = f"{project}_"
    return sorted(name for name in result.stdout.splitlines() if name.startswith(prefix))


def list_project_images(project: str) -> list[str]:
    result = run_docker(["images", "--format", "{{.Repository}}:{{.Tag}}"])
    if result.returncode != 0:
        raise RestoreError(f"Failed to list Docker images: {docker_detail(result)}")
    prefix = f"{project}-"
    return sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if line.partition(":")[0].startswith(prefix)
    )


def resolve_target(arg: str | None, cwd: Path) -> Path:
    if arg is None:
        return cwd.resolve()
    path = Path(arg)
    return path.resolve() if path.is_absolute() else (cwd / arg).resolve()


def confirm_create(target: Path) -> bool:
    answer = input(f"Directory {target} does not exist. Create it? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def parse_args(argv: list[str] | None = None) -> tuple[Path, str | None, str | None, bool]:
    if argv is None:
        argv = sys.argv[1:]

    force = False
    new_name: str | None = None
    positional: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--force":
            force = True
        elif arg == "--name":
            i += 1
            if i >= len(argv):
                print(USAGE, file=sys.stderr)
                sys.exit(1)
            new_name = argv[i]
        elif arg in {"-h", "--help"}:
            print(USAGE)
            sys.exit(0)
        elif arg.startswith("-"):
            print(f"{RED}✗{RESET} Unknown option: {arg}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            sys.exit(1)
        else:
            positional.append(arg)
        i += 1

    if not (1 <= len(positional) <= 2):
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    archive = Path(positional[0]).expanduser().resolve()
    directory_arg = positional[1] if len(positional) == 2 else None
    return archive, directory_arg, new_name, force


def load_manifest(extract_dir: Path) -> dict[str, Any]:
    manifest_path = extract_dir / "metadata" / "backup.json"
    if not manifest_path.exists():
        raise RestoreError(
            f"Archive is missing metadata/backup.json (not a backup.py archive?)"
        )
    try:
        manifest = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise RestoreError(f"metadata/backup.json is not valid JSON: {exc}") from exc

    if manifest.get("format_version") != 1:
        raise RestoreError(
            f"Unsupported backup format_version: {manifest.get('format_version')!r}"
        )
    if "project_name" not in manifest or "volumes" not in manifest:
        raise RestoreError("metadata/backup.json is missing required fields.")
    return manifest


def extract_archive(archive: Path) -> Path:
    if not archive.exists():
        raise RestoreError(f"Archive not found: {archive}")
    extract_dir = Path(tempfile.mkdtemp(prefix="dockerseed-restore-"))
    try:
        with tarfile.open(archive, "r:*") as tar:
            tar.extractall(extract_dir, filter="data")
    except tarfile.TarError as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise RestoreError(f"Failed to read archive: {exc}") from exc

    metadata_dir = extract_dir / "metadata"
    if not (metadata_dir / "containers.json").exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
        raise RestoreError("Archive is missing metadata/containers.json.")
    return extract_dir


def snapshot_path(path: Path) -> bytes | Path | None:
    """Capture enough state to undo overwriting `path` later.

    Returns None if the path did not exist, a Path to a saved backup copy if
    it was a directory, or the raw bytes if it was a file.
    """
    if not path.exists():
        return None
    if path.is_dir():
        backup_copy = Path(tempfile.mkdtemp(prefix="restore-snapshot-")) / path.name
        shutil.copytree(path, backup_copy)
        return backup_copy
    return path.read_bytes()


def restore_snapshot(path: Path, snapshot: bytes | Path | None) -> None:
    if snapshot is None:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink(missing_ok=True)
        return
    if isinstance(snapshot, Path):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        shutil.copytree(snapshot, path)
        shutil.rmtree(snapshot.parent, ignore_errors=True)
        return
    path.write_bytes(snapshot)


def copy_metadata_entry(
    src: Path,
    dest: Path,
    ledger: RollbackLedger,
    label: str,
) -> None:
    if not src.exists():
        return
    previous = snapshot_path(dest)
    if dest.exists():
        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()
    if src.is_dir():
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)
    ledger.append(f"Restore previous {label}", lambda: restore_snapshot(dest, previous))


def rewrite_compose_project_name(env_path: Path, new_name: str) -> None:
    original_text = env_path.read_text() if env_path.exists() else ""
    lines = original_text.splitlines(keepends=True)
    rewritten: list[str] = []
    replaced = False
    for line in lines:
        body = line.splitlines()[0] if line.splitlines() else line
        if body.startswith("COMPOSE_PROJECT_NAME="):
            ending = line[len(body):]
            rewritten.append(f"COMPOSE_PROJECT_NAME={new_name}{ending}")
            replaced = True
        else:
            rewritten.append(line)
    if not replaced:
        prefix = "".join(rewritten)
        if prefix and not prefix.endswith(("\n", "\r")):
            prefix += "\n"
        rewritten = [prefix, f"COMPOSE_PROJECT_NAME={new_name}\n"]
    env_path.write_text("".join(rewritten))


def run_subprocess_step(script: Path, cwd: Path, label: str) -> None:
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=cwd,
        check=False,
    )
    if result.returncode != 0:
        raise RestoreError(f"{label} exited with status {result.returncode}")


def write_rollback_report(
    *,
    project: str,
    target: Path,
    attempted_at: datetime,
    succeeded_steps: list[str],
    failed_step: str,
    rollback_failures: list[str],
    created_volumes: list[str],
    created_target: bool,
) -> Path:
    timestamp = attempted_at.strftime("%Y%m%d%H%M%S")
    base_dir = target.parent if created_target and not target.exists() else target
    if not base_dir.exists():
        base_dir = Path.cwd()
    report_path = base_dir / f"RESTORE-ROLLBACK-{project}-{timestamp}.txt"

    lines = [
        "DockerSeed restore rollback report",
        f"Attempted restore of project: {project}",
        f"Target directory: {target}",
        f"Attempted at: {attempted_at.isoformat()}",
        "",
        "Succeeded steps:",
    ]
    if succeeded_steps:
        lines.extend(f"- {step}" for step in succeeded_steps)
    else:
        lines.append("- None")
    lines += ["", "Failure that triggered rollback:", f"- {failed_step}", "", "Automatic undo failures:"]
    if rollback_failures:
        lines.extend(f"- {failure}" for failure in rollback_failures)
    else:
        lines.append("- None")
    lines += ["", "Manual rollback commands:"]
    if created_volumes:
        for volume in created_volumes:
            lines.append(f"docker volume rm -f {shlex.quote(volume)}")
    else:
        lines.append("# No new volumes were recorded.")
    if created_target:
        lines.append(f"rm -rf {shlex.quote(str(target))}")
    else:
        lines.append(
            f"# Target directory {target} pre-existed; review its contents/backups manually "
            "for any files this restore overwrote."
        )
    report_path.write_text("\n".join(lines))
    return report_path


def main(argv: list[str] | None = None) -> None:
    archive, directory_arg, new_name, force = parse_args(argv)

    try:
        require_docker_daemon()
    except RestoreError as exc:
        fail(str(exc))

    try:
        extract_dir = extract_archive(archive)
    except RestoreError as exc:
        fail(str(exc))
        return

    try:
        manifest = load_manifest(extract_dir)
    except RestoreError as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        fail(str(exc))
        return

    target = resolve_target(directory_arg, CWD)
    created_target = False
    if not target.exists():
        if not confirm_create(target):
            shutil.rmtree(extract_dir, ignore_errors=True)
            print("Aborted.")
            sys.exit(0)
        target.mkdir(parents=True)
        created_target = True
    elif not target.is_dir():
        shutil.rmtree(extract_dir, ignore_errors=True)
        fail(f"Target path exists and is not a directory: {target}")

    conflicting = [
        name
        for name in ("containers.json", ".env")
        if (target / name).exists()
    ]
    if conflicting and not force:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if created_target:
            shutil.rmtree(target, ignore_errors=True)
        fail(
            f"Target directory already has {', '.join(conflicting)}. "
            "Use --force to restore into it anyway."
        )

    try:
        project = normalize_project_name(new_name) if new_name else str(manifest["project_name"])
    except RestoreError as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if created_target:
            shutil.rmtree(target, ignore_errors=True)
        fail(str(exc))
        return

    try:
        existing_volumes = list_project_volumes(project)
        existing_images = list_project_images(project)
    except RestoreError as exc:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if created_target:
            shutil.rmtree(target, ignore_errors=True)
        fail(str(exc))
        return

    if (existing_volumes or existing_images) and not force:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if created_target:
            shutil.rmtree(target, ignore_errors=True)
        fail(
            f"Docker resources already exist for project '{project}' "
            f"(volumes: {existing_volumes}, images: {existing_images}). "
            "Use --force or --name to restore under a different name."
        )

    print(f"{BLUE}⚙{RESET} Restoring project '{project}' into {target}")

    ledger = RollbackLedger()
    attempted_at = datetime.now()
    succeeded_steps: list[str] = []
    created_volumes: list[str] = []

    if created_target:
        ledger.append(f"Remove created directory {target}", lambda: shutil.rmtree(target, ignore_errors=True))
        succeeded_steps.append(f"Created directory {target}")

    try:
        metadata_dir = extract_dir / "metadata"
        for rel in ("containers.json", ".env", "assets.json", "templates", "secrets"):
            src = metadata_dir / rel
            if not src.exists():
                continue
            copy_metadata_entry(src, target / rel, ledger, rel)
            succeeded_steps.append(f"Restored {rel}")
            print(f"{GREEN}✓{RESET} Restored {rel}")

        if new_name or not (target / ".env").exists():
            rewrite_compose_project_name(target / ".env", project)
            succeeded_steps.append(f"Pinned COMPOSE_PROJECT_NAME={project} in .env")
            print(f"{GREEN}✓{RESET} Pinned COMPOSE_PROJECT_NAME={project} in .env")

        volumes_dir = extract_dir / "volumes"
        volume_suffixes: list[str] = manifest.get("volumes", [])
        if volume_suffixes:
            print(f"{BLUE}⚙{RESET} Recreating Docker volumes:")
        for suffix in volume_suffixes:
            tar_path = volumes_dir / f"{suffix}.tar"
            if not tar_path.exists():
                raise RestoreError(f"Archive is missing volumes/{suffix}.tar listed in the manifest.")
            volume_name = f"{project}_{suffix}"
            ensure_docker_success(
                ["volume", "create", volume_name],
                f"Failed to create Docker volume {volume_name}",
            )
            created_volumes.append(volume_name)
            ledger.append(
                f"Remove created volume {volume_name}",
                lambda v=volume_name: ensure_docker_success(
                    ["volume", "rm", "-f", v], f"Failed to remove Docker volume {v}"
                ),
            )
            ensure_docker_success(
                [
                    "run", "--rm",
                    "-v", f"{volume_name}:/vol",
                    "-v", f"{volumes_dir}:/in:ro",
                    HELPER_IMAGE,
                    "tar", "-C", "/vol", "-xf", f"/in/{suffix}.tar",
                ],
                f"Failed to restore data into Docker volume {volume_name}",
            )
            succeeded_steps.append(f"Restored volume {volume_name}")
            print(f"{GREEN}✓{RESET} Restored volume {volume_name}")

        sow_script = SCRIPT_DIR / "sow.py"
        services_existed = (target / "services").exists()
        run_subprocess_step(sow_script, target, "sow.py")
        if not services_existed:
            ledger.append(
                "Remove generated services/",
                lambda: shutil.rmtree(target / "services", ignore_errors=True),
            )
        succeeded_steps.append("Ran sow.py")
        print(f"{GREEN}✓{RESET} Ran sow.py")

        harvest_script = SCRIPT_DIR / "harvest.py"
        compose_existed = (target / "docker-compose.yaml").exists()
        run_subprocess_step(harvest_script, target, "harvest.py")
        if not compose_existed:
            ledger.append(
                "Remove generated docker-compose.yaml",
                lambda: (target / "docker-compose.yaml").unlink(missing_ok=True),
            )
        succeeded_steps.append("Ran harvest.py")
        print(f"{GREEN}✓{RESET} Ran harvest.py")
    except Exception as exc:
        failed_step = str(exc)
        rollback_failures = ledger.rollback()
        report_path: Path | None = None
        if rollback_failures:
            report_path = write_rollback_report(
                project=project,
                target=target,
                attempted_at=attempted_at,
                succeeded_steps=succeeded_steps,
                failed_step=failed_step,
                rollback_failures=rollback_failures,
                created_volumes=created_volumes,
                created_target=created_target,
            )
        shutil.rmtree(extract_dir, ignore_errors=True)
        print(f"{RED}✗{RESET} Restore failed: {failed_step}", file=sys.stderr)
        if rollback_failures:
            print(f"{RED}✗{RESET} Automatic rollback also failed:", file=sys.stderr)
            for failure in rollback_failures:
                print(f"  - {failure}", file=sys.stderr)
            print(f"{YELLOW}⚠{RESET} Manual recovery instructions: {report_path}", file=sys.stderr)
        else:
            print(f"{GREEN}✓{RESET} Automatic rollback completed; no changes remain.")
        sys.exit(1)

    shutil.rmtree(extract_dir, ignore_errors=True)
    print(f"{GREEN}✓{RESET} Restore complete: project '{project}' in {target}")
    print(f"{GREY}◦{RESET} Volumes restored: {len(created_volumes)}")
    print(f"{GREY}◦{RESET} Next: cd {target} && docker-compose build (if not already built by harvest.py)")


if __name__ == "__main__":
    main()
