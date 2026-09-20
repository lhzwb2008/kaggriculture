#!/usr/bin/env python3
"""Extract, fingerprint, and encode Kaggriculture replay tapes.

Public replays already store the submitted action. The only fragile bit is the
offset: the action for turn t lives at steps[t + 1]. A 720-step episode has
719 acting turns; we pad a trailing PASS so the in-game tape is 720 long.

Index playback by day * 24 + hour, not obs['step']. Trimmed observations can
arrive without step, and `obs.get('step', 0) or 0` silently replays turn 0.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import json
import os
import shutil
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

PASS_ACTION = {"farmer": ["PASS"], "hands": [], "market": []}
ACTING_TURNS = 719
TAPE_LEN = 720
OPENING = 120
ROOT = Path(__file__).resolve().parents[1]

KAGGLE_AUTH_HELP = """\
FAIL: no Kaggle credentials. Competition submit cannot be anonymous.

This venv uses kaggle 1.7, which does not do browser login. One-time legacy key:

  1. Open https://www.kaggle.com/settings/api
  2. Create Legacy API Key (downloads kaggle.json)
  3. Put the file in one of:
       {root}/kaggle.json          (already gitignored)
       ~/.kaggle/kaggle.json       chmod 600
     or add to {root}/.env:
       KAGGLE_USERNAME=yourname
       KAGGLE_KEY=xxxxxxxx

Then rerun: python3 scripts/submit.py -m "shop-router-0908 public mosaic"
""".format(root=ROOT)


def apply_dotenv(path: Path) -> None:
    """Load KAGGLE_* keys from a dotenv file without overwriting the real env."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key.startswith("KAGGLE_") and key not in os.environ:
            os.environ[key] = value


def kaggle_json_candidates(root: Path | None = None) -> list[Path]:
    root = root or ROOT
    paths: list[Path] = []
    config_dir = os.environ.get("KAGGLE_CONFIG_DIR")
    if config_dir:
        paths.append(Path(config_dir) / "kaggle.json")
    paths.extend(
        [
            root / "kaggle.json",
            root / ".kaggle" / "kaggle.json",
            Path.home() / ".kaggle" / "kaggle.json",
        ]
    )
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.expanduser()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def prepare_kaggle_auth(root: Path | None = None, required: bool = True) -> bool:
    """Wire up legacy API auth so the CLI never needs `kaggle auth login`."""
    root = root or ROOT
    apply_dotenv(root / ".env")
    json_path = next((path for path in kaggle_json_candidates(root) if path.is_file()), None)
    if json_path is not None:
        os.environ.setdefault("KAGGLE_CONFIG_DIR", str(json_path.parent))
        return True
    if os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY"):
        return True
    if required:
        raise SystemExit(KAGGLE_AUTH_HELP)
    return False


def kaggle_cmd(explicit: str = "") -> list[str]:
    """Return argv that runs the CLI even when the venv shebang points at a stale path."""
    root = ROOT
    scripts: list[Path] = []
    if explicit:
        scripts.append(Path(explicit))
    env = os.environ.get("KAGGLE")
    if env:
        scripts.append(Path(env))
    which = shutil.which("kaggle")
    if which:
        scripts.append(Path(which))
    scripts.append(root / ".venv" / "bin" / "kaggle")
    pythons = [root / ".venv" / "bin" / "python"]
    virtual_env = os.environ.get("VIRTUAL_ENV")
    if virtual_env:
        pythons.append(Path(virtual_env) / "bin" / "python")
    which_python = shutil.which("python3")
    if which_python:
        pythons.append(Path(which_python))
    python = next((str(path) for path in pythons if path.is_file()), sys.executable)
    for script in scripts:
        if script.is_file():
            return [python, str(script)]
    raise FileNotFoundError("kaggle CLI not found (pip install kaggle)")


def find_kaggle(explicit: str = "") -> list[str]:
    return kaggle_cmd(explicit)


