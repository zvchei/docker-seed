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
    ds.py add-template [service [reference]]
                                      insert a template, @abstract service or
                                      service:<name> before the last of a service's
                                      templates, so its command is kept; with
                                      fewer arguments, list the possible values
    ds.py extend <service> <new-service> [template] [--command "cmd args..."]
                                      add a service that reuses <service>'s image, with
                                      `main` set to template (default: <new-service>),
                                      or `cmd` set to the split --command line

<cmd> is the service's resolved command: the compose `command:` if set,
otherwise the image's CMD. The entrypoint is kept as is. Without extra
arguments the service starts with its normal command. `shell` ignores <cmd>
and runs the given command (or bash) in a new container of the service.
`--serve` passes `--service-ports` to `docker compose run`, binding the
service's published ports as in `up`. `add` refuses to touch containers.json
when any of the recipe's service names is already defined there.
`add-template` refuses references that are unknown, already listed, or would
make a service include itself, and services that use `extends` (they reuse
their parent's image, so templates would have no effect). `extend` warns
when the template is not built into the parent's image, since its program
would be missing.

Works in any directory where `docker compose` finds the project.
"""

import json
import os
import re
import shlex
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


_DECODER = json.JSONDecoder()
_WHITESPACE = re.compile(r"\s*")


def _skip(text: str, i: int) -> int:
    return _WHITESPACE.match(text, i).end()  # type: ignore[union-attr]


def _array_items(text: str, start: int) -> list[tuple[int, int]]:
    """Returns the (start, end) spans of the items of the JSON array at text[start]."""
    spans: list[tuple[int, int]] = []
    i = _skip(text, start + 1)
    while text[i] != "]":
        _, end = _DECODER.raw_decode(text, i)
        spans.append((i, end))
        i = _skip(text, end)
        if text[i] == ",":
            i = _skip(text, i + 1)
    return spans


def _object_members(text: str, start: int) -> dict[str, tuple[int, int, int]]:
    """Returns key → (key_start, value_start, value_end) for the JSON object at text[start]."""
    members: dict[str, tuple[int, int, int]] = {}
    i = _skip(text, start + 1)
    while text[i] != "}":
        key, key_end = _DECODER.raw_decode(text, i)
        value_start = _skip(text, _skip(text, key_end) + 1)
        _, value_end = _DECODER.raw_decode(text, value_start)
        members[key] = (i, value_start, value_end)
        i = _skip(text, value_end)
        if text[i] == ",":
            i = _skip(text, i + 1)
    return members


def _line_indent(text: str, i: int) -> str | None:
    """Returns the indentation before text[i], or None if other text precedes it on its line."""
    line_start = text.rfind("\n", 0, i) + 1
    indent = text[line_start:i]
    return indent if not indent.strip() else None


def _insert_template(text: str, index: int, reference: str) -> str:
    """Inserts reference before the last of the index-th container's templates, keeping the layout."""
    start, _ = _array_items(text, _skip(text, 0))[index]
    members = _object_members(text, start)
    item = json.dumps(reference)

    if "templates" in members:
        _, value_start, value_end = members["templates"]
        items = _array_items(text, value_start)
        if not items:
            return f"{text[:value_start]}[{item}]{text[value_end:]}"
        last_start, _ = items[-1]
        indent = _line_indent(text, last_start)
        separator = f",\n{indent}" if indent is not None and "\n" in text[value_start:value_end] else ", "
        return f"{text[:last_start]}{item}{separator}{text[last_start:]}"

    # Place a new templates list after "enabled" (or "name"), as the recipes do.
    anchor = "enabled" if "enabled" in members else "name"
    key_start, _, value_end = members[anchor]
    indent = _line_indent(text, key_start)
    separator = f",\n{indent}" if indent is not None else ", "
    return f'{text[:value_end]}{separator}"templates": [{item}]{text[value_end:]}'


def _reference_target(reference: str) -> tuple[str, str]:
    """Splits a templates[] entry into ('template' | 'service', name), as sow reads it."""
    qualifier, separator, name = reference.partition(":")
    if separator:
        return ("service", name) if qualifier == "service" and name else ("invalid", reference)
    return ("service", reference) if reference.startswith("@") else ("template", reference)


def _templates_dirs(containers_file: Path) -> list[Path]:
    return [containers_file.parent / "templates", REPO_DIR / "templates"]


def _template_names(containers_file: Path) -> list[str]:
    return sorted({
        d.name
        for directory in _templates_dirs(containers_file) if directory.is_dir()
        for d in directory.iterdir() if (d / "template.json").is_file()
    })


def _referenced_services(name: str, by_name: dict[str, dict[str, Any]]) -> set[str]:
    """Returns every service that name pulls in through templates and extends."""
    seen: set[str] = set()
    pending = [name]
    while pending:
        container = by_name.get(pending.pop())
        if container is None:
            continue
        refs = [container["extends"]] if container.get("extends") else []
        for reference in container.get("templates", []):
            kind, target = _reference_target(reference)
            if kind == "service":
                refs.append(target)
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                pending.append(ref)
    return seen


def _reference_choices(service: str, containers: list[dict[str, Any]], containers_file: Path) -> list[str]:
    choices = _template_names(containers_file)
    for c in containers:
        name: str = c["name"]
        if name != service:
            choices.append(name if name.startswith("@") else f"service:{name}")
    return choices


def _check_reference(
    service: str,
    reference: str,
    current: list[Any],
    by_name: dict[str, dict[str, Any]],
    containers_file: Path,
) -> None:
    """Dies unless reference can be appended to service's current templates."""
    kind, target = _reference_target(reference)
    if kind == "invalid":
        _die(f"invalid reference '{reference}'; use '<template>', '@<abstract>' or 'service:<name>'")
    if kind == "template" and target not in _template_names(containers_file):
        hint = f"; did you mean 'service:{target}'?" if target in by_name else ""
        _die(f"template '{target}' does not exist{hint}")
    if kind == "service":
        if target == service:
            _die(f"service '{service}' cannot include itself")
        if target not in by_name:
            _die(f"service '{target}' does not exist in {containers_file}")
        if service in _referenced_services(target, by_name):
            _die(f"'{reference}' already includes '{service}'; adding it would create a cycle")
    if (kind, target) in {_reference_target(r) for r in current if isinstance(r, str)}:
        _die(f"service '{service}' already lists '{reference}'")


def add_template(args: list[str]) -> None:
    containers_file, text, containers = _load_containers()
    by_name = {c["name"]: c for c in containers}
    if not args:
        print("\n".join(c["name"] for c in containers if not c.get("extends")))
        return
    service = args[0]
    container = by_name.get(service)
    if container is None:
        _die(f"service '{service}' does not exist in {containers_file}")
        return
    if len(args) == 1:
        print("\n".join(_reference_choices(service, containers, containers_file)))
        return
    if len(args) > 2:
        _die("add-template takes a service name and one reference")
    reference = args[1]

    if container.get("extends"):
        _die(
            f"service '{service}' extends '{container['extends']}' and reuses its image, "
            f"so templates would have no effect; use \"templates\": [\"service:{container['extends']}\", ...] "
            "instead of extends"
        )
    current = container.get("templates", [])
    if not isinstance(current, list):
        _die(f"service '{service}' field 'templates' must be a list")

    _check_reference(service, reference, current, by_name, containers_file)

    index = containers.index(container)
    # Insert before the last entry, which usually provides the command (last cmd wins).
    container["templates"] = [*current[:-1], reference, *current[-1:]]
    _write_containers(containers_file, _insert_template(text, index, reference), containers)
    print(f"Added '{reference}' to '{service}' templates in {containers_file}; run sow and harvest to rebuild.")


SERVICE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.]*")


