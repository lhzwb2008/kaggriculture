#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import main as router  # noqa: E402


def _farm():
    empty = {"kind": "EMPTY"}
    return {
        "money": 1000,
        "farmer": [4, 4],
        "hands": [],
        "tiles": [[empty] * 10 for _ in range(10)],
        "unlocked_quadrants": [0],
        "hires_today": 0,
    }


def _obs(day, hour, shops=()):
    step = day * 24 + hour
    return {
        "step": step,
        "day": day,
        "hour": hour,
        "player": 0,
        "farms": [_farm(), _farm()],
        "town": {"unlocked_shops": list(shops)},
        "market": {"inventory": {"EGG": 10000}, "prices": {}},
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
    }


class ShopRouterTests(unittest.TestCase):
    def setUp(self):
        router._ROUTER = None

    def test_loads_four_complete_tapes(self):
        agent = router.Router(ROOT)
        self.assertEqual(len(agent.tapes), 4)
        self.assertTrue(all(len(tape) == 719 for tape in agent.tapes))
        self.assertEqual(agent.default, 0)

    def test_opening_matches_default_tape(self):
        action = router.agent(_obs(0, 0))
        self.assertEqual(action["market"][0], ["BUY_PRODUCT", "WHEAT", 13])
        self.assertEqual(router._ROUTER.active, 0)

    def test_day6_yarn_store_switches_tape(self):
        router.agent(_obs(0, 0))
        router.agent(_obs(6, 0, shops=["YARN_STORE"]))
        self.assertEqual(router._ROUTER.active, 1)

    def test_day6_without_yarn_keeps_default(self):
        router.agent(_obs(0, 0))
        router.agent(_obs(6, 0, shops=["BAKERY"]))
        self.assertEqual(router._ROUTER.active, 0)

    def test_full_season_smoke_with_yarn_and_egg_fork(self):
        router._ROUTER = None
        last = None
        for step in range(720):
            day, hour = divmod(step, 24)
            egg = 9000 if step >= 648 else 10000
            obs = _obs(day, hour, shops=["YARN_STORE"] if step >= 144 else [])
            obs["market"]["inventory"]["EGG"] = egg
            last = router.agent(obs)
            self.assertIn("farmer", last)
            self.assertIn("market", last)
        self.assertEqual(last, {"farmer": ["PASS"], "hands": [], "market": []})
        self.assertEqual(router._ROUTER.active, 2)
        self.assertEqual([row["step"] for row in router._ROUTER.decisions], [144, 648])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