def obs_step(obs: dict[str, Any]) -> int:
    day, hour = obs.get("day"), obs.get("hour")
    if day is not None and hour is not None:
        try:
            return int(day) * 24 + int(hour)
        except (TypeError, ValueError):
            pass
    raw = obs.get("step")
    if raw in (None, ""):
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def normalize_action(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return dict(PASS_ACTION)
    farmer = raw.get("farmer") or ["PASS"]
    if not isinstance(farmer, list) or not farmer:
        farmer = ["PASS"]
    hands = raw.get("hands") or []
    if not isinstance(hands, list):
        hands = []
    market = raw.get("market") or []
    if not isinstance(market, list):
        market = []
    return {
        "farmer": [str(x) if not isinstance(x, (int, float)) else x for x in farmer],
        "hands": [list(h) if isinstance(h, (list, tuple)) else ["PASS"] for h in hands],
        "market": [list(o) if isinstance(o, (list, tuple)) else o for o in market],
    }


def pad_tape(actions: list[dict[str, Any]], length: int = TAPE_LEN) -> list[dict[str, Any]]:
    out = [normalize_action(row) for row in actions[:length]]
    while len(out) < length:
        out.append(dict(PASS_ACTION))
    return out


def encode_blob(actions: list[dict[str, Any]]) -> str:
    payload = json.dumps(pad_tape(actions), separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return base64.b85encode(zlib.compress(payload, 9)).decode("ascii")


def decode_blob(blob: str) -> list[dict[str, Any]]:
    return json.loads(zlib.decompress(base64.b85decode(blob.encode("ascii"))).decode("utf-8"))


def fingerprint(actions: Iterable[dict[str, Any]], n: int = OPENING) -> str:
    rows = [normalize_action(row) for row, _ in zip(actions, range(n))]
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def summarize(actions: list[dict[str, Any]]) -> dict[str, Any]:
    plants: Counter[str] = Counter()
    sells: Counter[str] = Counter()
    buys: Counter[str] = Counter()
    hires = 0
    land = 0
    animals: Counter[str] = Counter()
    for row in actions:
        units = [row.get("farmer") or ["PASS"], *(row.get("hands") or [])]
        for op in units:
            if isinstance(op, list) and op and op[0] == "PLANT" and len(op) > 1:
                plants[str(op[1])] += 1
        for order in row.get("market") or []:
            if not isinstance(order, list) or not order:
                continue
            kind = order[0]
            if kind == "HIRE":
                hires += 1
            elif kind == "BUY_LAND":
                land += 1
            elif kind == "BUY_ANIMAL" and len(order) >= 3:
                animals[str(order[1])] += int(order[2] or 0)
            elif kind == "SELL" and len(order) >= 3:
                sells[str(order[1])] += int(order[2] or 0)
            elif kind in {"BUY_SEED", "BUY_PRODUCT"} and len(order) >= 3:
                buys[f"{kind}:{order[1]}"] += int(order[2] or 0)
    return {
        "turns": len(actions),
        "hires": hires,
        "buy_land": land,
        "plants": dict(plants),
        "animals": dict(animals),
        "sells": dict(sells),
        "buys": dict(buys),
    }


def _as_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0]
    raise ValueError("replay JSON is not an object")


def load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def extract_actions(replay: Any, seat: int) -> list[dict[str, Any]]:
    """Action for turn t is at steps[t + 1][seat]['action']."""
    data = _as_dict(replay)
    steps = data.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError("replay has no steps")
    actions = []
    for turn in range(len(steps) - 1):
        row = steps[turn + 1]
        if not isinstance(row, list) or seat >= len(row):
            raise ValueError(f"replay step {turn + 1} missing seat {seat}")
        cell = row[seat] or {}
        actions.append(normalize_action(cell.get("action")))
    return actions


def replay_rewards(replay: Any) -> list[float | None]:
    data = _as_dict(replay)
    rewards = data.get("rewards")
    if isinstance(rewards, list) and rewards:
        return [None if r is None else float(r) for r in rewards]
    steps = data.get("steps") or []
    if not steps:
        return []
    last = steps[-1]
    out = []
    for cell in last:
        value = None if not isinstance(cell, dict) else cell.get("reward")
        out.append(None if value is None else float(value))
    return out


def replay_episode_id(replay: Any, fallback: str = "") -> str:
    data = _as_dict(replay)
    for key in ("EpisodeId", "episodeId", "id"):
        if data.get(key) not in (None, ""):
            return str(data[key])
    info = data.get("info") or {}
    if isinstance(info, dict):
        for key in ("EpisodeId", "episodeId", "id"):
            if info.get(key) not in (None, ""):
                return str(info[key])
    return fallback


def winning_seats(replay: Any) -> list[int]:
    rewards = replay_rewards(replay)
    numeric = [(i, r) for i, r in enumerate(rewards) if r is not None]
    if not numeric:
        return [0]
    best = max(r for _, r in numeric)
    return [i for i, r in numeric if r == best]


def iter_replay_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files = []
    for path in sorted(root.rglob("*.json")):
        name = path.name.lower()
        if name in {"manifest.json", "kernel-metadata.json"}:
            continue
        files.append(path)
    return files


def is_replay(payload: Any) -> bool:
    try:
        data = _as_dict(payload)
    except ValueError:
        return False
    steps = data.get("steps")
    return isinstance(steps, list) and len(steps) >= 2 and isinstance(steps[0], list)


def is_tape(payload: Any) -> bool:
    if isinstance(payload, list) and payload and isinstance(payload[0], dict) and "farmer" in payload[0]:
        return True
    if isinstance(payload, dict) and isinstance(payload.get("actions"), list):
        return True
    return False


def load_actions(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, dict) and isinstance(payload.get("actions"), list):
        actions = pad_tape(payload["actions"])
        meta = dict(payload.get("meta") or {})
        meta.setdefault("source", str(path))
        return actions, meta
    if isinstance(payload, list):
        return pad_tape(payload), {"source": str(path)}
    raise ValueError(f"{path} is not a harvested tape")


def write_tape(path: Path, actions: list[dict[str, Any]], meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tape = pad_tape(actions)
    record = {
        "meta": {
            **meta,
            "fingerprint": fingerprint(tape),
            "summary": summarize(tape),
        },
        "actions": tape,
    }
    path.write_text(json.dumps(record, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def read_manifest_ids(path: Path, top: int, score_keys: tuple[str, ...] = (
    "avg_score", "AvgScore", "score", "average_score", "min_score",
)) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return []
    id_key = next(
        (key for key in ("episode_id", "EpisodeId", "episodeId", "id") if key in rows[0]),
        None,
    )
    if id_key is None:
        raise ValueError(f"{path} has no episode id column; saw {list(rows[0])}")
    score_key = next((key for key in score_keys if key in rows[0]), None)

    def score(row: dict[str, str]) -> float:
        if not score_key:
            return 0.0
        try:
            return float(row.get(score_key) or 0)
        except ValueError:
            return 0.0

    ranked = sorted(rows, key=score, reverse=True)
    ids = []
    seen = set()
    for row in ranked:
        episode = str(row.get(id_key) or "").strip()
        if not episode or episode in seen:
            continue
        seen.add(episode)
        ids.append(episode)
        if len(ids) >= top:
            break
    return ids


def tape_rank_key(meta: dict[str, Any]) -> tuple[float, float, str]:
    bank = meta.get("bank")
    score = meta.get("episode_score")
    try:
        bank_n = float(bank) if bank is not None else -1.0
    except (TypeError, ValueError):
        bank_n = -1.0
    try:
        score_n = float(score) if score is not None else -1.0
    except (TypeError, ValueError):
        score_n = -1.0
    return (bank_n, score_n, str(meta.get("episode_id") or ""))
