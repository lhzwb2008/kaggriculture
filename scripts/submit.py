#!/usr/bin/env python3
"""Submit the agent via Kaggle CLI. Whole pipeline stays on CLI, not the web editor."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = "kaggriculture"


def find_kaggle(explicit: str = "") -> str:
    candidates = []
    if explicit:
        candidates.append(explicit)
    env = os.environ.get("KAGGLE")
    if env:
        candidates.append(env)
    which = shutil.which("kaggle")
    if which:
        candidates.append(which)
    venv = ROOT / ".venv" / "bin" / "kaggle"
    if venv.is_file():
        candidates.append(str(venv))
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    raise SystemExit("FAIL: kaggle CLI not found (pip install kaggle && kaggle auth login)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-m", "--message", default="wheat loop baseline")
    p.add_argument("-f", "--file", type=Path, default=ROOT / "main.py")
    p.add_argument("--kaggle", default="")
    p.add_argument("--status", action="store_true", help="list recent submissions")
    p.add_argument("--leaderboard", action="store_true")
    args = p.parse_args()
    kaggle = find_kaggle(args.kaggle)

    if args.leaderboard:
        return subprocess.call([kaggle, "competitions", "leaderboard", COMP, "-s"])
    if args.status:
        return subprocess.call([kaggle, "competitions", "submissions", COMP])

    path = args.file.resolve()
    if not path.exists():
        raise SystemExit(f"FAIL: {path} missing")
    cmd = [kaggle, "competitions", "submit", COMP, "-f", str(path), "-m", args.message]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