def _template_manifest(name: str, containers_file: Path) -> dict[str, Any]:
    for directory in _templates_dirs(containers_file):
        manifest = directory / name / "template.json"
        if manifest.is_file():
            return json.loads(manifest.read_text())
    return {}


def _image_templates(name: str, by_name: dict[str, dict[str, Any]], containers_file: Path) -> set[str]:
    """Returns the templates, with their requires, built into the image of service name."""
    found: set[str] = set()
    seen: set[str] = set()
    pending_services = [name]
    while pending_services:
        container = by_name.get(pending_services.pop())
        if container is None or container["name"] in seen:
            continue
        seen.add(container["name"])
        if container.get("extends"):
            pending_services.append(container["extends"])
            continue
        pending_templates: list[str] = []
        for reference in container.get("templates", []):
            kind, target = _reference_target(reference)
            if kind == "service":
                pending_services.append(target)
            elif kind == "template":
                pending_templates.append(target)
        while pending_templates:
            template = pending_templates.pop()
            if template not in found:
                found.add(template)
                pending_templates.extend(_template_manifest(template, containers_file).get("requires", []))
    return found


def extend(args: list[str]) -> None:
    command: list[str] | None = None
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--command" or arg.startswith("--command="):
            if arg == "--command":
                i += 1
                if i == len(args):
                    _die("--command needs a command line")
                arg = args[i]
            else:
                arg = arg.removeprefix("--command=")
            try:
                command = shlex.split(arg)
            except ValueError as e:
                _die(f"cannot parse --command: {e}")
            if not command:
                _die("--command needs a command line")
        else:
            positional.append(arg)
        i += 1

    containers_file, text, containers = _load_containers()
    by_name = {c["name"]: c for c in containers}
    if not positional:
        print("\n".join(name for name in by_name if not name.startswith("@")))
        return
    parent = positional[0]
    if parent not in by_name:
        _die(f"service '{parent}' does not exist in {containers_file}")
    if parent.startswith("@"):
        _die(f"abstract service '{parent}' cannot be extended; use ds add-template instead")
    if len(positional) == 1:
        print("\n".join(sorted(_image_templates(parent, by_name, containers_file))))
        return
    if len(positional) > 3:
        _die("extend takes a service, a new service name and an optional template")
    name = positional[1]
    if name in by_name:
        _die(f"service '{name}' already exists in {containers_file}")
    if not SERVICE_NAME.fullmatch(name):
        _die(f"invalid service name '{name}'; use letters, digits, '_' and '.' (not '-')")

    entry: dict[str, Any] = {"name": name, "enabled": True, "extends": parent}
    if command is not None:
        if len(positional) == 3:
            _die("give either a template or --command, not both")
        entry["cmd"] = command
        entrypoints = {
            t: e
            for t in sorted(_image_templates(parent, by_name, containers_file))
            if (e := _template_manifest(t, containers_file).get("entrypoint"))
        }
        for template, entrypoint in entrypoints.items():
            print(
                f"note: template '{template}' in '{parent}'s image sets entrypoint "
                f"{json.dumps(entrypoint)}; if it is in effect, --command is passed to it as arguments",
                file=sys.stderr,
            )
    else:
        template = positional[2] if len(positional) == 3 else name
        if template not in _template_names(containers_file):
            _die(f"template '{template}' does not exist; name one, or use --command")
        if template not in _image_templates(parent, by_name, containers_file):
            print(
                f"warning: template '{template}' is not built into '{parent}'s image, "
                "so its command may not be installed there",
                file=sys.stderr,
            )
        entry["main"] = template

    lines = [f"        {json.dumps(k)}: {json.dumps(v)}" for k, v in entry.items()]
    entry_text = "[\n    {\n" + ",\n".join(lines) + "\n    }\n]"
    _write_containers(containers_file, _append_entries(text, entry_text), containers + [entry])
    how = f"cmd {json.dumps(command)}" if command is not None else f"main '{entry['main']}'"
    print(f"Added '{name}' extending '{parent}' with {how} to {containers_file}; run sow and harvest.")


ACTIONS: dict[str, Callable[[str, list[str]], None]] = {
    "run": run,
    "up": up,
}


def main() -> None:
    if sys.argv[1:2] == ["list"]:
        list_services()
        return
    if sys.argv[1:2] == ["extend"]:
        extend(sys.argv[2:])
        return
    if sys.argv[1:2] == ["add-template"]:
        add_template(sys.argv[2:])
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
