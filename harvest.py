#!/usr/bin/env python3
"""
harvest.py — Orchestrates the DockerSeed stack after seed.py has run.

Steps:
  1. Read enabled services from containers.json
  2. Regenerate the root docker-compose.yaml (include stanza)
  3. Interactively review and update .env variables
  4. Optionally run `docker-compose build`
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR: Path = Path(__file__).resolve().parent
SERVICES_DIR: Path = SCRIPT_DIR / "services"
CONTAINERS_FILE: Path = SCRIPT_DIR / "containers.json"
ENV_FILE: Path = SCRIPT_DIR / ".env"
ENV_TMP: Path = SCRIPT_DIR / ".env.tmp"
DOCKER_COMPOSE_FILE: Path = SCRIPT_DIR / "docker-compose.yaml"

# ANSI colour helpers
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
GREY = "\033[37m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Step 1 — service discovery
# ---------------------------------------------------------------------------


def get_enabled_services(containers_file: Path) -> list[str]:
    with open(containers_file) as f:
        containers: list[dict[str, Any]] = json.load(f)
    return [c["name"] for c in containers if c.get("enabled", True)]


# ---------------------------------------------------------------------------
# Step 2 — root docker-compose.yaml generation
# ---------------------------------------------------------------------------


def generate_root_compose(script_dir: Path, service_names: list[str]) -> None:
    print(f"\n{BLUE}⚙{RESET} Generating docker-compose.yaml from the list of services:")

    lines = ["include:\n", "  - common/docker-compose.yaml\n"]
    for name in service_names:
        lines.append(f"  - services/{name}/docker-compose.yaml\n")
        print(f"\t{GREY}◦{RESET} {name}")

    (script_dir / "docker-compose.yaml").write_text("".join(lines))
    print(f"{GREEN}✓{RESET} Done.")


# ---------------------------------------------------------------------------
# Step 3 — interactive .env configuration
# ---------------------------------------------------------------------------


def _parse_env(env_file: Path) -> tuple[list[str], dict[str, str]]:
    """Return (raw_lines, ordered_vars) from .env.

    raw_lines preserves every line verbatim (including comments/blanks).
    ordered_vars maps var_name → current_value in file order (no duplicates).
    """
    raw_lines: list[str] = []
    ordered_vars: dict[str, str] = {}

    if not env_file.exists():
        return raw_lines, ordered_vars

    duplicates: list[str] = []
    with open(env_file) as f:
        for line in f:
            raw_lines.append(line)
            stripped = line.rstrip("\n")
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name, _, value = stripped.partition("=")
                if name in ordered_vars:
                    duplicates.append(name)
                else:
                    ordered_vars[name] = value

    for name in duplicates:
        print(f"{YELLOW}⚠{RESET}  Duplicate variable '{name}' in .env — only the first occurrence will be used.")

    return raw_lines, ordered_vars


def configure_env(env_file: Path, env_tmp: Path) -> None:
    print("Setting up project variables:\n")

    raw_lines, env_vars = _parse_env(env_file)

    if not env_vars:
        print(f"{GREY}◦{RESET} No variables found in .env — skipping.")
        return

    var_names = list(env_vars.keys())

    while True:
        # Prompt for each variable
        for name in var_names:
            current = env_vars[name]
            new_value = input(f"{YELLOW}?{RESET} Enter value for {name} [{current}]: ").strip()
            if new_value:
                env_vars[name] = new_value

        # Show summary
        print("\nCurrent configuration:\n")
        for name in var_names:
            print(f"{GREY}◦{RESET} {name}={env_vars[name]}")
        print()

        # Confirmation loop
        confirmed = False
        while True:
            answer = input("Is this correct? [y/n]: ").strip().lower()
            if answer in ("y", "yes"):
                confirmed = True
                break
            if answer in ("n", "no"):
                print(f"\n{YELLOW}↻{RESET}\n")
                break

        if confirmed:
            break

    # Write updated values, preserving comments and blank lines
    with open(env_tmp, "w") as f:
        for line in raw_lines:
            stripped = line.rstrip("\n")
            if stripped and not stripped.startswith("#") and "=" in stripped:
                name = stripped.partition("=")[0]
                f.write(f"{name}={env_vars.get(name, stripped.partition('=')[2])}\n")
            else:
                f.write(line)

    shutil.copy(env_tmp, env_file)
    env_tmp.unlink(missing_ok=True)

    print(f"{GREEN}✓{RESET} Environment variables saved.")


# ---------------------------------------------------------------------------
# Step 4 — optional docker-compose build
# ---------------------------------------------------------------------------


def prompt_docker_build() -> None:
    answer = input("\nDo you want to proceed with `docker-compose build`? [Y/n]: ").strip()
    print()
    if answer == "" or answer.lower() in ("y", "yes"):
        dc = shutil.which("docker-compose")
        if dc is None:
            print(f"{YELLOW}⚠{RESET} `docker-compose` is not installed or not in PATH.")
            sys.exit(1)
        subprocess.run([dc, "build"], check=True)
    else:
        print("Use `docker-compose build` to manually create the service images.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print("Starting build...")

    service_names = get_enabled_services(CONTAINERS_FILE)

    generate_root_compose(SCRIPT_DIR, service_names)

    print()
    configure_env(ENV_FILE, ENV_TMP)

    prompt_docker_build()


if __name__ == "__main__":
    main()
