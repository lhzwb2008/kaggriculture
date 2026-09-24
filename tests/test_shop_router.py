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
    return {
        "step": day * 24 + hour,
        "day": day,
        "hour": hour,
        "player": 0,
        "farms": [_farm(), _farm()],
        "town": {"unlocked_shops": list(shops)},
        "market": {"inventory": {"EGG": 10000}, "prices": {"WOOL": 200, "WHEAT": 25}},
        "private": {"shed": {}, "seeds": {}, "inventories": [{}]},
    }


class ShopRouterTests(unittest.TestCase):
    def setUp(self):
        router._POLICY = None

    def test_loads_thirteen_complete_tapes(self):
        policy = router.Policy(ROOT)
        self.assertEqual(len(policy.tapes), 13)
        self.assertTrue(all(len(tape) == 719 for tape in policy.tapes))

    def test_opening_matches_default_tape(self):
        action = router.agent(_obs(0, 0))
        self.assertEqual(action["market"][0], ["BUY_PRODUCT", "WHEAT", 13])
        self.assertEqual(router._POLICY.players[0].plan, 0)

    def test_day6_routes_on_the_first_two_shops(self):
        router.agent(_obs(6, 0, shops=["BAKERY", "YARN_STORE"]))
        self.assertEqual(router._POLICY.players[0].plan, 3)
        router._POLICY = None
        router.agent(_obs(6, 0, shops=["YARN_STORE", "YARN_STORE"]))
        self.assertEqual(router._POLICY.players[0].plan, 12)
        router._POLICY = None
        router.agent(_obs(6, 0, shops=["BAKERY", "PIZZA_SHOP"]))
        self.assertEqual(router._POLICY.players[0].plan, 0)

    def test_day27_switches_every_route_to_the_shared_ending(self):
        router.agent(_obs(6, 0, shops=["YARN_STORE", "YARN_STORE"]))
        router.agent(_obs(27, 0, shops=["YARN_STORE", "YARN_STORE"]))
        self.assertEqual(router._POLICY.players[0].plan, 2)

    def test_weed_blocks_planting_for_this_worker_only(self):
        state = router.DayState()
        view_obs = _obs(3, 2)
        view_obs["farms"][0]["tiles"][4][4] = {"kind": "WEED"}
        view = router.FarmView(view_obs)
        action = {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": []}
        router.repair_weeds(action, view, state, 3 * 24 + 2)
        self.assertEqual(action["farmer"], ["DIG"])
        self.assertEqual(list(state.queues[0]), [["PLANT", "WHEAT"]])

    def test_pulled_sales_follow_opening_buys_in_value_order(self):
        tape = [{"market": []}, {"market": []}, {
            "market": [["SELL", "WOOL", 4], ["SELL", "CARROT", 2]],
        }]
        obs = _obs(0, 1)
        obs["private"]["shed"] = {"WOOL": 4, "CARROT": 2}
        obs["market"]["prices"] = {"WOOL": 180, "CARROT": 30, "WHEAT": 25}
        action = {
            "farmer": ["PASS"],
            "hands": [],
            "market": [["BUY_PRODUCT", "WHEAT", 1], ["SELL", "FERTILIZER", 1]],
        }
        router.advance_sales(action, router.FarmView(obs), router.DayState(), tape, 1)
        self.assertEqual(action["market"], [
            ["BUY_PRODUCT", "WHEAT", 1],
            ["SELL", "WOOL", 4],
            ["SELL", "CARROT", 2],
            ["SELL", "FERTILIZER", 1],
        ])

    def test_last_hour_sells_shed_overflow(self):
        obs = _obs(4, 23)
        obs["private"]["shed"] = {"WOOL": 90, "CARROT": 20, "WHEAT": 5}
        obs["market"]["prices"] = {"WOOL": 180, "CARROT": 30, "WHEAT": 40}
        action = {"farmer": ["PASS"], "hands": [], "market": [["HIRE"]]}
        state = router.DayState()
        router.relieve_shed(action, router.FarmView(obs), state, 4 * 24 + 23)
        self.assertEqual(action["market"][0], ["HIRE"])
        self.assertEqual(action["market"][1][0], "SELL")
        self.assertNotEqual(action["market"][1][1], "WHEAT")
        self.assertGreater(state.advanced_sales.get("WOOL", 0) + state.advanced_sales.get("CARROT", 0), 0)

    def test_full_season_does_not_crash(self):
        last = None
        for step in range(720):
            day, hour = divmod(step, 24)
            shops = ["BAKERY", "YARN_STORE"] if step >= 144 else []
            last = router.agent(_obs(day, hour, shops=shops))
            self.assertIn("farmer", last)
            self.assertIn("market", last)
        self.assertEqual(last["farmer"], ["PASS"])
        self.assertEqual(router._POLICY.players[0].plan, 2)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
