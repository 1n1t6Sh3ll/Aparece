import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import dashboard_api  # noqa: E402
import main  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "dashboard_records.jsonl"
client = TestClient(main.app)


def rich_record():
    from benchmark.shootout.live import fact_sentences, product_truth
    for line in FIX.read_text(encoding="utf-8").splitlines():
        rec = dashboard_api.adapt(json.loads(line))
        if rec and len(fact_sentences(product_truth(rec), "en")) >= 2:
            return rec
    raise unittest.SkipTest("no fixture record with 2+ facts")


class ShootoutLiveTest(unittest.TestCase):
    def test_offline_runs_free_generators_only(self):
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""}):
            j = client.post("/v1/shootout/live", json={"product": rich_record(), "language": "en"}).json()
        self.assertTrue(j["available"])
        self.assertTrue(j["live"])
        self.assertEqual(set(j["generators"]), {"original", "productlens"})
        self.assertEqual(j["cost"]["generation_usd"], 0.0)
        self.assertEqual(len(j["products"]), 1)
        self.assertIn("Skipped", j["caveats"][-1])

    def test_bad_input_is_422(self):
        self.assertEqual(client.post("/v1/shootout/live", json={"product": "x"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
