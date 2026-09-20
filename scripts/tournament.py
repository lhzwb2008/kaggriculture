#!/usr/bin/env python3
"""Local head-to-head of harvested tapes (no overlays).

    python3 scripts/tournament.py tapes/a.json tapes/b.json --games 4
    python3 scripts/tournament.py tapes/*.json --games 2
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tape_lib import PASS_ACTION, load_actions, obs_step  # noqa: E402


def make_player(actions: list[dict]):
    def agent(obs, config=None):
        step = min(obs_step(obs), len(actions) - 1)
        return copy.deepcopy(actions[step] if step >= 0 else PASS_ACTION)

    return agent


def play(left, right, steps: int, seed: int | None, debug: bool):
    from kaggle_environments import make

    config = {"episodeSteps": steps}
    if seed is not None:
        config["seed"] = seed
    env = make("kaggriculture", configuration=config, debug=debug)
    env.run([left, right])
    last = env.steps[-1]
    return last[0]["reward"], last[1]["reward"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tapes", nargs="+", type=Path)
    p.add_argument("--games", type=int, default=2)
    p.add_argument("--steps", type=int, default=720)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    loaded = []
    for path in args.tapes:
        actions, meta = load_actions(path)
        loaded.append((path, actions, meta))
    if len(loaded) < 2:
        raise SystemExit("need at least two tapes")

    try:
        from kaggle_environments import make  # noqa: F401
    except ImportError:
        print("FAIL: kaggle-environments not installed")
        return 1

    wins = {path: 0 for path, _, _ in loaded}
    games = 0
    for i, (left_path, left_actions, _) in enumerate(loaded):
        for right_path, right_actions, _ in loaded[i + 1 :]:
            for game in range(args.games):
                seed = None if args.seed is None else args.seed + games
                try:
                    ours, theirs = play(
                        make_player(left_actions),
                        make_player(right_actions),
                        args.steps,
                        seed,
                        args.debug,
                    )
                except Exception as exc:
                    print(f"FAIL: local env could not run ({exc})")
                    return 1
                games += 1
                left_n = ours if ours is not None else 0.0
                right_n = theirs if theirs is not None else 0.0
                if left_n > right_n:
                    wins[left_path] += 1
                    outcome = f"{left_path.name} win"
                elif left_n < right_n:
                    wins[right_path] += 1
                    outcome = f"{right_path.name} win"
                else:
                    outcome = "tie"
                print(f"{left_path.name} vs {right_path.name}  game {game + 1}: {outcome}  {ours} / {theirs}")

    print("wins:")
    for path, _, _ in loaded:
        print(f"  {path.name}: {wins[path]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
