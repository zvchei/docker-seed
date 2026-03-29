#!/usr/bin/env python3
"""
DockerSeed v2 — Generates Dockerfile and docker-compose.yaml
by combining feature templates defined in templates/.

Each entry in containers.json may set "enabled": false to skip generating
that service (defaults to true when omitted).
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

SCRIPT_DIR: Path = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = SCRIPT_DIR / "templates"
SERVICES_DIR: Path = SCRIPT_DIR / "services"
CONTAINERS_FILE: Path = SCRIPT_DIR / "containers.json"

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


def generate_compose(name: str, merged: Merged) -> str:
    indent: str = "    "
    lines: list[str] = ["services:"]
    lines.append(f"{indent}{name}:")
    lines.append(f"{indent}{indent}hostname: ${{PROJECT}}-{name}")
    lines.append(f"{indent}{indent}extends:")
    lines.append(f"{indent}{indent}{indent}file: ../../common/docker-compose.yaml")
    lines.append(f"{indent}{indent}{indent}service: {merged.get('base_service', 'base')}")

    if merged.get("init"):
        lines.append(f"{indent}{indent}init: true")

    vol_lines: list[str] = [f"- root:/home/${{CONTAINER_USER}}/${{PROJECT}}"]
    for vol_name, vol_path in merged.get("volumes", {}).items():
        vol_lines.append(f"- {vol_name}:/home/${{CONTAINER_USER}}/{vol_path}")

    lines.append(f"{indent}{indent}volumes:")
    for vl in vol_lines:
        lines.append(f"{indent}{indent}{indent}{vl}")

    lines.append(f"{indent}{indent}build:")
    lines.append(f"{indent}{indent}{indent}context: .")
    lines.append(f"{indent}{indent}{indent}additional_contexts:")
    lines.append(f"{indent}{indent}{indent}{indent}localhost/base: service:base")

    for ctx_name, ctx_path in merged.get("contexts", {}).items():
        lines.append(f"{indent}{indent}{indent}{indent}{ctx_name}: {ctx_path}")

    build_args: dict[str, str] = merged.get("build_args", {})
    if build_args:
        lines.append(f"{indent}{indent}{indent}args:")
        for arg_name, compose_value in build_args.items():
            lines.append(f"{indent}{indent}{indent}{indent}{arg_name}: {compose_value}")

    if merged.get("ports"):
        lines.append(f"{indent}{indent}ports:")
        for port in merged["ports"]:
            lines.append(f"{indent}{indent}{indent}- {port}")

    env_vars: dict[str, str] = merged.get("env_vars", {})
    if env_vars:
        lines.append(f"{indent}{indent}environment:")
        for var_name, var_value in env_vars.items():
            lines.append(f"{indent}{indent}{indent}{var_name}: {var_value}")

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

    generated: list[str] = []

    for container in containers:
        name: str = container["name"]
        if not container.get("enabled", True):
            print(f"\n\033[33m⊘\033[0m  Skipping {name} (enabled: false)")
            continue

        template_names: list[str] = container["templates"]
        resolved_names = resolve_templates(template_names)

        print(f"\n\033[34m⚙\033[0m  Generating {name} from: {', '.join(resolved_names)}")

        templates: list[Template] = [load_template(t) for t in resolved_names]
        merged: Merged = merge_templates(templates)

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

        if container.get("profile"):
            merged["base_service"] = container["profile"]

        if container.get("networks"):
            merged["networks"] = container["networks"]

        if container.get("env_vars"):
            merged.setdefault("env_vars", {}).update(container["env_vars"])

        service_dir: Path = SERVICES_DIR / name
        if service_dir.exists():
            shutil.rmtree(service_dir)
        service_dir.mkdir(parents=True)

        dockerfile_content: str = generate_dockerfile(merged)
        (service_dir / "Dockerfile").write_text(dockerfile_content)

        compose_content: str = generate_compose(name, merged)
        (service_dir / "docker-compose.yaml").write_text(compose_content)

        print(f"\033[32m✓\033[0m  Generated services/{name}/")
        generated.append(name)

    print(f"\n\033[32m✓\033[0m  Done. Generated {len(generated)} container(s).")
    print(f"\nRun \033[1m./build.sh\033[0m to build the services.")


if __name__ == "__main__":
    main()
