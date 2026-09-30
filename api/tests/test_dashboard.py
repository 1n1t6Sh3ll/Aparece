import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
ENV = {"PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"), "PRODUCTLENS_EVAL": str(FIX / "dashboard_eval.json")}
MISSING = {"PRODUCTLENS_DATA": str(FIX / "nope.jsonl"), "PRODUCTLENS_EVAL": str(FIX / "nope.json")}
client = TestClient(main.app)


@mock.patch.dict(os.environ, ENV)
class DashboardApiTest(unittest.TestCase):
    def test_search(self):
        ids = [r["product_id"] for r in client.get("/v1/products", params={"q": "tee"}).json()["results"]]
        self.assertIn("p_target", ids)
        self.assertNotIn("p_hood", ids)
        self.assertEqual(len(client.get("/v1/products").json()["results"]), 7)
        self.assertEqual(client.get("/v1/products", params={"q": "zip hoodie"}).json()["results"][0]["product_id"], "p_hood")

    def test_product_and_404(self):
        body = client.get("/v1/products/p_heavy").json()
        self.assertEqual(body["summary"]["title"], "Heavyweight Tee")
        self.assertTrue(body["evidence"])
        self.assertEqual(client.get("/v1/products/missing").status_code, 404)
        self.assertEqual(client.get("/v1/products/missing/gaps").status_code, 404)

    def test_gaps_reuse_analysis(self):
        body = client.get("/v1/products/p_target/gaps").json()
        m = body["metrics"]
        self.assertEqual(sorted(m["peer_ids"]), ["p_boxy", "p_heavy", "p_linen", "p_slim"])  # de + hoodie excluded
        self.assertLess(m["attribute_completeness_pct"]["target"], m["attribute_completeness_pct"]["peer_median"])
        self.assertEqual({i["type"] for i in body["issues"]}, {"OBSERVED_FACT", "SUPPORTED_HYPOTHESIS", "UNKNOWN"})
        self.assertEqual(body["price"], {"target": 25.0, "currency": "EUR", "peer_count": 4,
                                         "peer_min": 22.0, "peer_max": 30.0, "peer_median": 27.5})

    def test_stats(self):
        s = client.get("/v1/stats").json()
        self.assertEqual(s["total"], 7)
        self.assertEqual(s["by_language"], {"en": 6, "de": 1})
        self.assertEqual(s["by_product_type"]["hoodie"], 1)
        self.assertEqual(sum(s["by_quality"].values()), 7)

    def test_eval(self):
        body = client.get("/v1/eval").json()
        self.assertTrue(body["available"])
        self.assertIn("finetuned", body["results"])

    def test_missing_files_are_empty(self):
        with mock.patch.dict(os.environ, MISSING):
            self.assertEqual(client.get("/v1/products").json(), {"results": []})
            self.assertEqual(client.get("/v1/stats").json()["total"], 0)
            self.assertEqual(client.get("/v1/eval").json(), {"available": False, "results": {}})

    def test_dashboard_served(self):
        r = client.get("/dashboard/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ProductLens", r.text)


if __name__ == "__main__":
    unittest.main()
