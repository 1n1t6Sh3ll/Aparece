"""GET /v1/shootout serves the report read-only, falls back to the committed sample, never 500s on a missing file."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
SAMPLE = Path(__file__).resolve().parents[1] / "shootout" / "sample_report.json"
REAL = Path(__file__).resolve().parents[1] / "shootout" / "results" / "2026-09-29" / "report.json"


class ShootoutApiTest(unittest.TestCase):
    def get(self, real, sample, out="none.json", committed="none.json"):
        with mock.patch.dict(os.environ, {"PRODUCTLENS_SHOOTOUT": str(real), "PRODUCTLENS_SHOOTOUT_SAMPLE": str(sample),
                                          "PRODUCTLENS_SHOOTOUT_OUT": str(out), "PRODUCTLENS_SHOOTOUT_REAL": str(committed)}):
            r = client.get("/v1/shootout")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_report_sample_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "report.json"
            p.write_text(json.dumps({"generators": {"productlens": {}}, "overall": {"winner": "productlens"}}), encoding="utf-8")
            b = self.get(p, Path(d) / "none.json")
            self.assertTrue(b["available"])
            self.assertEqual(b["overall"]["winner"], "productlens")
            self.assertFalse(self.get(Path(d) / "nope.json", Path(d) / "none.json")["available"])
            s = self.get(Path(d) / "nope.json", SAMPLE)
            self.assertTrue(s["available"] and s["sample"])
            self.assertIn("not proof of real-world ranking", s["label"])

    def test_priority_env_then_out_then_committed_real_then_sample(self):
        with tempfile.TemporaryDirectory() as d:
            env, out = Path(d) / "env.json", Path(d) / "out.json"
            for p, w in ((env, "from-env"), (out, "from-out")):
                p.write_text(json.dumps({"generators": {"g": {}}, "overall": {"winner": w}}), encoding="utf-8")
            miss = Path(d) / "missing.json"
            self.assertEqual(self.get(env, SAMPLE, out, REAL)["overall"]["winner"], "from-env")
            self.assertEqual(self.get(miss, SAMPLE, out, REAL)["overall"]["winner"], "from-out")
            r = self.get(miss, SAMPLE, miss, REAL)
            self.assertTrue(r["available"])
            self.assertIs(r["sample"], False)
            self.assertEqual(r["setup"]["products"], 5)
            self.assertEqual(r["cost"]["judge_calls"], 300)
            self.assertTrue(self.get(miss, SAMPLE, miss, miss)["sample"])

    def test_default_serves_committed_real_run(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("PRODUCTLENS_SHOOTOUT")}
        with mock.patch.dict(os.environ, env, clear=True):
            b = client.get("/v1/shootout").json()
        self.assertTrue(b["available"])
        self.assertIs(b["sample"], False)  # the committed real run (or a newer local out/ run), never the sample


if __name__ == "__main__":
    unittest.main()
