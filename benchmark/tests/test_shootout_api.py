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


class ShootoutApiTest(unittest.TestCase):
    def get(self, real, sample):
        with mock.patch.dict(os.environ, {"PRODUCTLENS_SHOOTOUT": str(real), "PRODUCTLENS_SHOOTOUT_SAMPLE": str(sample)}):
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


if __name__ == "__main__":
    unittest.main()
