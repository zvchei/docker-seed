#!/usr/bin/env python3
"""
backup.py — Archive a DockerSeed project and its live Docker named volumes
into a single restorable .tar file.

Operates on the current working directory: reads project metadata from cwd,
exports Docker volumes for the current Compose project, and writes one archive
that restore.py consumes using this exact top-level layout:

  metadata/backup.json      # manifest/contract for restore.py
  metadata/containers.json  # required
  metadata/.env             # optional
  metadata/assets.json      # optional
  metadata/templates/       # optional local cwd overlay
  metadata/secrets/         # optional, only when included explicitly
  volumes/<suffix>.tar      # one tar per Docker volume, where <suffix> is the
                            # volume name without the "<project>_" prefix

The archive itself is written uncompressed (plain .tar) so backup.py never
sits silently churning through a slow, single-threaded gzip pass. Compress it
afterwards if you want to save space; restore.py accepts both plain .tar and
gzip-compressed .tar.gz archives. For a compression command that actually
shows progress (plain `gzip` doesn't), pipe through `pv` (pipe-viewer):

    pv backup.tar | gzip > backup.tar.gz

(install with e.g. `apt install pv` / `brew install pv`; without it, plain
`gzip backup.tar` still works, just silently.)

Usage:
    ./backup.py [output.tar] [--force] [--include-secrets] [--no-secrets]

The archive is assembled in a staging directory first, then atomically moved
into place so failures never leave a partial final backup file behind.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORK_DIR: Path = Path.cwd()
CONTAINERS_FILE: Path = WORK_DIR / "containers.json"
ENV_FILE: Path = WORK_DIR / ".env"
ASSETS_FILE: Path = WORK_DIR / "assets.json"
TEMPLATES_DIR: Path = WORK_DIR / "templates"
SECRETS_DIR: Path = WORK_DIR / "secrets"
HELPER_IMAGE: str = "alpine"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
GREY = "\033[37m"
RESET = "\033[0m"

USAGE = f"""\
{BLUE}Usage:{RESET}
    ./backup.py [output.tar] [--force] [--include-secrets] [--no-secrets]

Create one restorable DockerSeed backup archive from the current working
directory and its Docker named volumes.

The archive is written uncompressed (plain .tar). Compress it afterwards if
you want to save space; restore.py accepts both .tar and .tar.gz. Plain
`gzip` gives no progress feedback — pipe through `pv` for a live progress
bar instead: {GREY}pv backup.tar | gzip > backup.tar.gz{RESET}

Options:
    {GREEN}--force{RESET}            overwrite an existing destination file
    {GREEN}--include-secrets{RESET}  include real files under ./secrets/ without prompting
    {GREEN}--no-secrets{RESET}       skip ./secrets/ without prompting
