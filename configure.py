#!/usr/bin/env python3
"""
configure.py — Interactively review and update .env variables.

Operates on the current working directory by default:
    ./configure.py
    ./configure.py /path/to/.env

till.py and harvest.py call configure_env after seeding .env from the
repo's .env.template when needed. Run this script directly to walk
through an existing .env again.
"""

import shutil
import sys
from pathlib import Path

SCRIPT_DIR: Path = Path(__file__).resolve().parent
WORK_DIR: Path = Path.cwd()
ENV_FILE: Path = WORK_DIR / ".env"
ENV_TMP: Path = WORK_DIR / ".env.tmp"
ENV_TEMPLATE: Path = SCRIPT_DIR / ".env.template"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
GREY = "\033[37m"
RESET = "\033[0m"


def seed_env_from_template(env_file: Path, template: Path | None = None) -> None:
    """Copy .env.template to env_file. Caller must ensure env_file is missing."""
    if template is None:
        template = ENV_TEMPLATE
    if not template.is_file():
        print(f"{RED}✗{RESET} Env template not found at {template}")
        sys.exit(1)
    shutil.copyfile(template, env_file)
    print(f"{GREEN}✓{RESET} Created {env_file} from {template.name}")


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
        print(
            f"{YELLOW}⚠{RESET}  Duplicate variable '{name}' in .env — "
            "only the first occurrence will be used."
        )

    return raw_lines, ordered_vars


def configure_env(env_file: Path, env_tmp: Path | None = None) -> None:
    """Interactively prompt for each variable in env_file and save updates."""
    if env_tmp is None:
        env_tmp = env_file.parent / ".env.tmp"

    if not env_file.exists():
        print(f"{RED}✗{RESET} {env_file} not found.")
        print(
            f"{GREY}◦{RESET} Run till.py or harvest.py to create .env "
            "from .env.template first."
        )
        sys.exit(1)

    print("Setting up project variables:\n")

    raw_lines, env_vars = _parse_env(env_file)

    if not env_vars:
        print(f"{GREY}◦{RESET} No variables found in .env — skipping.")
        return

    var_names = list(env_vars.keys())

    while True:
        for name in var_names:
            current = env_vars[name]
            new_value = input(
                f"{YELLOW}?{RESET} Enter value for {name} [{current}]: "
            ).strip()
            if new_value:
                env_vars[name] = new_value

        print("\nCurrent configuration:\n")
        for name in var_names:
            print(f"{GREY}◦{RESET} {name}={env_vars[name]}")
        print()

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


def main() -> None:
    if len(sys.argv) > 2:
        print(f"Usage: {sys.argv[0]} [.env]", file=sys.stderr)
        sys.exit(1)

    env_file = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else ENV_FILE
    configure_env(env_file)


if __name__ == "__main__":
    main()
