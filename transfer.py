#!/usr/bin/env python3
"""
transfer.py — Copy a directory or file between the host and a service named volume.

The target service does not need to be running. Transfer uses a one-shot
alpine helper that mounts the Compose named volume.

Usage:
    ./transfer.py <host-path> <service>:<volume>:<path>   # import: host → volume
    ./transfer.py <service>:<volume>:<path> <host-path>   # export: volume → host

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
    ./transfer.py [--force] <host-path> <service>:<volume>[:<path>]
    ./transfer.py [--force] <service>:<volume>[:<path>] <host-path>

Import (host → volume) or export (volume → host); direction is inferred from
which argument is a volume spec. The spec's first field must be a generated
service (services/<name>/). <path> is inside that volume: omitted or . for the
volume root, a relative path, or an absolute container path under the mount.

Examples (import; reverse the args to export):

  # Directory as directory — contents of ./dir become volume path dir/
  ./transfer.py ./dir service:volume:dir

  # Directory into directory — contents of ./dir go into dest/ (trailing / optional)
  ./transfer.py ./dir service:volume:dest/

  # File as file — copy/rename to an exact path
  ./transfer.py ./file.ext service:volume:file.ext
  ./transfer.py ./file.ext service:volume:path/to/other.ext

  # File into directory — keep basename; trailing / forces dir even if missing
  ./transfer.py ./file.ext service:volume:dest/
  ./transfer.py ./file.ext service:volume          # into volume root

  # Export file as file (including rename) / into directory
  ./transfer.py service:volume:file.ext ./path/to/other.ext
  ./transfer.py service:volume:file.ext ./dest/

For files: if the destination exists as a directory (or is the volume root), or
ends with /, the file is placed inside it under the same basename; otherwise the
path is the destination file (parents are created as needed). Directory transfers
always copy contents into the destination path. --force skips the overwrite prompt.
"""

