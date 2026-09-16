#!/usr/bin/env python3
"""Run main.py against a built-in opponent. Same CLI-first loop as ARC local eval."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kaggle_environments import make  # noqa: E402

from main import agent  # noqa: E402


def play(opponent: str, steps: int, debug: bool) -> tuple[float | None, float | None]:
    env = make("kaggriculture", configuration={"episodeSteps": steps}, debug=debug)
    env.run([agent, opponent])
    last = env.steps[-1]
    return last[0]["reward"], last[1]["reward"]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--opponent", default="random", choices=["random", "pass", "starter"])
    p.add_argument("--steps", type=int, default=720)
    p.add_argument("--games", type=int, default=1)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    wins = 0
    for i in range(args.games):
        ours, theirs = play(args.opponent, args.steps, args.debug)
        ours_n = ours if ours is not None else 0.0
        theirs_n = theirs if theirs is not None else 0.0
        if ours_n > theirs_n:
            wins += 1
            outcome = "win"
        elif ours_n < theirs_n:
            outcome = "loss"
        else:
            outcome = "tie"
        print(f"game {i + 1}: {outcome}  us={ours}  opp={theirs}")
    if args.games > 1:
        print(f"wins {wins}/{args.games}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
