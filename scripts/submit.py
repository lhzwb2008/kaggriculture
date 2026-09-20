#!/usr/bin/env python3
"""Submit the agent via Kaggle CLI. Auth is token/file based, never a browser login."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tape_lib import kaggle_cmd, prepare_kaggle_auth  # noqa: E402

COMP = "kaggriculture"
BUNDLE = ("main.py", "observation.py", "model.json", "actions.json")


def pack_bundle(root: Path = ROOT) -> Path:
    missing = [name for name in BUNDLE if not (root / name).is_file()]
    if missing:
        raise SystemExit(f"FAIL: missing {missing}")
    dest = root / "submission.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        for name in BUNDLE:
            tar.add(root / name, arcname=name)
    return dest


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("-m", "--message", default="shop-router-0908 public mosaic")
    p.add_argument("-f", "--file", type=Path, default=None)
    p.add_argument("--kaggle", default="")
    p.add_argument("--status", action="store_true", help="list recent submissions")
    p.add_argument("--leaderboard", action="store_true")
    p.add_argument("--pack-only", action="store_true", help="write submission.tar.gz and stop")
    args = p.parse_args()

    if args.pack_only:
        dest = pack_bundle(ROOT)
        print(f"wrote {dest} ({dest.stat().st_size} bytes)")
        return 0

    prepare_kaggle_auth(ROOT)
    kaggle = kaggle_cmd(args.kaggle)

    if args.leaderboard:
        return subprocess.call([*kaggle, "competitions", "leaderboard", COMP, "-s"])
    if args.status:
        return subprocess.call([*kaggle, "competitions", "submissions", COMP])

    path = args.file.resolve() if args.file else pack_bundle(ROOT)
    if not path.exists():
        raise SystemExit(f"FAIL: {path} missing")
    cmd = [*kaggle, "competitions", "submit", COMP, "-f", str(path), "-m", args.message]
    print(" ".join(cmd))
    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
