#!/usr/bin/env python3
"""
ds.py — Starts a service with extra arguments appended to its command.

    ds.py run <service> [args...]     docker compose run --rm <service> <cmd> <args...>
    ds.py up  <service> [args...]     docker compose up <service>, with <cmd> <args...>
    ds.py shell [--serve] <service> [command [args...]]
                                      docker compose run --rm <service> <command> <args...>,
                                      or a bash shell when no command is given
    ds.py list                        enabled services from the nearest containers.json
    ds.py add [recipe]                append a recipe's services to the nearest
                                      containers.json, or list recipes when none is given

<cmd> is the service's resolved command: the compose `command:` if set,
otherwise the image's CMD. The entrypoint is kept as is. Without extra
arguments the service starts with its normal command. `shell` ignores <cmd>
and runs the given command (or bash) in a new container of the service.
`--serve` passes `--service-ports` to `docker compose run`, binding the
service's published ports as in `up`. `add` refuses to touch containers.json
when any of the recipe's service names is already defined there.

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

REPO_DIR: Path = Path(__file__).resolve().parent
RECIPES_DIR: Path = REPO_DIR / "recipes"

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


def shell(args: list[str]) -> None:
    serve = False
    while args and args[0] == "--serve":
        serve = True
        args = args[1:]
    if not args:
        _die("shell requires a service name")
    service, *command = args
    extra = ["--service-ports"] if serve else []
    os.execvp("docker", ["docker", "compose", "run", "--rm", *extra, service, *(command or [SHELL])])


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


def recipes() -> list[str]:
    return sorted(d.name for d in RECIPES_DIR.iterdir() if (d / "containers.json").is_file())


def _append_entries(text: str, recipe_text: str) -> str:
    """Appends the entries of the recipe's JSON array to the one in text, keeping both layouts."""
    body = text.rstrip()
    inner = recipe_text.strip()[1:-1].strip("\n").rstrip()
    if not body.endswith("]") or not inner:
        return ""
    head = body[:-1].rstrip()
    separator = "\n" if head.endswith("[") else ",\n"
    return f"{head}{separator}{inner}\n]\n"


def _load_containers() -> tuple[Path, str, list[dict[str, Any]]]:
    containers_file = _containers_file()
    if containers_file is None:
        _die("no containers.json found in this directory or its parents; run till first")
    text = containers_file.read_text()
    try:
        return containers_file, text, json.loads(text)
    except json.JSONDecodeError as e:
        _die(f"{containers_file}: {e}")
        raise


def _write_containers(path: Path, updated: str, expected: list[dict[str, Any]]) -> None:
    """Writes the text-edited file, or a plain re-dump if the edit went wrong."""
    try:
        valid = json.loads(updated) == expected
    except json.JSONDecodeError:
        valid = False
    path.write_text(updated if valid else json.dumps(expected, indent=4) + "\n")


def add(args: list[str]) -> None:
    if not args:
        print("\n".join(recipes()))
        return
    recipe = args[0]
    recipe_file = RECIPES_DIR / recipe / "containers.json"
    if "/" in recipe or not recipe_file.is_file():
        _die(f"unknown recipe '{recipe}'; available: {', '.join(recipes())}")
    containers_file, text, containers = _load_containers()
    recipe_text = recipe_file.read_text()
    entries: list[dict[str, Any]] = json.loads(recipe_text)

    existing = {c["name"] for c in containers}
    clashes = [e["name"] for e in entries if e["name"] in existing]
    if clashes:
        _die(
            f"{containers_file} already defines {', '.join(clashes)}; "
            f"recipe '{recipe}' not added"
        )

    _write_containers(containers_file, _append_entries(text, recipe_text), containers + entries)

    names = ", ".join(e["name"] for e in entries)
    print(f"Added recipe '{recipe}' ({names}) to {containers_file}")
    print(f"See {RECIPES_DIR / recipe / 'README.md'} for its extra steps, then run sow and harvest.")


ACTIONS: dict[str, Callable[[str, list[str]], None]] = {
    "run": run,
    "up": up,
}


def main() -> None:
    if sys.argv[1:2] == ["list"]:
        list_services()
        return
    if sys.argv[1:2] == ["add"]:
        add(sys.argv[2:])
        return
    if sys.argv[1:2] == ["shell"]:
        shell(sys.argv[2:])
        return
    if len(sys.argv) < 3 or sys.argv[1] not in ACTIONS:
        print(__doc__.strip(), file=sys.stderr)
        sys.exit(2)
    ACTIONS[sys.argv[1]](sys.argv[2], sys.argv[3:])


if __name__ == "__main__":
    main()
