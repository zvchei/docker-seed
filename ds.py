#!/usr/bin/env python3
"""
ds.py — Starts a service with extra arguments appended to its command.

    ds.py run <service> [args...]     docker compose run --rm <service> <cmd> <args...>
    ds.py up  <service> [args...]     docker compose up <service>, with <cmd> <args...>
    ds.py shell <service> [command [args...]]
                                      docker compose run --rm <service> <command> <args...>,
                                      or a bash shell when no command is given
    ds.py list                        enabled services from the nearest containers.json

<cmd> is the service's resolved command: the compose `command:` if set,
otherwise the image's CMD. The entrypoint is kept as is. Without extra
arguments the service starts with its normal command. `shell` ignores <cmd>
and runs the given command (or bash) in a new container of the service.

Works in any directory where `docker compose` finds the project.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

# Default compose file names, in the order docker compose looks for them.
COMPOSE_FILES: tuple[str, ...] = (
    "compose.yaml",
    "compose.yml",
    "docker-compose.yml",
    "docker-compose.yaml",
)
OVERRIDE_FILES: tuple[str, ...] = (
    "compose.override.yaml",
    "compose.override.yml",
    "docker-compose.override.yml",
    "docker-compose.override.yaml",
)

SHELL: str = "bash"

RED = "\033[31m"
RESET = "\033[0m"


def _die(message: str) -> None:
    print(f"{RED}✗{RESET} ds: {message}", file=sys.stderr)
    sys.exit(1)


def _project_config(service: str) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json", service],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _die(result.stderr.strip() or f"cannot read compose config for '{service}'")
    return json.loads(result.stdout)


def _image_cmd(image: str) -> list[str]:
    result = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{json .Config.Cmd}}", image],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _die(f"image '{image}' not found; build it first (docker compose build)")
    return json.loads(result.stdout) or []


def _escaped_command(config: dict[str, Any], service: str) -> list[str]:
    """Returns the service command with `$` escaped as `$$`, as compose config prints it."""
    svc: dict[str, Any] = config["services"][service]
    command: list[str] | str | None = svc.get("command")
    if isinstance(command, str):
        _die(f"service '{service}' uses a string command; use the list form")
    if command is not None:
        return command
    image: str = svc.get("image") or f"{config['name']}-{service}"
    return [arg.replace("$", "$$") for arg in _image_cmd(image)]


def _containers_file() -> Path | None:
    """Returns the nearest containers.json in this directory or its parents."""
    directory = Path.cwd()
    for candidate in (directory, *directory.parents):
        if (candidate / "containers.json").is_file():
            return candidate / "containers.json"
    return None


def _compose_files() -> list[str]:
    """Returns the -f arguments docker compose would use on its own."""
    if compose_file := os.environ.get("COMPOSE_FILE"):
        separator = os.environ.get("COMPOSE_PATH_SEPARATOR", os.pathsep)
        return [arg for f in compose_file.split(separator) for arg in ("-f", f)]
    directory = Path.cwd()
    for candidate in (directory, *directory.parents):
        for name in COMPOSE_FILES:
            if (candidate / name).is_file():
                files = [candidate / name]
                files += [candidate / o for o in OVERRIDE_FILES if (candidate / o).is_file()][:1]
                return [arg for f in files for arg in ("-f", str(f))]
    _die("no compose file found in this directory or its parents")
    return []


def run(service: str, args: list[str]) -> None:
    command: list[str] = []
    if args:
        config = _project_config(service)
        command = [a.replace("$$", "$") for a in _escaped_command(config, service)] + args
    os.execvp("docker", ["docker", "compose", "run", "--rm", service, *command])


def up(service: str, args: list[str]) -> None:
    if not args:
        os.execvp("docker", ["docker", "compose", "up", service])

    config = _project_config(service)
    command = _escaped_command(config, service) + [a.replace("$", "$$") for a in args]
    files = _compose_files()  # passing -f disables the default lookup, so name them again

    with tempfile.NamedTemporaryFile("w", prefix="ds-", suffix=".yaml", delete=False) as f:
        json.dump({"services": {service: {"command": command}}}, f)
        override = f.name
    try:
        # Let docker compose handle Ctrl+C; we only wait and clean up.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        result = subprocess.run(["docker", "compose", *files, "-f", override, "up", service])
    finally:
        os.unlink(override)
    sys.exit(result.returncode)


def shell(service: str, args: list[str]) -> None:
    os.execvp("docker", ["docker", "compose", "run", "--rm", service, *(args or [SHELL])])


def list_services() -> None:
    containers_file = _containers_file()
    if containers_file is None:
        _die("no containers.json found in this directory or its parents")
    with open(containers_file) as f:
        containers: list[dict[str, Any]] = json.load(f)
    for container in containers:
        name: str = container["name"]
        if container.get("enabled", True) and not name.startswith("@"):
            print(name)


ACTIONS: dict[str, Callable[[str, list[str]], None]] = {
    "run": run,
    "up": up,
    "shell": shell,
}


def main() -> None:
    if sys.argv[1:2] == ["list"]:
        list_services()
        return
    if len(sys.argv) < 3 or sys.argv[1] not in ACTIONS:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    ACTIONS[sys.argv[1]](sys.argv[2], sys.argv[3:])


if __name__ == "__main__":
    main()
