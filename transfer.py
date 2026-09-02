#!/usr/bin/env python3
"""
transfer.py — Copy a directory between the host and a service named volume.

The target service does not need to be running. Transfer uses a one-shot
alpine helper that mounts the Compose named volume.

Usage:
    ./transfer.py <host-dir> <service>:<volume>:<path>   # import: host → volume
    ./transfer.py <service>:<volume>:<path> <host-dir>   # export: volume → host

Direction is inferred from the arguments. A volume spec is service:volume
or service:volume:path whose first field is a generated service name.
"""

from __future__ import annotations

import argparse
import posixpath
import shutil
import subprocess
import sys
from pathlib import Path

WORK_DIR: Path = Path.cwd()
SERVICES_DIR: Path = WORK_DIR / "services"
ENV_FILE: Path = WORK_DIR / ".env"
COMPOSE_FILE: Path = WORK_DIR / "docker-compose.yaml"
HELPER_IMAGE: str = "alpine"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
GREY = "\033[37m"
RESET = "\033[0m"

USAGE = """\
Usage:
    ./transfer.py [--force] <host-dir> <service>:<volume>[:<path>]
    ./transfer.py [--force] <service>:<volume>[:<path>] <host-dir>

Import copies a host directory into a named volume. Export copies the
other way. Direction is inferred from which argument is a volume spec.

A volume spec's first field must be a generated service (services/<name>/).
<path> is inside that volume: omitted or . for the volume root, a relative
path under it, or an absolute container path under the volume mount.
"""

HELPER_SCRIPT = """\
set -e
if [ "$XFER_REL" = "." ]; then
  DEST=/xfer
else
  DEST=/xfer/$XFER_REL
fi

if [ "$XFER_MODE" = import ]; then
  if [ "$XFER_OVERWRITE" = 1 ]; then
    if [ "$XFER_REL" = "." ]; then
      find /xfer -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    else
      rm -rf "$DEST"
    fi
  fi
  mkdir -p "$DEST"
  tar -C /host -cf - . | tar -C "$DEST" -xf -
  chown -R "$XFER_UID:$XFER_GID" "$DEST"
else
  if [ ! -d "$DEST" ]; then
    echo "Source path does not exist in the volume or is not a directory: $XFER_REL" >&2
    exit 1
  fi
  if [ "$XFER_OVERWRITE" = 1 ]; then
    find /host -mindepth 1 -maxdepth 1 -exec rm -rf {} +
  fi
  tar -C "$DEST" -cf - . | tar -C /host -xf -
fi
"""


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


def existing_service_names(services_dir: Path) -> set[str]:
    if not services_dir.exists():
        return set()
    return {
        path.name
        for path in services_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }


def interpolate_mount(template: str, env: dict[str, str]) -> str:
    result = template
    for name, value in env.items():
        result = result.replace(f"${{{name}}}", value)
    if "${" in result:
        print(
            f"{RED}✗{RESET} Unresolved variable in volume mount '{template}'. "
            "Check .env for CONTAINER_USER and PROJECT.",
            file=sys.stderr,
        )
        sys.exit(1)
    return result


def service_volume_mounts(compose_path: Path) -> dict[str, str]:
    """Return compose volume key → container mount path from the service list."""
    mounts: dict[str, str] = {}
    in_service_volumes = False
    for line in compose_path.read_text().splitlines():
        stripped = line.strip()
        if not in_service_volumes:
            if stripped == "volumes:" and line[:1].isspace():
                in_service_volumes = True
            continue
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            item = stripped[2:]
            name, sep, mount = item.partition(":")
            if sep and name:
                mounts[name.strip()] = mount.strip()
            continue
        break
    return mounts


def parse_volume_spec(spec: str) -> tuple[str, str, str]:
    """Split service:volume[:path] on the first two colons."""
    if ":" not in spec:
        raise ValueError(f"not a volume spec: {spec}")
    service, rest = spec.split(":", 1)
    if ":" in rest:
        volume, path = rest.split(":", 1)
    else:
        volume, path = rest, "."
    if not service:
        raise ValueError("volume spec is missing a service name")
    if not volume:
        raise ValueError("volume spec is missing a volume name")
    if not path or path == "./":
        path = "."
    return service, volume, path


def classify_arg(arg: str, service_names: set[str], cwd: Path) -> str:
    """Return 'spec', 'host', or 'ambiguous'."""
    looks_like_spec = ":" in arg and arg.split(":", 1)[0] in service_names
    path = Path(arg)
    if not path.is_absolute():
        path = cwd / arg
    exists_as_dir = path.is_dir()
    if looks_like_spec and exists_as_dir:
        return "ambiguous"
    if looks_like_spec:
        return "spec"
    return "host"


