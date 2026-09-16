"""Kaggriculture baseline: wheat plant / water / harvest loop with movement.

Kaggle requires a root-level `agent(obs)` in main.py.
"""

from __future__ import annotations


WHEAT_FIRST_YIELD = 2
WHEAT_SEED_COST = 10


def _step_toward(fx: int, fy: int, tx: int, ty: int) -> str:
    if fx < tx:
        return "EAST"
    if fx > tx:
        return "WEST"
    if fy < ty:
        return "SOUTH"
    if fy > ty:
        return "NORTH"
    return "PASS"


def _plant_action(tile: object, day: int) -> list[str] | None:
    if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
        return None
    age = day - tile["planted_day"]
    if tile.get("yield_units", 0) > 0 or age >= WHEAT_FIRST_YIELD:
        return ["HARVEST"]
    if not tile.get("watered_today"):
        return ["WATER"]
    return None


def _targets(tiles: list, day: int, have_seed: bool) -> list[tuple[int, int, list[str]]]:
    harvest, water, weed, plant = [], [], [], []
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED":
                continue
            act = _plant_action(tile, day)
            if act == ["HARVEST"]:
                harvest.append((x, y, act))
            elif act == ["WATER"]:
                water.append((x, y, act))
            elif isinstance(tile, dict) and tile.get("kind") == "WEED":
                weed.append((x, y, ["DIG"]))
            elif tile is None and have_seed:
                plant.append((x, y, ["PLANT", "WHEAT"]))
    return harvest + water + weed + plant


def agent(obs, config=None):
    me = obs["farms"][obs["player"]]
    private = obs["private"]
    fx, fy = me["farmer"]
    tile = me["tiles"][fy][fx]
    seeds = private["seeds"].get("WHEAT", 0)

    market = []
    if seeds == 0 and me["money"] >= WHEAT_SEED_COST:
        market.append(["BUY_SEED", "WHEAT", 1])
    wheat = private["shed"].get("WHEAT", 0)
    if wheat > 0:
        market.append(["SELL", "WHEAT", wheat])

    here = _plant_action(tile, obs["day"])
    if here:
        return {"farmer": here, "hands": [], "market": market}
    if tile is None and seeds > 0:
        return {"farmer": ["PLANT", "WHEAT"], "hands": [], "market": market}
    if isinstance(tile, dict) and tile.get("kind") == "WEED":
        return {"farmer": ["DIG"], "hands": [], "market": market}

    cands = _targets(me["tiles"], obs["day"], seeds > 0 or any(o[0] == "BUY_SEED" for o in market))
    if not cands:
        return {"farmer": ["PASS"], "hands": [], "market": market}
    tx, ty, cmd = min(cands, key=lambda c: abs(c[0] - fx) + abs(c[1] - fy))
    if (fx, fy) == (tx, ty):
        return {"farmer": cmd, "hands": [], "market": market}
    return {"farmer": [_step_toward(fx, fy, tx, ty)], "hands": [], "market": market}
