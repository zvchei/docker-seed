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
from typing import Any, TypedDict

SCRIPT_DIR: Path = Path(__file__).resolve().parent
TEMPLATES_DIR: Path = SCRIPT_DIR / "templates"
SERVICES_DIR: Path = SCRIPT_DIR / "services"
CONTAINERS_FILE: Path = SCRIPT_DIR / "containers.json"
SERVICES_LIST: Path = SCRIPT_DIR / "services.list"

type Manifest = dict[str, Any]
type Fragment = tuple[str, str]
type Merged = dict[str, Any]


class Template(TypedDict):
    name: str
    manifest: Manifest
    root_dockerfile: str
    user_dockerfile: str


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


def merge_templates(templates: list[Template]) -> Merged:
    apt_packages: list[str] = []
    root_fragments: list[Fragment] = []
    user_fragments: list[Fragment] = []
    volumes: dict[str, str] = {}
    ports: list[str] = []
    cmd: list[str] | None = None
    build_args: dict[str, str] = {}

    for tpl in templates:
        m: Manifest = tpl["manifest"]

        for pkg in m.get("apt_packages", []):
            if pkg not in apt_packages:
                apt_packages.append(pkg)

        if tpl["root_dockerfile"].strip():
            root_fragments.append((tpl["name"], tpl["root_dockerfile"]))

        if tpl["user_dockerfile"].strip():
            user_fragments.append((tpl["name"], tpl["user_dockerfile"]))

        for vol_name, vol_path in m.get("volumes", {}).items():
            volumes[vol_name] = vol_path

        ports.extend(m.get("ports", []))

        if "cmd" in m:
            cmd = m["cmd"]

        for arg_name, arg_value in m.get("build_args", {}).items():
            build_args[arg_name] = str(arg_value)

    return {
        "apt_packages": apt_packages,
        "root_fragments": root_fragments,
        "user_fragments": user_fragments,
        "volumes": volumes,
        "ports": ports,
        "cmd": cmd,
        "build_args": build_args,
    }


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

    if merged["apt_packages"]:
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
    lines.append("WORKDIR $HOME")

    for name, fragment in merged["user_fragments"]:
        lines.append("")
        lines.append(f"# --- {name} ---")
        lines.append(fragment.rstrip())

    lines.append("")
    lines.append("WORKDIR /home/${USER}/${PROJECT}")

    if merged["cmd"]:
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
    lines.append(f"{indent}{indent}{indent}file: ../common/docker-compose.yaml")
    lines.append(f"{indent}{indent}{indent}service: base")

    vol_lines: list[str] = [f"- root:/home/${{CONTAINER_USER}}/${{PROJECT}}"]
    for vol_name, vol_path in merged["volumes"].items():
        vol_lines.append(f"- {vol_name}:/home/${{CONTAINER_USER}}/{vol_path}")

    lines.append(f"{indent}{indent}volumes:")
    for vl in vol_lines:
        lines.append(f"{indent}{indent}{indent}{vl}")

    lines.append(f"{indent}{indent}build:")
    lines.append(f"{indent}{indent}{indent}context: .")
    lines.append(f"{indent}{indent}{indent}additional_contexts:")
    lines.append(f"{indent}{indent}{indent}{indent}localhost/base: service:base")

    build_args: dict[str, str] = merged.get("build_args", {})
    if build_args:
        lines.append(f"{indent}{indent}{indent}args:")
        for arg_name, compose_value in build_args.items():
            lines.append(f"{indent}{indent}{indent}{indent}{arg_name}: {compose_value}")

    if merged["ports"]:
        lines.append(f"{indent}{indent}ports:")
        for port in merged["ports"]:
            lines.append(f"{indent}{indent}{indent}- {port}")

    lines.append("")
    lines.append("volumes:")
    lines.append(f"{indent}root:")
    for vol_name in merged["volumes"]:
        lines.append(f"{indent}{vol_name}:")

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

        print(f"\n\033[34m⚙\033[0m  Generating {name} from: {', '.join(template_names)}")

        templates: list[Template] = [load_template(t) for t in template_names]
        merged: Merged = merge_templates(templates)

        container_main = container.get("main")
        if container_main is not None:
            tpl_manifest = load_template(container_main)["manifest"]
            merged["cmd"] = tpl_manifest.get("cmd")

        container_cmd = container.get("cmd")
        if container_cmd is not None:
            if isinstance(container_cmd, list):
                merged["cmd"] = container_cmd
            else:
                print(f"Error: 'cmd' must be a command array (list of strings)")
                sys.exit(1)

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

    existing_services: set[str] = set()
    if SERVICES_LIST.exists():
        for line in SERVICES_LIST.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                existing_services.add(stripped)

    with open(SERVICES_LIST, "a") as f:
        for name in generated:
            if name in existing_services:
                print(f"  Service '{name}' already in services.list, skipping.")
            else:
                f.write(f"{name}\n")
                print(f"\033[32m✓\033[0m  Added '{name}' to services.list.")

    print(f"\nRun \033[1m./build.sh\033[0m to build the services.")


if __name__ == "__main__":
    main()
