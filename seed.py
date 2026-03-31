#!/usr/bin/env python3
"""
DockerSeed v2 — Generates Dockerfile and docker-compose.yaml
by combining feature templates defined in templates/.

Each entry in containers.json may set "enabled": false to skip generating
that service (defaults to true when omitted).
"""

import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

SCRIPT_DIR: Path = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = SCRIPT_DIR / "templates"
SERVICES_DIR: Path = SCRIPT_DIR / "services"
CONTAINERS_FILE: Path = SCRIPT_DIR / "containers.json"
ASSETS_FILE: Path = SCRIPT_DIR / "assets.json"

type Manifest = dict[str, Any]
type Fragment = tuple[str, str]
type Merged = dict[str, Any]

# Manifest keys that carry no mergeable data:
NON_MANIFEST_KEYS: frozenset[str] = frozenset({"description", "requires"})

# Fields where overwriting is mandatory instead of accumulating or merging:
LAST_WINS_ARRAY_FIELDS: frozenset[str] = frozenset({"cmd", "entrypoint"})


class Template(TypedDict):
    name: str
    manifest: Manifest
    root_dockerfile: str
    user_dockerfile: str


def merge_field(existing: Any, value: Any, key: str = "", method: str = "merge") -> Any:
    if method not in {"merge", "replace"}:
        print(f"Error: unknown merge method '{method}'")
        sys.exit(1)

    if (
        existing is not None
        and value is not None
        and type(existing) is not type(value)
    ):
        print(
            f"Error: type mismatch for field '{key}' across templates "
            f"(got {type(existing).__name__} and {type(value).__name__})"
        )
        sys.exit(1)

    if existing is None:
        if isinstance(value, list):
            return cast(list[Any], value.copy())
        if isinstance(value, dict):
            return cast(dict[str, Any], value.copy())
        return value

    if method == "replace":
        if isinstance(value, list):
            return cast(list[Any], value.copy())
        if isinstance(value, dict):
            return cast(dict[str, Any], value.copy())
        return value

    if isinstance(value, list):
        result: list[Any] = list(cast(list[Any], existing))
        for item in cast(list[Any], value):
            if item not in result:
                result.append(item)
        return result

    if isinstance(value, dict):
        result_dict: dict[str, Any] = dict(cast(dict[str, Any], existing))
        result_dict.update(cast(dict[str, Any], value))
        return result_dict

    return value