def detect_direction(
    first: str,
    second: str,
    service_names: set[str],
    cwd: Path,
) -> tuple[str, str, str]:
    """Return (direction, host_dir, spec) where direction is import or export."""
    kind_a = classify_arg(first, service_names, cwd)
    kind_b = classify_arg(second, service_names, cwd)

    if kind_a == "ambiguous" or kind_b == "ambiguous":
        offender = first if kind_a == "ambiguous" else second
        raise ValueError(
            f"ambiguous argument '{offender}': it looks like a volume spec "
            "and exists as a local directory"
        )
    if kind_a == "host" and kind_b == "spec":
        return "import", first, second
    if kind_a == "spec" and kind_b == "host":
        return "export", second, first
    if kind_a == "spec" and kind_b == "spec":
        raise ValueError("both arguments look like volume specs")
    raise ValueError(
        "neither argument looks like a volume spec "
        "(service:volume[:path] with a generated service name)"
    )


def resolve_volume_key(
    volume: str,
    service: str,
    mounts: dict[str, str],
) -> str:
    if volume in mounts:
        return volume
    prefixed = f"{service}_{volume}"
    if prefixed in mounts:
        return prefixed
    available = ", ".join(sorted(mounts)) or "(none)"
    raise ValueError(
        f"volume '{volume}' is not mounted on service '{service}'. "
        f"Available: {available}"
    )


def volume_relative_path(internal: str, mount: str) -> str:
    """Map a volume-internal path to a path relative to the volume root."""
    internal = internal.strip() or "."
    mount_n = posixpath.normpath(mount)

    if internal in (".", "./"):
        return "."

    if posixpath.isabs(internal):
        path_n = posixpath.normpath(internal)
        if path_n == mount_n:
            return "."
        prefix = mount_n.rstrip("/") + "/"
        if not path_n.startswith(prefix):
            raise ValueError(
                f"absolute path '{internal}' is not under volume mount '{mount_n}'"
            )
        rel = path_n[len(prefix) :]
    else:
        rel = posixpath.normpath(internal)

    if rel in (".", ""):
        return "."
    if rel == ".." or rel.startswith("../"):
        raise ValueError(f"path '{internal}' escapes the volume root")
    return rel


