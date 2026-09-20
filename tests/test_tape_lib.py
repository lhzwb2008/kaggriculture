#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble_tape import TRACE_END, TRACE_START, inject  # noqa: E402
from harvest_tapes import _parse_rows  # noqa: E402
from tape_lib import (  # noqa: E402
    apply_dotenv,
    decode_blob,
    encode_blob,
    extract_actions,
    fingerprint,
    kaggle_cmd,
    kaggle_json_candidates,
    normalize_action,
    obs_step,
    pad_tape,
    prepare_kaggle_auth,
    winning_seats,
)


def _replay(actions0, actions1, rewards):
    steps = [[{}, {}]]
    for a0, a1 in zip(actions0, actions1):
        steps.append([{"action": a0}, {"action": a1}])
    steps.append([{"reward": rewards[0]}, {"reward": rewards[1]}])
    return {"steps": steps, "rewards": rewards, "EpisodeId": 42}


class TapeLibTests(unittest.TestCase):
    def test_obs_step_prefers_day_hour(self):
        self.assertEqual(obs_step({"day": 2, "hour": 5, "step": 0}), 53)
        self.assertEqual(obs_step({"step": 11}), 11)
        self.assertEqual(obs_step({}), 0)

    def test_extract_uses_t_plus_one(self):
        replay = _replay(
            [{"farmer": ["NORTH"], "hands": [], "market": []}],
            [{"farmer": ["SOUTH"], "hands": [], "market": []}],
            [100, 50],
        )
        self.assertEqual(extract_actions(replay, 0)[0]["farmer"], ["NORTH"])
        self.assertEqual(extract_actions(replay, 1)[0]["farmer"], ["SOUTH"])
        self.assertEqual(winning_seats(replay), [0])

    def test_encode_roundtrip(self):
        actions = pad_tape([
            {"farmer": ["PLANT", "WHEAT"], "hands": [["WATER"]], "market": [["HIRE"]]},
        ])
        blob = encode_blob(actions)
        back = decode_blob(blob)
        self.assertEqual(normalize_action(back[0])["farmer"], ["PLANT", "WHEAT"])
        self.assertEqual(len(back), 720)
        self.assertEqual(fingerprint(actions), fingerprint(back))

    def test_current_trace_roundtrip(self):
        import importlib.util

        path = ROOT / "agents" / "c95" / "main.py"
        spec = importlib.util.spec_from_file_location("c95_agent", path)
        agent_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent_mod)

        blob = encode_blob(agent_mod._TRACE)
        back = decode_blob(blob)
        self.assertEqual(len(back), len(agent_mod._TRACE))
        self.assertEqual(fingerprint(agent_mod._TRACE), fingerprint(back))

    def test_parse_kaggle_csv(self):
        text = "skip this\nid,createTime,state\n101,2026-09-01,complete\n102,2026-09-02,complete\n"
        rows = _parse_rows(text)
        self.assertEqual([row["id"] for row in rows], ["101", "102"])

    def test_inject_keeps_overlays(self):
        sample = (
            '"""old doc"""\n'
            "import json\n"
            f"{TRACE_START}\n    'abc'\n{TRACE_END}\n"
            "def agent(obs):\n    return 1\n"
        )
        out = inject(sample, "xyz", '"""new doc"""')
        self.assertIn("'xyz'", out)
        self.assertIn("def agent(obs):", out)
        self.assertTrue(out.startswith('"""new doc"""'))

    def test_dotenv_only_fills_missing_kaggle_keys(self):
        import os
        import tempfile

        os.environ.pop("KAGGLE_USERNAME", None)
        os.environ["KAGGLE_KEY"] = "keep-me"
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            handle.write("KAGGLE_USERNAME=alice\nKAGGLE_KEY=new\nOTHER=nope\n")
            path = Path(handle.name)
        try:
            apply_dotenv(path)
            self.assertEqual(os.environ["KAGGLE_USERNAME"], "alice")
            self.assertEqual(os.environ["KAGGLE_KEY"], "keep-me")
            self.assertNotIn("OTHER", os.environ)
        finally:
            os.environ.pop("KAGGLE_USERNAME", None)
            os.environ.pop("KAGGLE_KEY", None)
            path.unlink(missing_ok=True)

    def test_kaggle_cmd_uses_venv_python(self):
        cmd = kaggle_cmd()
        self.assertGreaterEqual(len(cmd), 2)
        self.assertTrue(cmd[0].endswith("python") or cmd[0].endswith("python3"))
        self.assertTrue(cmd[-1].endswith("kaggle"))

    def test_prepare_auth_points_config_dir_at_json(self):
        import os
        import tempfile

        old_user = os.environ.pop("KAGGLE_USERNAME", None)
        old_key = os.environ.pop("KAGGLE_KEY", None)
        old_dir = os.environ.pop("KAGGLE_CONFIG_DIR", None)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "kaggle.json").write_text('{"username":"a","key":"b"}', encoding="utf-8")
            self.assertTrue(prepare_kaggle_auth(root, required=True))
            self.assertEqual(os.environ.get("KAGGLE_CONFIG_DIR"), str(root))
            self.assertEqual(kaggle_json_candidates(root)[0].name, "kaggle.json")
        if old_user is not None:
            os.environ["KAGGLE_USERNAME"] = old_user
        if old_key is not None:
            os.environ["KAGGLE_KEY"] = old_key
        if old_dir is not None:
            os.environ["KAGGLE_CONFIG_DIR"] = old_dir
        else:
            os.environ.pop("KAGGLE_CONFIG_DIR", None)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
