#!/usr/bin/env python3
"""Replace main.py's _TRACE with a harvested tape. Overlays stay in place.

    python3 scripts/assemble_tape.py tapes/ep100453695_seat0.json
    python3 scripts/assemble_tape.py tapes/ep100453695_seat0.json --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tape_lib import encode_blob, fingerprint, load_actions, summarize  # noqa: E402

TRACE_START = "_TRACE = json.loads(zlib.decompress(base64.b85decode("
TRACE_END = ")).decode(\"utf-8\"))"


def _doc_line(meta: dict) -> str:
    episode = meta.get("episode_id", "unknown")
    seat = meta.get("seat", "?")
    bank = meta.get("bank", "?")
    fp = meta.get("fingerprint", "")
    return (
        f'"""Harvested episode {episode} seat {seat}: bank {bank}, '
        f'fp {fp}. Field tape swapped; C94/weed/market overlays kept."""'
    )


def inject(source: str, blob: str, docstring: str) -> str:
    start = source.find(TRACE_START)
    if start < 0:
        raise SystemExit("FAIL: _TRACE assignment not found in main.py")
    end = source.find(TRACE_END, start)
    if end < 0:
        raise SystemExit("FAIL: _TRACE terminator not found in main.py")
    end += len(TRACE_END)
    replacement = f"{TRACE_START}\n    '{blob}'\n{TRACE_END}"
    out = source[:start] + replacement + source[end:]
    out = re.sub(r'^""".*?"""', docstring, out, count=1, flags=re.S)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tape", type=Path)
    p.add_argument("--main", type=Path, default=ROOT / "agents" / "c95" / "main.py")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    actions, meta = load_actions(args.tape)
    blob = encode_blob(actions)
    meta.setdefault("fingerprint", fingerprint(actions))
    text = args.main.read_text(encoding="utf-8")
    updated = inject(text, blob, _doc_line(meta))
    if args.dry_run:
        print(f"would write {args.main}  blob={len(blob)} chars  fp={meta['fingerprint']}")
        print(f"summary {summarize(actions)}")
        return 0
    args.main.write_text(updated, encoding="utf-8")
    print(f"updated {args.main}")
    print(f"episode={meta.get('episode_id')} seat={meta.get('seat')} bank={meta.get('bank')}")
    print(f"fp={meta.get('fingerprint')} blob={len(blob)} chars")
    print(f"summary {summarize(actions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
