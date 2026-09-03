#!/usr/bin/env python3
"""
harvest.py — Orchestrates the DockerSeed stack after sow.py has run.

Operates on the current working directory (same as cleanup.py / sow.py).

Steps:
  1. Sync common/ from the DockerSeed repo into cwd when needed
  2. Read enabled services from ./containers.json
  3. Regenerate the root ./docker-compose.yaml (include stanza)
  4. If .env is missing, seed it from .env.template and run configure.py
  5. Optionally run `docker-compose build`
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import configure

SCRIPT_DIR: Path = Path(__file__).resolve().parent
WORK_DIR: Path = Path.cwd()
SERVICES_DIR: Path = WORK_DIR / "services"
CONTAINERS_FILE: Path = WORK_DIR / "containers.json"
ENV_FILE: Path = WORK_DIR / ".env"
DOCKER_COMPOSE_FILE: Path = WORK_DIR / "docker-compose.yaml"
COMMON_SRC: Path = SCRIPT_DIR / "common"
COMMON_DST: Path = WORK_DIR / "common"

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
    return [
        c["name"]
        for c in containers
        if c.get("enabled", True) and not c["name"].startswith("@")
    ]


# ---------------------------------------------------------------------------
# Step 2 — root docker-compose.yaml generation
# ---------------------------------------------------------------------------


def sync_common() -> None:
    """Copy repo common/ into the working directory when they differ."""
    if COMMON_SRC.resolve() == COMMON_DST.resolve():
        return
    if not COMMON_SRC.is_dir():
        print(f"{RED}✗{RESET} Shared common directory not found at {COMMON_SRC}")
        sys.exit(1)
    if COMMON_DST.exists():
        shutil.rmtree(COMMON_DST)
    shutil.copytree(COMMON_SRC, COMMON_DST)
    print(f"{GREEN}✓{RESET} Synced common/ into {COMMON_DST}")


def generate_root_compose(work_dir: Path, service_names: list[str]) -> None:
    print(f"\n{BLUE}⚙{RESET} Generating docker-compose.yaml from the list of services:")

    lines = ["include:\n", "  - common/docker-compose.yaml\n"]
    for name in service_names:
        lines.append(f"  - services/{name}/docker-compose.yaml\n")
        print(f"\t{GREY}◦{RESET} {name}")

    (work_dir / "docker-compose.yaml").write_text("".join(lines))
    print(f"{GREEN}✓{RESET} Done.")


# ---------------------------------------------------------------------------
# Step 3 — ensure .env (configure only when newly seeded)
# ---------------------------------------------------------------------------


def ensure_env() -> None:
    """Seed .env from template when missing, then configure; skip if present."""
    if ENV_FILE.exists():
        print(f"{GREY}◦{RESET} Using existing {ENV_FILE}")
        return

    print()
    configure.seed_env_from_template(ENV_FILE)
    configure.configure_env(ENV_FILE)


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

    sync_common()

    service_names = get_enabled_services(CONTAINERS_FILE)

    generate_root_compose(WORK_DIR, service_names)

    ensure_env()

    prompt_docker_build()


if __name__ == "__main__":
    main()
