import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
ENV = {"PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"), "PRODUCTLENS_EVAL": str(FIX / "dashboard_eval.json"),
       "PRODUCTLENS_SIGNALS": str(FIX / "dashboard_signals.jsonl"),
       "PRODUCTLENS_VISIBILITY": str(FIX / "dashboard_visibility.json")}
MISSING = {k: str(FIX / "nope") for k in ENV}
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

    def test_signals(self):
        body = client.get("/v1/products/p_target/signals").json()
        self.assertTrue(body["available"])
        self.assertFalse(body["currency_assumed"])
        self.assertEqual(body["signal"]["peer"]["percentile"], 29.2)
        self.assertTrue(client.get("/v1/products/p_heavy/signals").json()["currency_assumed"])
        self.assertEqual(client.get("/v1/products/p_slim/signals").json(), {"available": False, "signal": None})
        self.assertEqual(client.get("/v1/products/missing/signals").status_code, 404)

    def test_competitors_reuse_peers(self):
        body = client.get("/v1/products/p_target/competitors").json()
        peers = {p["product_id"]: p for p in body["peers"]}
        self.assertEqual(sorted(peers), ["p_boxy", "p_heavy", "p_linen", "p_slim"])
        self.assertEqual(peers["p_heavy"]["price_diff_pct"], 12.0)  # 28 vs 25 EUR
        self.assertEqual(peers["p_boxy"]["peer_percentile"], 8.3)
        self.assertGreater(peers["p_heavy"]["completeness_pct"], body["target"]["completeness_pct"])
        self.assertEqual(client.get("/v1/products/missing/competitors").status_code, 404)

    def test_visibility(self):
        body = client.get("/v1/visibility").json()
        self.assertTrue(body["available"])
        self.assertEqual(body["report"]["models"]["mock:mock-1"]["sites"]["shop.example.com"]["top3_rate"], 0.5)

    def test_languages(self):
        langs = client.get("/v1/languages").json()["languages"]
        self.assertEqual(langs["en"]["products"], 6)
        self.assertEqual(langs["de"]["visibility"], {})
        self.assertEqual(langs["es"]["products"], 0)
        self.assertEqual(langs["es"]["visibility"]["mock:mock-1"]["any_catalog_mention_rate"], 0.62)

    def test_new_routes_empty_when_missing(self):
        with mock.patch.dict(os.environ, MISSING):
            self.assertEqual(client.get("/v1/visibility").json(), {"available": False, "report": {}})
            self.assertEqual(client.get("/v1/languages").json(), {"languages": {}, "visibility_available": False})
        with mock.patch.dict(os.environ, {"PRODUCTLENS_SIGNALS": str(FIX / "nope"),
                                          "PRODUCTLENS_VISIBILITY": str(FIX / "heavy_tee.html")}):
            self.assertFalse(client.get("/v1/products/p_target/signals").json()["available"])
            self.assertFalse(client.get("/v1/visibility").json()["available"])  # malformed JSON

    def test_ground_truth_rows_regression(self):
        """dataset/output/final rows (string `source`, `gold` dotted keys) used to 500 in summary()."""
        with mock.patch.dict(os.environ, {"PRODUCTLENS_DATA": str(FIX / "dashboard_groundtruth.jsonl")}):
            rows = client.get("/v1/products").json()["results"]
            self.assertEqual([r["product_id"] for r in rows],
                             ["p_0000ebebddf4ef1d", "p_0009c51440229682", "p_000e804b82232833", "p_badfields"])
            self.assertEqual(rows[0]["brand"], "Lord of the Rings")  # HTML entities decoded
            self.assertEqual(rows[0]["product_type"], "t_shirt")
            self.assertEqual(rows[0]["merchant"], "merchoid.com")
            s = client.get("/v1/stats").json()
            self.assertEqual(s["total"], 4)
            self.assertEqual(s["by_language"]["en"], 3)
            for path in ("", "/gaps", "/competitors", "/signals"):
                self.assertEqual(client.get(f"/v1/products/p_0000ebebddf4ef1d{path}").status_code, 200, path)
                self.assertEqual(client.get(f"/v1/products/p_badfields{path}").status_code, 200, path)
            self.assertEqual(client.get("/v1/languages").status_code, 200)

    def test_old_dashboard_redirects(self):
        for path in ("/dashboard", "/dashboard/", "/dashboard/app.js"):
            r = client.get(path, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers["location"]), (307, "/"), path)


if __name__ == "__main__":
    unittest.main()
