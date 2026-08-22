#!/usr/bin/env python3
"""
cleanup.py — Reconcile generated services/, Docker images, and volumes
with containers.json.

Steps:
  1. Compare services/ against every entry in containers.json
  2. Remove services/<name>/ directories that are no longer declared
  3. List Docker images that use the compose project prefix
  4. Report stale images (no matching service in containers.json)
  5. Report stale volumes (not used by any declared service)
  6. Write a temporary shell script to remove stale images and volumes,
     open it in $EDITOR for review, then optionally run it
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import seed

SCRIPT_DIR: Path = Path(__file__).resolve().parent
SERVICES_DIR: Path = SCRIPT_DIR / "services"
CONTAINERS_FILE: Path = SCRIPT_DIR / "containers.json"
ENV_FILE: Path = SCRIPT_DIR / ".env"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
GREY = "\033[37m"
RESET = "\033[0m"


def load_containers(containers_file: Path) -> list[dict[str, Any]]:
    if not containers_file.exists():
        print(f"{RED}✗{RESET} {containers_file} not found.")
        sys.exit(1)

    with open(containers_file) as f:
        return json.load(f)


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


def compose_project_name(script_dir: Path, env: dict[str, str]) -> str:
    if project := env.get("COMPOSE_PROJECT_NAME"):
        return project
    return script_dir.name.lower()


def declared_service_names(containers: list[dict[str, Any]]) -> set[str]:
    return {container["name"] for container in containers}


def existing_service_dirs(services_dir: Path) -> set[str]:
    if not services_dir.exists():
        return set()
    return {
        path.name
        for path in services_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }


def image_service_names(containers: list[dict[str, Any]]) -> set[str]:
    """Return service names whose project-prefixed Docker images should be kept."""
    return {"base", *(container["name"] for container in containers)}


def expected_volume_names(containers: list[dict[str, Any]]) -> set[str]:
    """Return compose volume keys declared across all containers."""
    names: set[str] = {"root"}
    for container in containers:
        merged = seed.build_merged_for_container(container, containers)
        names.update(seed.resolve_container_volumes(container["name"], merged))
    return names


def run_docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
    )


def list_project_images(project: str) -> list[str]:
    result = run_docker(["images", "--format", "{{.Repository}}:{{.Tag}}"])
    if result.returncode != 0:
        print(f"{RED}✗{RESET} Failed to list Docker images: {result.stderr.strip()}")
        sys.exit(1)

    prefix = f"{project}-"
    images: list[str] = []
    for line in result.stdout.splitlines():
        repository = line.partition(":")[0]
        if repository.startswith(prefix):
            images.append(line.strip())
    return sorted(set(images))


def list_project_volumes(project: str) -> list[str]:
    result = run_docker(["volume", "ls", "--format", "{{.Name}}"])
    if result.returncode != 0:
        print(f"{RED}✗{RESET} Failed to list Docker volumes: {result.stderr.strip()}")
        sys.exit(1)

    prefix = f"{project}_"
    return sorted(name for name in result.stdout.splitlines() if name.startswith(prefix))


def audit_services(
    declared: set[str],
    existing: set[str],
) -> tuple[list[str], list[str], list[str]]:
    missing = sorted(declared - existing)
    extra = sorted(existing - declared)
    present = sorted(declared & existing)
    return missing, extra, present


def cleanup_service_dirs(extra: list[str], services_dir: Path) -> None:
    if not extra:
        print(f"{GREEN}✓{RESET} No extra service directories to remove.")
        return

    print(f"\n{BLUE}⚙{RESET} Removing extra service directories:")
    for name in extra:
        target = services_dir / name
        print(f"\t{GREY}✕{RESET} {target}")
        shutil.rmtree(target)
    print(f"{GREEN}✓{RESET} Removed {len(extra)} extra service director{'y' if len(extra) == 1 else 'ies'}.")


def find_stale_images(
    project_images: list[str],
    valid_names: set[str],
    project: str,
) -> list[str]:
    prefix = f"{project}-"
    stale: list[str] = []
    for image in project_images:
        service_name = image.partition(":")[0][len(prefix) :]
        if service_name not in valid_names:
            stale.append(image)
    return stale


def find_stale_volumes(
    project_volumes: list[str],
    valid_names: set[str],
    project: str,
) -> list[str]:
    prefix = f"{project}_"
    stale: list[str] = []
    for volume in project_volumes:
        volume_name = volume[len(prefix) :]
        if volume_name not in valid_names:
            stale.append(volume)
    return stale


def report_stale_items(label: str, stale: list[str]) -> None:
    print(f"\n{BLUE}⚙{RESET} {label}:")
    if stale:
        for item in stale:
            print(f"\t{YELLOW}◦{RESET} {item}")
    else:
        print(f"\t{GREEN}✓{RESET} None")


def default_editor() -> str:
    for var in ("VISUAL", "EDITOR"):
        if editor := os.environ.get(var):
            return editor
    return "vi"


def write_cleanup_script(
    stale_images: list[str],
    stale_volumes: list[str],
    project: str,
) -> Path:
    fd, path_str = tempfile.mkstemp(
        prefix=f"{project}-cleanup-",
        suffix=".sh",
        text=True,
    )
    script_path = Path(path_str)
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated by cleanup.py — removes stale DockerSeed images and volumes.",
        "# Review and edit before running.",
        "",
    ]

    if stale_images:
        lines.append("# Stale images")
        for image in stale_images:
            lines.append(f"docker rmi {shlex.quote(image)}")
        lines.append("")

    if stale_volumes:
        lines.append("# Stale volumes")
        for volume in stale_volumes:
            lines.append(f"docker volume rm {shlex.quote(volume)}")
        lines.append("")

    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines))

    script_path.chmod(script_path.stat().st_mode | 0o111)
    return script_path


def open_in_editor(path: Path) -> None:
    editor = default_editor()
    print(f"\n{BLUE}⚙{RESET} Opening cleanup script in {editor}:")
    print(f"\t{GREY}◦{RESET} {path}")
    subprocess.run([*shlex.split(editor), str(path)], check=True)


def prompt_run_cleanup_script(path: Path) -> None:
    answer = input(f"\nRun this cleanup script? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        print(f"{GREY}◦{RESET} Skipped. Script left at {path}")
        return

    print(f"\n{BLUE}⚙{RESET} Running {path}")
    result = subprocess.run([str(path)], check=False)
    if result.returncode == 0:
        print(f"{GREEN}✓{RESET} Cleanup script completed.")
        path.unlink(missing_ok=True)
    else:
        print(f"{RED}✗{RESET} Cleanup script failed with exit code {result.returncode}.")
        print(f"{GREY}◦{RESET} Script left at {path}")


def main() -> None:
    if shutil.which("docker") is None:
        print(f"{RED}✗{RESET} `docker` is not installed or not in PATH.")
        sys.exit(1)

    containers = load_containers(CONTAINERS_FILE)
    env = load_env(ENV_FILE)
    project = compose_project_name(SCRIPT_DIR, env)

    declared = declared_service_names(containers)
    existing = existing_service_dirs(SERVICES_DIR)
    missing, extra, present = audit_services(declared, existing)

    print(f"{BLUE}⚙{RESET} Project prefix: {project}")
    print(f"{BLUE}⚙{RESET} Declared services in containers.json: {len(declared)}")
    print(f"{BLUE}⚙{RESET} Service directories under services/: {len(existing)}")

    print(f"\n{BLUE}⚙{RESET} Services present:")
    if present:
        for name in present:
            print(f"\t{GREEN}✓{RESET} {name}")
    else:
        print(f"\t{GREY}◦{RESET} None")

    print(f"\n{BLUE}⚙{RESET} Services missing from services/ (run ./seed.py to generate):")
    if missing:
        for name in missing:
            print(f"\t{YELLOW}◦{RESET} {name}")
    else:
        print(f"\t{GREEN}✓{RESET} None")

    cleanup_service_dirs(extra, SERVICES_DIR)

    project_images = list_project_images(project)
    print(f"\n{BLUE}⚙{RESET} Project images ({project}-*):")
    if project_images:
        for image in project_images:
            print(f"\t{GREY}◦{RESET} {image}")
    else:
        print(f"\t{GREY}◦{RESET} None")

    valid_image_names = image_service_names(containers)
    stale_images = find_stale_images(project_images, valid_image_names, project)
    report_stale_items(
        "Stale images (no matching service in containers.json)",
        stale_images,
    )

    project_volumes = list_project_volumes(project)
    print(f"\n{BLUE}⚙{RESET} Project volumes ({project}_*):")
    if project_volumes:
        for volume in project_volumes:
            print(f"\t{GREY}◦{RESET} {volume}")
    else:
        print(f"\t{GREY}◦{RESET} None")

    valid_volume_names = expected_volume_names(containers)
    stale_volumes = find_stale_volumes(project_volumes, valid_volume_names, project)
    report_stale_items(
        "Stale volumes (not declared by any service in containers.json)",
        stale_volumes,
    )

    if stale_images or stale_volumes:
        script_path = write_cleanup_script(stale_images, stale_volumes, project)
        open_in_editor(script_path)
        prompt_run_cleanup_script(script_path)
    else:
        print(f"\n{GREEN}✓{RESET} No stale images or volumes to remove.")


if __name__ == "__main__":
    main()
