#!/usr/bin/env python3
"""
grow.py — Fetches all assets listed in assets.json into the assets/ directory.
Run this after seed.py and before build.sh / docker-compose build.
Files already present in assets/ are skipped.
"""

import json
import sys
import urllib.request
from pathlib import Path
from typing import Callable

SCRIPT_DIR: Path = Path(__file__).resolve().parent
ASSETS_FILE: Path = SCRIPT_DIR / "assets.json"
ASSETS_DIR: Path = SCRIPT_DIR / "assets"


def _make_progress() -> Callable[[int, int, int], None]:
    last_pct: list[int] = [-1]

    def _progress(block_count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        downloaded = min(block_count * block_size, total_size)
        pct = downloaded * 100 // total_size
        if pct == last_pct[0]:
            return
        last_pct[0] = pct
        bar_width = 30
        filled = pct * bar_width // 100
        bar = "█" * filled + "░" * (bar_width - filled)
        print(f"\r     [{bar}] {pct:3d}%", end="", flush=True)
        if pct >= 100:
            print()

    return _progress


def main() -> None:
    if not ASSETS_FILE.exists():
        print("No assets.json found — nothing to fetch.")
        return

    with open(ASSETS_FILE) as f:
        assets: list[dict[str, str]] = json.load(f)

    if not assets:
        print("assets.json is empty — nothing to fetch.")
        return

    ASSETS_DIR.mkdir(exist_ok=True)

    errors: int = 0
    for item in assets:
        url: str = item["url"]
        filename: str = item["filename"]
        dest: Path = ASSETS_DIR / filename

        if dest.exists():
            print(f"  \033[37m◦\033[0m  {filename} (already present, skipping)")
            continue

        print(f"  \033[34m⬇\033[0m  {filename}")
        print(f"     ↳ {url}")
        try:
            urllib.request.urlretrieve(url, dest, reporthook=_make_progress())
            print(f"  \033[32m✓\033[0m  {filename}")
        except Exception as e:
            print(f"  \033[31m✗\033[0m  Failed to fetch {filename}: {e}")
            if dest.exists():
                dest.unlink()
            errors += 1

    if errors:
        print(f"\n\033[31m✗\033[0m  {errors} asset(s) failed to download.")
        sys.exit(1)
    else:
        print(f"\n\033[32m✓\033[0m  All assets ready.")


if __name__ == "__main__":
    main()
