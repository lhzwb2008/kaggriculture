"""Bounded, own-state routing between complete public-history action tapes."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

FEATURE_NAMES = (
    [f"first_shop_{i}" for i in range(8)]
    + [f"last_shop_{i}" for i in range(8)]
    + [f"shop_count_{i}" for i in range(8)]
    + ["money", "units", "land"]
    + [f"shed_{i}" for i in range(12)]
    + [f"seed_{i}" for i in range(5)]
    + [f"crop_count_{i}" for i in range(5)]
    + [f"crop_yield_{i}" for i in range(5)]
    + [f"animal_count_{i}" for i in range(9, 12)]
    + [f"price_{i}" for i in range(9)]
    + [f"market_stock_{i}" for i in range(9)]
)


def features(shops, money, units, land, shed, seeds, tiles, prices, stock):
    """Use only shops already revealed, own farm, and current public market."""
    shops = list(shops)
    tiles = list(tiles)
    values = [int(bool(shops) and shops[0] == i) for i in range(8)]
    values += [int(bool(shops) and shops[-1] == i) for i in range(8)]
    values += [shops.count(i) for i in range(8)]
    values += [float(money), units, land, *list(shed)[:12], *list(seeds)[:5]]
    values += [sum(t[0] == 5 and t[1] == i for t in tiles) for i in range(5)]
    values += [sum(t[3] for t in tiles if t[0] == 5 and t[1] == i) for i in range(5)]
    values += [sum(bool(t[2]) and t[1] == i for t in tiles) for i in range(9, 12)]
    values += list(prices)[:9] + list(stock)[:9]
    if len(values) != len(FEATURE_NAMES):
        raise ValueError("incomplete routing observation")
    return values


def snapshot_features(snapshot, seat):
    """Extract the same features from a native evaluator's reached state."""
    farm = snapshot["farms"][seat]
    return features(
        snapshot["shops"], farm["money"], len(farm["units"]), farm["n_quadrants"],
        farm["shed"], farm["seeds"],
        [(tile[0], tile[1], tile[2], tile[8]) for tile in farm["tiles"]],
        [row[1] for row in snapshot["market"]], [row[0] for row in snapshot["market"]],
    )


def packed_features(observation, seat):
    """Seat selects the own farm; its identity is never a model input."""
    farm = observation.farms[seat]
    return features(
        list(observation.shops)[:observation.n_shops], farm.money, farm.n_units,
        farm.n_quadrants, list(farm.shed), list(farm.seeds),
        [(tile.kind, tile.what, tile.has_animal, tile.yield_units)
         for row in farm.tiles for tile in row],
        list(observation.market_prices), list(observation.market_inventory),
    )


def obs_step(observation, read):
    """Playback index. Prefer day*24+hour; missing step used to replay turn 0."""
    day, hour = read(observation, "day"), read(observation, "hour")
    if day is not None and hour is not None:
        try:
            return int(day) * 24 + int(hour)
        except (TypeError, ValueError):
            pass
    raw = read(observation, "step", 0)
    if raw in (None, ""):
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def choose(tree, values, active=0):
    """A domain miss or explicit -1 leaf retains the currently executing tape."""
    if len(values) != len(FEATURE_NAMES) or any(not math.isfinite(v) for v in values):
        return active
    if "domain" in tree:
        low, high = tree["domain"]
        if len(low) != len(values) or len(high) != len(values) or any(
            value < minimum or value > maximum
            for value, minimum, maximum in zip(values, low, high)
        ):
            return active
    while "feature" in tree:
        tree = tree["left"] if values[tree["feature"]] <= tree["threshold"] else tree["right"]
    choice = int(tree["choice"])
    return active if choice == -1 else choice


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Router:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.model = json.loads((self.folder / "model.json").read_text())
        if self.model.get("kind") != "mmpq_multi_entry_v1":
            raise ValueError("unexpected routing model kind")
        self.tapes = json.loads((self.folder / "actions.json").read_text())
        self.observation_module = load_module(self.folder / "observation.py", "mmpq_observation")
        self.default = int(self.model["default"])
        if not 0 <= self.default < len(self.tapes) or any(len(tape) != 719 for tape in self.tapes):
            raise ValueError("router requires complete 719-action tapes and a valid default")
        self.stages = {int(stage["step"]): stage for stage in self.model["stages"]}
        if len(self.stages) != len(self.model["stages"]) or any(
            step < 0 or step >= 719 or step % 24 for step in self.stages
        ):
            raise ValueError("routing steps must be distinct dawn boundaries")
        self.active = self.default
        self.decisions = []
        self.last_decision_step = None

    def act(self, observation, configuration=None):
        read = self.observation_module._read
        step = obs_step(observation, read)
        if step == 0:
            self.active = self.default
            self.decisions = []
            self.last_decision_step = None
        if step in self.stages and self.last_decision_step != step:
            seat = int(read(observation, "player", 0))
            packed = self.observation_module._pack_observation(observation, seat)
            values = packed_features(packed, seat)
            selected = choose(self.stages[step]["tree"], values, self.active)
            if not 0 <= selected < len(self.tapes):
                raise ValueError("routing choice outside candidate library")
            self.active = selected
            self.last_decision_step = step
            self.decisions.append({"step": step, "features": values, "choice": selected})
        if 0 <= step < 719:
            return self.tapes[self.active][step]
        return {"farmer": ["PASS"], "hands": [], "market": []}


_ROUTER = None


def agent(observation, configuration=None):
    global _ROUTER
    if _ROUTER is None:
        # Kaggle's source loader omits __file__, but preserves the code filename.
        _ROUTER = Router(Path(agent.__code__.co_filename).resolve().parent)
    return _ROUTER.act(observation, configuration)