def run_docker(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        print(f"{RED}✗{RESET} docker {' '.join(args[:3])} failed: {detail}", file=sys.stderr)
        sys.exit(1)
    return result


def docker_volume_exists(name: str) -> bool:
    return run_docker(["volume", "inspect", name]).returncode == 0


def volume_target_exists(docker_volume: str, rel: str) -> bool:
    dest = "/xfer" if rel == "." else f"/xfer/{rel}"
    if rel == ".":
        result = run_docker(
            [
                "run",
                "--rm",
                "-v",
                f"{docker_volume}:/xfer",
                HELPER_IMAGE,
                "sh",
                "-c",
                "ls -A /xfer | grep -q .",
            ]
        )
        return result.returncode == 0
    result = run_docker(
        ["run", "--rm", "-v", f"{docker_volume}:/xfer", HELPER_IMAGE, "test", "-e", dest]
    )
    return result.returncode == 0


def volume_path_is_dir(docker_volume: str, rel: str) -> bool:
    dest = "/xfer" if rel == "." else f"/xfer/{rel}"
    result = run_docker(
        ["run", "--rm", "-v", f"{docker_volume}:/xfer", HELPER_IMAGE, "test", "-d", dest]
    )
    return result.returncode == 0


def running_services(compose_file: Path, work_dir: Path) -> set[str]:
    if not compose_file.exists():
        return set()
    result = run_docker(
        [
            "compose",
            "-f",
            str(compose_file),
            "--project-directory",
            str(work_dir),
            "ps",
            "--status",
            "running",
            "--format",
            "{{.Service}}",
        ]
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def confirm_overwrite(target: str, *, volume_root: bool, force: bool) -> None:
    extra = ""
    if volume_root:
        extra = " This is the volume root; all contents will be replaced."
    print(f"{YELLOW}⚠{RESET} Target already exists: {target}.{extra}")
    if force:
        print(f"{GREY}◦{RESET} --force: overwriting.")
        return
    answer = input(f"Overwrite {target}? [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Aborted.")
        sys.exit(1)


def require_docker() -> None:
    if shutil.which("docker") is None:
        print(f"{RED}✗{RESET} `docker` is not installed or not in PATH.", file=sys.stderr)
        sys.exit(1)


def resolve_host_dir(host_dir: str, cwd: Path) -> Path:
    path = Path(host_dir)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def run_transfer(
    *,
    mode: str,
    docker_volume: str,
    rel: str,
    host_dir: Path,
    overwrite: bool,
    uid: str,
    gid: str,
) -> None:
    env_flags = [
        "-e",
        f"XFER_MODE={mode}",
        "-e",
        f"XFER_REL={rel}",
        "-e",
        f"XFER_OVERWRITE={'1' if overwrite else '0'}",
        "-e",
        f"XFER_UID={uid}",
        "-e",
        f"XFER_GID={gid}",
    ]
    result = run_docker(
        [
            "run",
            "--rm",
            *env_flags,
            "-v",
            f"{docker_volume}:/xfer",
            "-v",
            f"{host_dir}:/host",
            HELPER_IMAGE,
            "sh",
            "-c",
            HELPER_SCRIPT,
        ]
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        print(f"{RED}✗{RESET} Transfer failed: {detail}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="transfer.py",
        description="Copy a directory between the host and a DockerSeed named volume.",
        epilog=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the target directory without prompting",
    )
    parser.add_argument("first", help="host directory or service:volume[:path]")
    parser.add_argument("second", help="the other of host directory or volume spec")
    args = parser.parse_args(argv)

    service_names = existing_service_names(SERVICES_DIR)
    try:
        direction, host_arg, spec = detect_direction(
            args.first, args.second, service_names, WORK_DIR
        )
    except ValueError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        if not service_names:
            print(
                f"{GREY}◦{RESET} No generated services found — run ./sow.py first.",
                file=sys.stderr,
            )
        print(USAGE, file=sys.stderr)
        sys.exit(1)

    try:
        service, volume, internal = parse_volume_spec(spec)
    except ValueError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        sys.exit(1)

    compose_path = SERVICES_DIR / service / "docker-compose.yaml"
    if not compose_path.exists():
        print(
            f"{RED}✗{RESET} {compose_path} not found — run ./sow.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    mounts = service_volume_mounts(compose_path)
    try:
        volume_key = resolve_volume_key(volume, service, mounts)
    except ValueError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        sys.exit(1)

    env = load_env(ENV_FILE)
    mount = interpolate_mount(mounts[volume_key], env)
    try:
        rel = volume_relative_path(internal, mount)
    except ValueError as exc:
        print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
        sys.exit(1)

    uid = env.get("CONTAINER_USER_ID")
    if not uid:
        print(
            f"{RED}✗{RESET} CONTAINER_USER_ID is missing from .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    project = compose_project_name(WORK_DIR, env)
    docker_volume = f"{project}_{volume_key}"
    host_dir = resolve_host_dir(host_arg, WORK_DIR)
    volume_root = rel == "."
    loc = f"{service}:{volume_key}:{rel}"

    verb = "Importing" if direction == "import" else "Exporting"
    print(f"{BLUE}⚙{RESET} {verb} {'host → volume' if direction == 'import' else 'volume → host'}")
    print(f"{GREY}◦{RESET} Host: {host_dir}")
    print(f"{GREY}◦{RESET} Spec: {loc}")
    print(f"{GREY}◦{RESET} Docker volume: {docker_volume}")
    print(f"{GREY}◦{RESET} Volume mount: {mount}")

    require_docker()

    running = running_services(COMPOSE_FILE, WORK_DIR)
    if service in running:
        print(
            f"{YELLOW}⚠{RESET} Service '{service}' is running; "
            "open files in the volume may be in use."
        )

    overwrite = False
    if direction == "import":
        if not host_dir.is_dir():
            print(
                f"{RED}✗{RESET} Host path is not an existing directory: {host_dir}",
                file=sys.stderr,
            )
            sys.exit(1)

        created_volume = not docker_volume_exists(docker_volume)
        if created_volume:
            print(
                f"{YELLOW}⚠{RESET} Volume {docker_volume} does not exist yet; "
                "it will be created."
            )

        if not created_volume and volume_target_exists(docker_volume, rel):
            confirm_overwrite(loc, volume_root=volume_root, force=args.force)
            overwrite = True

        run_transfer(
            mode="import",
            docker_volume=docker_volume,
            rel=rel,
            host_dir=host_dir,
            overwrite=overwrite,
            uid=uid,
            gid=uid,
        )
        print(f"{GREEN}✓{RESET} Imported {host_dir} → {docker_volume}:{rel}")
        return

    if not docker_volume_exists(docker_volume):
        print(
            f"{RED}✗{RESET} Docker volume {docker_volume} does not exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not volume_path_is_dir(docker_volume, rel):
        print(
            f"{RED}✗{RESET} Source path does not exist in the volume "
            f"or is not a directory: {loc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if host_dir.exists():
        if not host_dir.is_dir():
            print(
                f"{RED}✗{RESET} Host path exists and is not a directory: {host_dir}",
                file=sys.stderr,
            )
            sys.exit(1)
        confirm_overwrite(str(host_dir), volume_root=False, force=args.force)
        overwrite = True
    else:
        host_dir.mkdir(parents=True, exist_ok=True)

    run_transfer(
        mode="export",
        docker_volume=docker_volume,
        rel=rel,
        host_dir=host_dir,
        overwrite=overwrite,
        uid=uid,
        gid=uid,
    )
    print(f"{GREEN}✓{RESET} Exported {docker_volume}:{rel} → {host_dir}")


if __name__ == "__main__":
    main()