def load_template(name: str) -> Template:
    tpl_dir: Path = TEMPLATES_DIR / name
    manifest_path: Path = tpl_dir / "template.json"
    if not manifest_path.exists():
        print(f"Error: template '{name}' not found at {tpl_dir}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest: Manifest = json.load(f)

    root_dockerfile: str = ""
    root_path: Path = tpl_dir / "root.Dockerfile"
    if root_path.exists():
        root_dockerfile = root_path.read_text()

    user_dockerfile: str = ""
    user_path: Path = tpl_dir / "user.Dockerfile"
    if user_path.exists():
        user_dockerfile = user_path.read_text()

    return {
        "name": name,
        "manifest": manifest,
        "root_dockerfile": root_dockerfile,
        "user_dockerfile": user_dockerfile,
    }


def resolve_templates(names: list[str], _chain: list[str] | None = None) -> list[str]:
    """Return template names in dependency-resolved order."""
    if _chain is None:
        _chain = []

    resolved: list[str] = []

    for name in names:
        if name in _chain:
            print(f"Error: circular dependency detected: {' -> '.join(_chain)} -> {name}")
            sys.exit(1)

        manifest_path = TEMPLATES_DIR / name / "template.json"
        if not manifest_path.exists():
            print(f"Error: template '{name}' not found at {TEMPLATES_DIR / name}")
            sys.exit(1)

        with open(manifest_path) as f:
            manifest: Manifest = json.load(f)

        requires: list[str] = manifest.get("requires", [])
        if requires:
            sub_resolved = resolve_templates(requires, _chain + [name])
            for req in sub_resolved:
                if req not in resolved:
                    resolved.append(req)

        if name not in resolved:
            resolved.append(name)

    return resolved


def merge_templates(templates: list[Template]) -> Merged:
    root_fragments: list[Fragment] = []
    user_fragments: list[Fragment] = []
    merged: Merged = {}

    for tpl in templates:
        m: Manifest = tpl["manifest"]

        if tpl["root_dockerfile"].strip():
            root_fragments.append((tpl["name"], tpl["root_dockerfile"]))

        if tpl["user_dockerfile"].strip():
            user_fragments.append((tpl["name"], tpl["user_dockerfile"]))

        for key, value in m.items():
            if key in NON_MANIFEST_KEYS:
                continue

            existing = merged.get(key)

            method: str = "replace" if key in LAST_WINS_ARRAY_FIELDS else "merge"
            merged[key] = merge_field(existing, value, key=key, method=method)

    merged["root_fragments"] = root_fragments
    merged["user_fragments"] = user_fragments
    return merged


def generate_dockerfile(merged: Merged) -> str:
    lines: list[str] = [
        "FROM localhost/base",
        "",
        "ARG USER",
        "ARG PROJECT",
        "ENV HOME=/home/${USER}",
    ]

    for arg_name in merged.get("build_args", {}):
        lines.append(f"ARG {arg_name}")
        lines.append(f"ENV {arg_name}=${{{arg_name}}}")

    lines.append("")
    lines.append("USER root")

    if merged.get("apt_packages"):
        pkgs: str = " ".join(merged["apt_packages"])
        lines.append(f"RUN apt-get -y update && \\")
        lines.append(f"    apt-get -y install {pkgs} && \\")
        lines.append(f"    apt-get -y clean && rm -rf /var/lib/apt/lists/*")

    for name, fragment in merged["root_fragments"]:
        lines.append("")
        lines.append(f"# --- {name} ---")
        lines.append(fragment.rstrip())

    lines.append("")
    lines.append("USER ${USER}")

    volumes: dict[str, str] = merged.get("volumes", {})
    if merged["user_fragments"] or volumes:
        lines.append("WORKDIR $HOME")

    if volumes:
        lines.append("")
        paths = [f"$HOME/{path}" for path in volumes.values()]
        if len(paths) == 1:
            lines.append(f"RUN mkdir -p {paths[0]}")
        else:
            lines.append("RUN mkdir -p \\")
            for path in paths[:-1]:
                lines.append(f"    {path} \\")
            lines.append(f"    {paths[-1]}")

    for name, fragment in merged["user_fragments"]:
        lines.append("")
        lines.append(f"# --- {name} ---")
        lines.append(fragment.rstrip())

    lines.append("")
    lines.append("WORKDIR $HOME/${PROJECT}")

    if merged.get("entrypoint"):
        entrypoint_json: str = json.dumps(merged["entrypoint"])
        lines.append("")
        lines.append(f"ENTRYPOINT {entrypoint_json}")

    if merged.get("cmd"):
        cmd_json: str = json.dumps(merged["cmd"])
        lines.append("")
        lines.append(f"CMD {cmd_json}")

    lines.append("")
    return "\n".join(lines)


def validate_extends(containers: list[dict[str, Any]]) -> None:
    """Validate all 'extends' references: targets must exist and no cycles."""
    names: set[str] = {c["name"] for c in containers}

    def check(name: str, chain: list[str]) -> None:
        if name in chain:
            print(f"Error: circular 'extends' detected: {' -> '.join(chain + [name])}")
            sys.exit(1)
        container = next((c for c in containers if c["name"] == name), None)
        if container is None:
            return
        parent = container.get("extends")
        if parent:
            if parent not in names:
                print(
                    f"Error: container '{name}' extends '{parent}', "
                    f"which does not exist in containers.json."
                )
                sys.exit(1)
            check(parent, chain + [name])

    for container in containers:
        if container.get("extends"):
            check(container["name"], [])


def build_merged_for_container(
    container: dict[str, Any],
    all_containers: list[dict[str, Any]],
    _chain: list[str] | None = None,
) -> Merged:
    """Return the fully-resolved merged dict for a container, handling 'extends' chains."""
    if _chain is None:
        _chain = []

    name: str = container["name"]
    if name in _chain:
        print(f"Error: circular 'extends' detected: {' -> '.join(_chain + [name])}")
        sys.exit(1)

    parent_name: str | None = container.get("extends")
    if parent_name is not None:
        parent = next((c for c in all_containers if c["name"] == parent_name), None)
        if parent is None:
            print(f"Error: container '{name}' extends '{parent_name}', which does not exist.")
            sys.exit(1)

        parent_merged = build_merged_for_container(parent, all_containers, _chain + [name])
        merged: Merged = copy.deepcopy(parent_merged)
        merged["extended_service"] = parent_name

        if container.get("ports") is not None:
            merged["ports"] = container["ports"]
        if container.get("workdir"):
            merged["workdir"] = container["workdir"]
        if container.get("init"):
            merged["init"] = True
        if container.get("interactive"):
            merged["interactive"] = True
        if container.get("networks") is not None:
            merged["networks"] = container["networks"]
        if container.get("network_mode") is not None:
            merged["network_mode"] = container["network_mode"]
        if container.get("restart") is not None:
            merged["restart"] = container["restart"]
        if container.get("env_vars"):
            merged.setdefault("env_vars", {}).update(container["env_vars"])
        if container.get("cmd") is not None:
            if isinstance(container["cmd"], list):
                merged["cmd"] = container["cmd"]
            else:
                print(f"Error: 'cmd' must be a command array (list of strings)")
                sys.exit(1)

        container_main = container.get("main")
        if container_main is not None:
            tpl_manifest = load_template(container_main)["manifest"]
            merged["cmd"] = tpl_manifest.get("cmd")
            merged["entrypoint"] = tpl_manifest.get("entrypoint")

        return merged

    # Regular container: template-based resolution.
    template_names: list[str] = container.get("templates", [])
    resolved_names = resolve_templates(template_names)
    templates_list: list[Template] = [load_template(t) for t in resolved_names]
    merged = merge_templates(templates_list)

    container_main = container.get("main")
    if container_main is not None:
        tpl_manifest = load_template(container_main)["manifest"]
        merged["cmd"] = tpl_manifest.get("cmd")
        merged["entrypoint"] = tpl_manifest.get("entrypoint")

    container_entrypoint = container.get("entrypoint")
    if container_entrypoint is not None:
        if isinstance(container_entrypoint, list):
            merged["entrypoint"] = container_entrypoint
        else:
            print(f"Error: 'entrypoint' must be a command array (list of strings)")
            sys.exit(1)

    container_cmd = container.get("cmd")
    if container_cmd is not None:
        if isinstance(container_cmd, list):
            merged["cmd"] = container_cmd
        else:
            print(f"Error: 'cmd' must be a command array (list of strings)")
            sys.exit(1)

    container_ports = container.get("ports")
    if container_ports is not None:
        if isinstance(container_ports, list):
            merged["ports"] = container_ports
        else:
            print(f"Error: 'ports' must be a list of port mappings (list of strings)")
            sys.exit(1)

    if container.get("init"):
        merged["init"] = True

    if container.get("interactive"):
        merged["interactive"] = True

    if container.get("workdir"):
        merged["workdir"] = container["workdir"]

    if container.get("profile"):
        merged["base_service"] = container["profile"]

    if container.get("networks"):
        merged["networks"] = container["networks"]

    if container.get("network_mode") is not None:
        merged["network_mode"] = container["network_mode"]

    if container.get("restart") is not None:
        merged["restart"] = container["restart"]

    if container.get("env_vars"):
        merged.setdefault("env_vars", {}).update(container["env_vars"])

    return merged


def generate_compose(name: str, merged: Merged) -> str:
    indent: str = "    "
    lines: list[str] = ["services:"]
    lines.append(f"{indent}{name}:")
    lines.append(f"{indent}{indent}hostname: ${{PROJECT}}-{name}")

    # Security settings inlined in every service (self-contained, no reliance on common/base).
    lines.append(f'{indent}{indent}cap_drop: ["all"]')
    lines.append(f"{indent}{indent}security_opt:")
    lines.append(f"{indent}{indent}{indent}- no-new-privileges")
    lines.append(f"{indent}{indent}read_only: true")
    lines.append(f"{indent}{indent}tmpfs:")
    lines.append(f"{indent}{indent}{indent}- /tmp:noexec,nosuid,nodev,mode=1777")
    lines.append(f"{indent}{indent}user: ${{CONTAINER_USER_ID}}:${{CONTAINER_USER_ID}}")

    if merged.get("init"):
        lines.append(f"{indent}{indent}init: true")

    if merged.get("interactive"):
        lines.append(f"{indent}{indent}tty: true")
        lines.append(f"{indent}{indent}stdin_open: true")

    if merged.get("workdir"):
        lines.append(f"{indent}{indent}working_dir: {merged['workdir']}")

    if merged.get("base_service") == "gpu":
        lines.append(f"{indent}{indent}deploy:")
        lines.append(f"{indent}{indent}{indent}resources:")
        lines.append(f"{indent}{indent}{indent}{indent}reservations:")
        lines.append(f"{indent}{indent}{indent}{indent}{indent}devices:")
        lines.append(f"{indent}{indent}{indent}{indent}{indent}{indent}- driver: nvidia")
        lines.append(f"{indent}{indent}{indent}{indent}{indent}{indent}  capabilities: [gpu]")
        lines.append(f"{indent}{indent}{indent}{indent}{indent}{indent}  count: all")

    vol_lines: list[str] = [f"- root:/home/${{CONTAINER_USER}}/${{PROJECT}}"]
    for vol_name, vol_path in merged.get("volumes", {}).items():
        vol_lines.append(f"- {vol_name}:/home/${{CONTAINER_USER}}/{vol_path}")

    lines.append(f"{indent}{indent}volumes:")
    for vl in vol_lines:
        lines.append(f"{indent}{indent}{indent}{vl}")

    extended_service: str | None = merged.get("extended_service")
    if extended_service:
        lines.append(f"{indent}{indent}image: ${{COMPOSE_PROJECT_NAME}}-{extended_service}")
        lines.append(f"{indent}{indent}pull_policy: never")
        if merged.get("cmd"):
            cmd_json: str = json.dumps(merged["cmd"])
            lines.append(f"{indent}{indent}command: {cmd_json}")
    else:
        lines.append(f"{indent}{indent}build:")
        lines.append(f"{indent}{indent}{indent}context: .")
        lines.append(f"{indent}{indent}{indent}additional_contexts:")
        lines.append(f"{indent}{indent}{indent}{indent}localhost/base: service:base")

        if merged.get("assets"):
            lines.append(f"{indent}{indent}{indent}{indent}assets: ../../assets")

        for ctx_name, ctx_path in merged.get("contexts", {}).items():
            lines.append(f"{indent}{indent}{indent}{indent}{ctx_name}: {ctx_path}")

        standard_build_args: frozenset[str] = frozenset(
            {"USER", "USER_ID", "PROJECT", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_NAME"}
        )
        lines.append(f"{indent}{indent}{indent}args:")
        lines.append(f"{indent}{indent}{indent}{indent}USER: ${{CONTAINER_USER}}")
        lines.append(f"{indent}{indent}{indent}{indent}USER_ID: ${{CONTAINER_USER_ID}}")
        lines.append(f"{indent}{indent}{indent}{indent}PROJECT: ${{PROJECT}}")
        lines.append(f"{indent}{indent}{indent}{indent}GIT_AUTHOR_EMAIL: ${{GIT_AUTHOR_EMAIL}}")
        lines.append(f"{indent}{indent}{indent}{indent}GIT_AUTHOR_NAME: ${{GIT_AUTHOR_NAME}}")

        for arg_name, compose_value in merged.get("build_args", {}).items():
            if arg_name not in standard_build_args:
                lines.append(f"{indent}{indent}{indent}{indent}{arg_name}: {compose_value}")

        lines.append(f"{indent}{indent}pull_policy: never")

    if merged.get("ports"):
        lines.append(f"{indent}{indent}ports:")
        for port in merged["ports"]:
            lines.append(f"{indent}{indent}{indent}- {port}")

    env_vars: dict[str, str] = merged.get("env_vars", {})
    if env_vars:
        lines.append(f"{indent}{indent}environment:")
        for var_name, var_value in env_vars.items():
            lines.append(f"{indent}{indent}{indent}{var_name}: {var_value}")

    network_mode: str | None = merged.get("network_mode")
    if network_mode:
        lines.append(f"{indent}{indent}network_mode: {network_mode}")

    restart: str | None = merged.get("restart")
    if restart:
        lines.append(f"{indent}{indent}restart: {restart}")

    networks: list[dict[str, Any]] = merged.get("networks", [])
    if networks:
        lines.append(f"{indent}{indent}networks:")
        for net in networks:
            lines.append(f"{indent}{indent}{indent}- {net['name']}")

    lines.append("")
    lines.append("volumes:")
    lines.append(f"{indent}root:")
    for vol_name in merged.get("volumes", {}):
        lines.append(f"{indent}{vol_name}:")

    if networks:
        lines.append("")
        lines.append("networks:")
        for net in networks:
            lines.append(f"{indent}{net['name']}:")
            if net.get("external"):
                lines.append(f"{indent}{indent}external: true")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    if not CONTAINERS_FILE.exists():
        print(f"Error: {CONTAINERS_FILE} not found.")
        sys.exit(1)

    with open(CONTAINERS_FILE) as f:
        containers: list[dict[str, Any]] = json.load(f)

    if not containers:
        print("No containers defined in containers.json.")
        return

    validate_extends(containers)

    generated: list[str] = []
    all_assets: list[dict[str, str]] = []

    for container in containers:
        name: str = container["name"]
        if not container.get("enabled", True):
            print(f"\n\033[33m⊘\033[0m  Skipping {name} (enabled: false)")
            continue

        is_extends: bool = bool(container.get("extends"))

        if is_extends:
            print(f"\n\033[34m⚙\033[0m  Generating {name} (extends: {container['extends']})")
        else:
            resolved_names = resolve_templates(container.get("templates", []))
            label = ", ".join(resolved_names) if resolved_names else "(no templates)"
            print(f"\n\033[34m⚙\033[0m  Generating {name} from: {label}")

        merged: Merged = build_merged_for_container(container, containers)

        service_dir: Path = SERVICES_DIR / name
        if service_dir.exists():
            shutil.rmtree(service_dir)
        service_dir.mkdir(parents=True)

        if not is_extends:
            dockerfile_content: str = generate_dockerfile(merged)
            (service_dir / "Dockerfile").write_text(dockerfile_content)

        compose_content: str = generate_compose(name, merged)
        (service_dir / "docker-compose.yaml").write_text(compose_content)

        for asset in merged.get("assets", []):
            if asset not in all_assets:
                all_assets.append(asset)

        print(f"\033[32m✓\033[0m  Generated services/{name}/")
        generated.append(name)

    print(f"\n\033[32m✓\033[0m  Done. Generated {len(generated)} container(s).\n")

    if all_assets:
        with open(ASSETS_FILE, "w") as f:
            json.dump(all_assets, f, indent=2)
        print(f"\033[32m✓\033[0m  Generated assets.json with {len(all_assets)} asset(s).")

        for asset in all_assets:
            print(f"  \033[34m⬇\033[0m  {asset['filename']}")
            print(f"     ↳ {asset['url']}")

        print(f"\nRun \033[1m./grow.py\033[0m to download assets before building.")
    elif ASSETS_FILE.exists():
        ASSETS_FILE.unlink()

    print(f"Run \033[1m./harvest.sh\033[0m to build the services.")


if __name__ == "__main__":
    main()