HELPER_SCRIPT = """\
set -e
if [ "$XFER_REL" = "." ]; then
  DEST=/xfer
else
  DEST=/xfer/$XFER_REL
fi

if [ "$XFER_KIND" = file ]; then
  if [ "$XFER_MODE" = import ]; then
    if [ "$XFER_OVERWRITE" = 1 ]; then
      rm -f "$DEST"
    fi
    mkdir -p "$(dirname "$DEST")"
    cp "/host/$XFER_NAME" "$DEST"
    chown "$XFER_UID:$XFER_GID" "$DEST"
  else
    if [ ! -f "$DEST" ]; then
      echo "Source path does not exist in the volume or is not a file: $XFER_REL" >&2
      exit 1
    fi
    if [ "$XFER_OVERWRITE" = 1 ]; then
      rm -f "/host/$XFER_NAME"
    fi
    cp "$DEST" "/host/$XFER_NAME"
  fi
  exit 0
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
    """Return (direction, host_path, spec) where direction is import or export."""
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


def path_implies_directory(path: str) -> bool:
    """True when a trailing slash marks the path as a directory destination."""
    stripped = path.strip()
    return bool(stripped) and stripped.endswith("/")


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


def resolve_import_file_rel(rel: str, basename: str, *, dest_is_dir: bool) -> str:
    """Resolve the volume-relative destination for a file import."""
    if rel == "." or dest_is_dir:
        if rel == ".":
            return basename
        return posixpath.normpath(posixpath.join(rel, basename))
    return rel


def resolve_export_file_host(
    host: Path,
    volume_basename: str,
    *,
    dest_is_dir: bool = False,
) -> Path:
    """Resolve the host destination path for a file export."""
    if dest_is_dir or (host.exists() and host.is_dir()):
        return host / volume_basename
    return host


def ensure_parent_dir(path: Path) -> None:
    """Create parent directories for a file path; fail if a parent is not a directory."""
    parent = path.parent
    if parent.exists() and not parent.is_dir():
        raise ValueError(f"parent path exists and is not a directory: {parent}")
    parent.mkdir(parents=True, exist_ok=True)


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


def volume_path_is_file(docker_volume: str, rel: str) -> bool:
    if rel == ".":
        return False
    dest = f"/xfer/{rel}"
    result = run_docker(
        ["run", "--rm", "-v", f"{docker_volume}:/xfer", HELPER_IMAGE, "test", "-f", dest]
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


def resolve_host_path(host_path: str, cwd: Path) -> Path:
    path = Path(host_path)
    if not path.is_absolute():
        path = cwd / path
    return path.resolve()


def run_transfer(
    *,
    mode: str,
    kind: str,
    docker_volume: str,
    rel: str,
    host_mount: Path,
    host_name: str,
    overwrite: bool,
    uid: str,
    gid: str,
) -> None:
    env_flags = [
        "-e",
        f"XFER_MODE={mode}",
        "-e",
        f"XFER_KIND={kind}",
        "-e",
        f"XFER_REL={rel}",
        "-e",
        f"XFER_NAME={host_name}",
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
            f"{host_mount}:/host",
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
        description="Copy a directory or file between the host and a DockerSeed named volume.",
        epilog=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite the target without prompting",
    )
    parser.add_argument("first", help="host path or service:volume[:path]")
    parser.add_argument("second", help="the other of host path or volume spec")
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
    volume_path_is_explicit_dir = path_implies_directory(internal)
    host_path_is_explicit_dir = path_implies_directory(host_arg)
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
    host_path = resolve_host_path(host_arg, WORK_DIR)

    require_docker()

    running = running_services(COMPOSE_FILE, WORK_DIR)
    if service in running:
        print(
            f"{YELLOW}⚠{RESET} Service '{service}' is running; "
            "open files in the volume may be in use."
        )

    overwrite = False
    if direction == "import":
        if host_path.is_file():
            kind = "file"
            created_volume = not docker_volume_exists(docker_volume)
            if created_volume:
                print(
                    f"{YELLOW}⚠{RESET} Volume {docker_volume} does not exist yet; "
                    "it will be created."
                )
                dest_is_dir = volume_path_is_explicit_dir
            else:
                if volume_path_is_explicit_dir:
                    if volume_path_is_file(docker_volume, rel):
                        print(
                            f"{RED}✗{RESET} Destination path ends with '/' but "
                            f"exists as a file in the volume: {service}:{volume_key}:{rel}",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                    dest_is_dir = True
                elif volume_path_is_file(docker_volume, rel):
                    dest_is_dir = False
                elif volume_path_is_dir(docker_volume, rel) or rel == ".":
                    dest_is_dir = True
                else:
                    dest_is_dir = False

            dest_rel = resolve_import_file_rel(
                rel, host_path.name, dest_is_dir=dest_is_dir
            )
            loc = f"{service}:{volume_key}:{dest_rel}"

            print(f"{BLUE}⚙{RESET} Importing host → volume (file)")
            print(f"{GREY}◦{RESET} Host: {host_path}")
            print(f"{GREY}◦{RESET} Spec: {loc}")
            print(f"{GREY}◦{RESET} Docker volume: {docker_volume}")
            print(f"{GREY}◦{RESET} Volume mount: {mount}")

            if not created_volume and volume_target_exists(docker_volume, dest_rel):
                if volume_path_is_dir(docker_volume, dest_rel):
                    print(
                        f"{RED}✗{RESET} Destination exists as a directory in the volume: {loc}",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                confirm_overwrite(loc, volume_root=False, force=args.force)
                overwrite = True

            run_transfer(
                mode="import",
                kind=kind,
                docker_volume=docker_volume,
                rel=dest_rel,
                host_mount=host_path.parent,
                host_name=host_path.name,
                overwrite=overwrite,
                uid=uid,
                gid=uid,
            )
            print(f"{GREEN}✓{RESET} Imported {host_path} → {docker_volume}:{dest_rel}")
            return

        if not host_path.is_dir():
            print(
                f"{RED}✗{RESET} Host path is not an existing directory or file: {host_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        if docker_volume_exists(docker_volume) and volume_path_is_file(docker_volume, rel):
            print(
                f"{RED}✗{RESET} Cannot import a directory onto a file in the volume: "
                f"{service}:{volume_key}:{rel}",
                file=sys.stderr,
            )
            sys.exit(1)

        loc = f"{service}:{volume_key}:{rel}"
        volume_root = rel == "."

        print(f"{BLUE}⚙{RESET} Importing host → volume")
        print(f"{GREY}◦{RESET} Host: {host_path}")
        print(f"{GREY}◦{RESET} Spec: {loc}")
        print(f"{GREY}◦{RESET} Docker volume: {docker_volume}")
        print(f"{GREY}◦{RESET} Volume mount: {mount}")

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
            kind="dir",
            docker_volume=docker_volume,
            rel=rel,
            host_mount=host_path,
            host_name=".",
            overwrite=overwrite,
            uid=uid,
            gid=uid,
        )
        print(f"{GREEN}✓{RESET} Imported {host_path} → {docker_volume}:{rel}")
        return

    if not docker_volume_exists(docker_volume):
        print(
            f"{RED}✗{RESET} Docker volume {docker_volume} does not exist.",
            file=sys.stderr,
        )
        sys.exit(1)

    if volume_path_is_file(docker_volume, rel):
        kind = "file"
        volume_basename = posixpath.basename(rel)
        if host_path_is_explicit_dir and host_path.exists() and host_path.is_file():
            print(
                f"{RED}✗{RESET} Host path ends with '/' but exists as a file: {host_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        dest_host = resolve_export_file_host(
            host_path,
            volume_basename,
            dest_is_dir=host_path_is_explicit_dir,
        )

        loc = f"{service}:{volume_key}:{rel}"
        print(f"{BLUE}⚙{RESET} Exporting volume → host (file)")
        print(f"{GREY}◦{RESET} Host: {dest_host}")
        print(f"{GREY}◦{RESET} Spec: {loc}")
        print(f"{GREY}◦{RESET} Docker volume: {docker_volume}")
        print(f"{GREY}◦{RESET} Volume mount: {mount}")

        if dest_host.exists() and dest_host.is_dir():
            print(
                f"{RED}✗{RESET} Host path exists and is a directory: {dest_host}",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            ensure_parent_dir(dest_host)
        except ValueError as exc:
            print(f"{RED}✗{RESET} {exc}", file=sys.stderr)
            sys.exit(1)

        if dest_host.exists():
            confirm_overwrite(str(dest_host), volume_root=False, force=args.force)
            overwrite = True

        run_transfer(
            mode="export",
            kind=kind,
            docker_volume=docker_volume,
            rel=rel,
            host_mount=dest_host.parent,
            host_name=dest_host.name,
            overwrite=overwrite,
            uid=uid,
            gid=uid,
        )
        print(f"{GREEN}✓{RESET} Exported {docker_volume}:{rel} → {dest_host}")
        return

    if not volume_path_is_dir(docker_volume, rel):
        print(
            f"{RED}✗{RESET} Source path does not exist in the volume "
            f"or is not a directory or file: {service}:{volume_key}:{rel}",
            file=sys.stderr,
        )
        sys.exit(1)

    loc = f"{service}:{volume_key}:{rel}"
    print(f"{BLUE}⚙{RESET} Exporting volume → host")
    print(f"{GREY}◦{RESET} Host: {host_path}")
    print(f"{GREY}◦{RESET} Spec: {loc}")
    print(f"{GREY}◦{RESET} Docker volume: {docker_volume}")
    print(f"{GREY}◦{RESET} Volume mount: {mount}")

    if host_path.exists():
        if not host_path.is_dir():
            print(
                f"{RED}✗{RESET} Cannot export a directory onto a host file: {host_path}",
                file=sys.stderr,
            )
            sys.exit(1)
        confirm_overwrite(str(host_path), volume_root=False, force=args.force)
        overwrite = True
    else:
        host_path.mkdir(parents=True, exist_ok=True)

    run_transfer(
        mode="export",
        kind="dir",
        docker_volume=docker_volume,
        rel=rel,
        host_mount=host_path,
        host_name=".",
        overwrite=overwrite,
        uid=uid,
        gid=uid,
    )
    print(f"{GREEN}✓{RESET} Exported {docker_volume}:{rel} → {host_path}")


if __name__ == "__main__":
    main()
