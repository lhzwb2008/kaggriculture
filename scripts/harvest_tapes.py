#!/usr/bin/env python3
"""Pull public Kaggriculture replays and distill winner tapes.

Typical loop:

    python3 scripts/harvest_tapes.py --export-current
    python3 scripts/harvest_tapes.py --scout-top 3
    python3 scripts/harvest_tapes.py --from-submission 12345678
    python3 scripts/harvest_tapes.py --episode 100453695
    python3 scripts/harvest_tapes.py --from-dir replays
    python3 scripts/harvest_tapes.py --rank
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tape_lib import (  # noqa: E402
    extract_actions,
    find_kaggle,
    fingerprint,
    is_replay,
    is_tape,
    iter_replay_files,
    load_actions,
    load_json,
    pad_tape,
    prepare_kaggle_auth,
    read_manifest_ids,
    replay_episode_id,
    replay_rewards,
    summarize,
    tape_rank_key,
    winning_seats,
    write_tape,
)

DEFAULT_TAPES = ROOT / "tapes"
DEFAULT_REPLAYS = ROOT / "replays"


def _export_current(out_dir: Path) -> Path:
    import importlib.util

    path = ROOT / "agents" / "c95" / "main.py"
    spec = importlib.util.spec_from_file_location("c95_agent", path)
    agent_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent_mod)

    actions = pad_tape(agent_mod._TRACE)
    dest = out_dir / "current_c95.json"
    write_tape(
        dest,
        actions,
        {
            "label": "archived C95 TRACE",
            "source": "agents/c95/main.py",
            "episode_id": "91587143",
            "seat": 1,
        },
    )
    return dest


def _download_replay(episode_id: str, dest: Path, kaggle: list[str]) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [*kaggle, "competitions", "replay", str(episode_id), "-p", str(dest)]
    print(" ".join(cmd))
    code = subprocess.call(cmd)
    if code != 0:
        cmd = [*kaggle, "competitions", "replay", "kaggriculture", str(episode_id), "-p", str(dest)]
        print(" ".join(cmd))
        code = subprocess.call(cmd)
        if code != 0:
            raise SystemExit(f"FAIL: could not download replay {episode_id}")
    matches = list(dest.glob(f"*{episode_id}*.json"))
    if not matches:
        matches = sorted(dest.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise SystemExit(f"FAIL: replay {episode_id} downloaded but no JSON found in {dest}")
    return matches[0]


def _harvest_replay(path: Path, out_dir: Path, seats: list[int] | None, winner_only: bool) -> list[Path]:
    payload = load_json(path)
    if is_tape(payload) and not is_replay(payload):
        actions, meta = load_actions(path)
        dest = out_dir / f"{path.stem}.json"
        write_tape(dest, actions, {**meta, "copied_from": str(path)})
        print(f"copied tape {dest.name}  fp={fingerprint(actions)}")
        return [dest]
    if not is_replay(payload):
        print(f"skip {path}: not a replay")
        return []

    episode = replay_episode_id(payload, fallback=path.stem)
    rewards = replay_rewards(payload)
    chosen = seats if seats is not None else (winning_seats(payload) if winner_only else [0, 1])
    written = []
    for seat in chosen:
        try:
            actions = extract_actions(payload, seat)
        except ValueError as exc:
            print(f"skip {path} seat {seat}: {exc}")
            continue
        bank = rewards[seat] if seat < len(rewards) else None
        dest = out_dir / f"ep{episode}_seat{seat}.json"
        write_tape(
            dest,
            actions,
            {
                "episode_id": episode,
                "seat": seat,
                "bank": bank,
                "rewards": rewards,
                "source": str(path),
                "winner": seat in winning_seats(payload),
            },
        )
        summary = summarize(actions)
        print(
            f"wrote {dest.name}  fp={fingerprint(actions)}  "
            f"bank={bank}  plants={summary['plants']}  sells={summary['sells']}"
        )
        written.append(dest)
    return written


def _kaggle_text(kaggle: list[str], args: list[str]) -> str:
    cmd = [*kaggle, *args]
    print(" ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit((proc.stderr or proc.stdout or "kaggle command failed").strip())
    return proc.stdout


def _parse_rows(text: str) -> list[dict[str, str]]:
    lines = [line for line in text.splitlines() if line.strip()]
    start = 0
    for i, line in enumerate(lines):
        if "," in line and re.search(r"id|teamId|submission", line, re.I):
            start = i
            break
    blob = "\n".join(lines[start:])
    try:
        return list(csv.DictReader(io.StringIO(blob)))
    except csv.Error:
        return []


def _row_id(row: dict[str, str], *keys: str) -> str:
    lower = {k.lower(): v for k, v in row.items()}
    for key in keys:
        value = row.get(key) or lower.get(key.lower())
        if value:
            return str(value).strip()
    return ""


def _episodes_for_submission(kaggle: list[str], submission_id: str, top: int) -> list[str]:
    text = _kaggle_text(kaggle, ["competitions", "episodes", str(submission_id), "-v"])
    rows = _parse_rows(text)
    ids = []
    for row in rows:
        episode = _row_id(row, "id", "episodeId", "EpisodeId")
        if episode and episode not in ids:
            ids.append(episode)
        if len(ids) >= top:
            break
    if not ids:
        ids = re.findall(r"\b\d{5,}\b", text)[:top]
    return ids


def _submissions_for_team(kaggle: list[str], team_id: str) -> list[str]:
    text = _kaggle_text(kaggle, ["competitions", "team-submissions", str(team_id)])
    rows = _parse_rows(text)
    ranked = []
    for row in rows:
        sid = _row_id(row, "id", "submissionId")
        if not sid:
            continue
        try:
            score = float(row.get("publicScore") or row.get("score") or 0)
        except ValueError:
            score = 0.0
        ranked.append((score, sid))
    ranked.sort(reverse=True)
    ids = [sid for _, sid in ranked]
    if not ids:
        ids = re.findall(r"\b\d{5,}\b", text)
    return ids


def _scout_top_teams(kaggle: list[str], n_teams: int, per_team: int) -> list[str]:
    text = _kaggle_text(kaggle, ["competitions", "leaderboard", "kaggriculture", "-s"])
    rows = _parse_rows(text)
    team_ids = []
    for row in rows:
        team = _row_id(row, "teamId", "team_id", "id")
        if team and team not in team_ids:
            team_ids.append(team)
        if len(team_ids) >= n_teams:
            break
    if not team_ids:
        team_ids = re.findall(r"\b\d{3,}\b", text)[:n_teams]
    episode_ids = []
    for team in team_ids:
        submissions = _submissions_for_team(kaggle, team)
        if not submissions:
            continue
        episode_ids.extend(_episodes_for_submission(kaggle, submissions[0], per_team))
    return episode_ids


def _rank(out_dir: Path) -> int:
    rows = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            actions, meta = load_actions(path)
        except ValueError:
            continue
        rows.append((path, actions, meta))
    if not rows:
        print(f"no tapes in {out_dir}")
        return 1
    current_fp = None
    current = out_dir / "current_c95.json"
    if current.is_file():
        _, current_meta = load_actions(current)
        current_fp = current_meta.get("fingerprint")
    rows.sort(key=lambda item: tape_rank_key(item[2]), reverse=True)
    print(f"{'file':<28} {'fp':<12} {'bank':>10} {'same':>5} plants")
    for path, actions, meta in rows:
        same = "yes" if current_fp and meta.get("fingerprint") == current_fp else ""
        plants = (meta.get("summary") or summarize(actions)).get("plants")
        print(
            f"{path.name:<28} {meta.get('fingerprint', ''):<12} "
            f"{str(meta.get('bank', '')):>10} {same:>5} {plants}"
        )
    best = next(
        (item for item in rows if not current_fp or item[2].get("fingerprint") != current_fp),
        rows[0],
    )
    print(f"\nstrongest distinct tape: {best[0]}")
    print(f"assemble with: python3 scripts/assemble_tape.py {best[0]}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=DEFAULT_TAPES)
    p.add_argument("--replays", type=Path, default=DEFAULT_REPLAYS)
    p.add_argument("--episode", action="append", default=[], help="public episode id to download")
    p.add_argument("--from-dir", type=Path, help="folder of replay JSON")
    p.add_argument("--from-manifest", type=Path, help="daily dump manifest.csv")
    p.add_argument("--from-submission", action="append", default=[], help="submission id whose episodes to pull")
    p.add_argument("--from-team", action="append", default=[], help="leaderboard teamId to scout")
    p.add_argument("--scout-top", type=int, default=0, help="pull episodes from the current top N teams")
    p.add_argument("--top", type=int, default=12, help="how many episodes to pull per source")
    p.add_argument("--seat", type=int, choices=[0, 1], help="force one seat instead of the winner")
    p.add_argument("--both", action="store_true", help="keep both seats")
    p.add_argument("--export-current", action="store_true", help="dump main.py TRACE as a baseline tape")
    p.add_argument("--rank", action="store_true", help="print harvested tapes strongest-first")
    p.add_argument("--kaggle", default="")
    args = p.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.export_current:
        path = _export_current(args.out)
        print(f"exported current TRACE to {path}")

    seats = [args.seat] if args.seat is not None else None
    winner_only = not args.both and seats is None
    harvested = 0

    episode_ids = list(args.episode)
    if args.from_manifest:
        episode_ids.extend(read_manifest_ids(args.from_manifest, args.top))
    need_cli = bool(args.from_submission or args.from_team or args.scout_top or episode_ids)
    kaggle: list[str] = []
    if need_cli:
        prepare_kaggle_auth(ROOT)
        kaggle = find_kaggle(args.kaggle)
    if args.scout_top:
        episode_ids.extend(_scout_top_teams(kaggle, args.scout_top, max(1, args.top // max(args.scout_top, 1))))
    for submission_id in args.from_submission:
        episode_ids.extend(_episodes_for_submission(kaggle, submission_id, args.top))
    for team_id in args.from_team:
        submissions = _submissions_for_team(kaggle, team_id)
        if submissions:
            episode_ids.extend(_episodes_for_submission(kaggle, submissions[0], args.top))
    episode_ids = list(dict.fromkeys(episode_ids))

    if episode_ids:
        for episode_id in episode_ids:
            replay = _download_replay(episode_id, args.replays / str(episode_id), kaggle)
            harvested += len(_harvest_replay(replay, args.out, seats, winner_only))

    if args.from_dir:
        for path in iter_replay_files(args.from_dir):
            harvested += len(_harvest_replay(path, args.out, seats, winner_only))

    if harvested:
        print(f"harvested {harvested} tape(s) into {args.out}")

    if args.rank or harvested or args.export_current:
        return _rank(args.out)
    if not (
        args.episode or args.from_dir or args.from_manifest or args.export_current
        or args.from_submission or args.from_team or args.scout_top
    ):
        p.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