"""

KNOWN_SECRET_PLACEHOLDERS: frozenset[str] = frozenset({"README", "ssh/README"})


class BackupError(Exception):
    pass


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


def list_project_volumes(project: str) -> list[str]:
    result = run_docker(["volume", "ls", "--format", "{{.Name}}"])
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise BackupError(f"Failed to list Docker volumes: {detail}")

    prefix = f"{project}_"
    return sorted(name for name in result.stdout.splitlines() if name.startswith(prefix))


def strip_project_volume_suffix(volume_name: str, project: str) -> str:
    prefix = f"{project}_"
    if not volume_name.startswith(prefix):
        raise ValueError(
            f"volume '{volume_name}' does not start with expected prefix '{prefix}'"
        )
    return volume_name[len(prefix) :]


def secrets_have_real_content(secrets_dir: Path) -> bool:
    if not secrets_dir.exists() or not secrets_dir.is_dir():
        return False

    for path in secrets_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(secrets_dir).as_posix()
        if rel not in KNOWN_SECRET_PLACEHOLDERS:
            return True
    return False


def prompt_include_secrets() -> bool:
    while True:
        answer = input(
            "secrets/ contains files beyond placeholders. Include them in the backup? [y/n]: "
        ).strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False


def default_backup_path(
    work_dir: Path,
    project: str,
    now: datetime | None = None,
) -> Path:
    timestamp = backup_timestamp(now)
    return work_dir / f"{project}-backup-{timestamp}.tar"


def backup_timestamp(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return stamp.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")


def manifest_timestamp(now: datetime | None = None) -> str:
    stamp = now or datetime.now(timezone.utc)
    return (
        stamp.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_backup_manifest(
    project_name: str,
    created_at: datetime,
    volumes: list[str],
    included_secrets: bool,
) -> dict[str, Any]:
    return {
        "format_version": 1,
        "project_name": project_name,
        "created_at": manifest_timestamp(created_at),
        "volumes": list(volumes),
        "included_secrets": included_secrets,
    }


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def parse_args(argv: list[str]) -> tuple[str | None, bool, bool | None]:
    output_arg: str | None = None
    force = False
    include_secrets: bool | None = None

    for arg in argv:
        if arg == "--force":
            force = True
        elif arg == "--include-secrets":
            if include_secrets is False:
                raise BackupError("--include-secrets and --no-secrets are mutually exclusive.")
            include_secrets = True
        elif arg == "--no-secrets":
            if include_secrets is True:
                raise BackupError("--include-secrets and --no-secrets are mutually exclusive.")
            include_secrets = False
        elif arg.startswith("-"):
            raise BackupError(f"Unknown option: {arg}")
        elif output_arg is None:
            output_arg = arg
        else:
            raise BackupError("Expected at most one output path.")

    return output_arg, force, include_secrets


def require_docker_daemon() -> None:
    try:
        result = run_docker(["info"])
    except FileNotFoundError as exc:
        raise BackupError("`docker` is not installed or not in PATH.") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise BackupError(f"Docker daemon is not reachable: {detail}")


def ensure_destination_parent_writable(dest: Path) -> None:
    parent = dest.parent
    if not parent.exists():
        raise BackupError(f"Destination directory does not exist: {parent}")
    if not parent.is_dir():
        raise BackupError(f"Destination parent is not a directory: {parent}")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise BackupError(f"Destination directory is not writable: {parent}")


def run_preflight(dest: Path, *, force: bool) -> None:
    require_docker_daemon()

    if not CONTAINERS_FILE.exists():
        raise BackupError(f"{CONTAINERS_FILE} not found.")

    if dest.exists():
        if dest.is_dir():
            raise BackupError(f"Destination path is a directory: {dest}")
        if not force:
            raise BackupError(f"Destination already exists: {dest} (use --force to overwrite).")

    ensure_destination_parent_writable(dest)


def stage_project_metadata(
    metadata_dir: Path,
    *,
    include_secrets: bool,
) -> None:
    shutil.copy2(CONTAINERS_FILE, metadata_dir / "containers.json")

    if ENV_FILE.exists():
        shutil.copy2(ENV_FILE, metadata_dir / ".env")

    if ASSETS_FILE.exists():
        shutil.copy2(ASSETS_FILE, metadata_dir / "assets.json")

    if TEMPLATES_DIR.exists():
        shutil.copytree(TEMPLATES_DIR, metadata_dir / "templates")

    if include_secrets and SECRETS_DIR.exists():
        shutil.copytree(SECRETS_DIR, metadata_dir / "secrets")


def export_volume_tar(volume_name: str, suffix: str, output_dir: Path) -> None:
    result = run_docker(
        [
            "run",
            "--rm",
            "-v",
            f"{volume_name}:/vol:ro",
            "-v",
            f"{output_dir}:/out",
            HELPER_IMAGE,
            "tar",
            "-C",
            "/vol",
            "-cf",
            f"/out/{suffix}.tar",
            ".",
        ]
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise BackupError(f"Failed to export volume {volume_name}: {detail}")


def write_archive(staging_dir: Path, tmp_output_path: Path) -> None:
    with tarfile.open(tmp_output_path, "w:") as archive:
        for path in sorted(staging_dir.iterdir(), key=lambda item: item.name):
            archive.add(path, arcname=path.name)


def choose_secrets_policy(has_real_secrets: bool, override: bool | None) -> bool:
    if not has_real_secrets:
        return False
    if override is not None:
        return override
    return prompt_include_secrets()


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)

    try:
        output_arg, force, secrets_override = parse_args(argv)
    except BackupError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    env = load_env(ENV_FILE)
    project = compose_project_name(WORK_DIR, env)
    dest = (
        default_backup_path(WORK_DIR, project)
        if output_arg is None
        else Path(output_arg).expanduser()
    )
    if not dest.is_absolute():
        dest = (WORK_DIR / dest).resolve()

    run_preflight(dest, force=force)

    include_secrets = choose_secrets_policy(
        secrets_have_real_content(SECRETS_DIR),
        secrets_override,
    )

    created_at = datetime.now(timezone.utc)
    staging_dir: Path | None = None
    tmp_output_path: Path | None = None

    try:
        print(f"{BLUE}⚙{RESET} Project: {project}")
        print(f"{BLUE}⚙{RESET} Destination: {dest}")

        staging_dir = Path(
            tempfile.mkdtemp(
                prefix=f"{project}-backup-",
                dir=WORK_DIR,
            )
        )
        metadata_dir = staging_dir / "metadata"
        volumes_dir = staging_dir / "volumes"
        metadata_dir.mkdir()
        volumes_dir.mkdir()

        stage_project_metadata(metadata_dir, include_secrets=include_secrets)
        print(f"{GREEN}✓{RESET} Staged project metadata.")

        volume_names = list_project_volumes(project)
        volume_suffixes: list[str] = []
        if not volume_names:
            print(f"{YELLOW}⚠{RESET} No Docker volumes found for project {project}.")
        else:
            print(f"{BLUE}⚙{RESET} Exporting Docker volumes:")

        for volume_name in volume_names:
            suffix = strip_project_volume_suffix(volume_name, project)
            export_volume_tar(volume_name, suffix, volumes_dir)
            volume_suffixes.append(suffix)
            print(f"\t{GREEN}✓{RESET} {volume_name} → volumes/{suffix}.tar")

        manifest = build_backup_manifest(
            project_name=project,
            created_at=created_at,
            volumes=volume_suffixes,
            included_secrets=include_secrets,
        )
        # restore.py relies on metadata/backup.json and the top-level
        # metadata/ + volumes/ archive layout defined in this script's docstring.
        (metadata_dir / "backup.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{GREEN}✓{RESET} Wrote metadata/backup.json.")

        with tempfile.NamedTemporaryFile(
            dir=dest.parent,
            prefix=f"{dest.stem}-",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            tmp_output_path = Path(tmp_file.name)

        write_archive(staging_dir, tmp_output_path)
        os.replace(tmp_output_path, dest)
        tmp_output_path = None

        print(f"{GREEN}✓{RESET} Backup created.")
        print(f"{GREY}◦{RESET} Archive: {dest}")
        print(f"{GREY}◦{RESET} Project: {project}")
        print(f"{GREY}◦{RESET} Volumes archived: {len(volume_suffixes)}")
        print(
            f"{GREY}◦{RESET} Secrets included: {'yes' if include_secrets else 'no'}"
        )
        print(f"{GREY}◦{RESET} Size: {format_size(dest.stat().st_size)}")
    finally:
        if staging_dir is not None and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if tmp_output_path is not None and tmp_output_path.exists():
            tmp_output_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except BackupError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        sys.exit(1)
