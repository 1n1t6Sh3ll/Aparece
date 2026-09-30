import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import safe_fetch  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "heavy_tee.html").read_text(encoding="utf-8")
URL = "https://shop.example.com/products/heavy-tee"
ENV = {"PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"), "PRODUCTLENS_SIGNALS": str(FIX / "dashboard_signals.jsonl"),
       "PRODUCTLENS_VISIBILITY": str(FIX / "nope")}
client = TestClient(main.app)
KINDS = ["missing_attribute", "description", "structured_data", "price", "language"]


@mock.patch.dict(os.environ, ENV)
class AuditTest(unittest.TestCase):
    def audit(self, **body):
        r = client.post("/v1/audit", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_audit_html_shape_and_rank(self):
        b = self.audit(html=HTML, url=URL)
        self.assertEqual(b["product"]["title"], "Heavyweight Oversized Tee - Black | Example Shop")
        self.assertFalse(b["product"]["draft"])
        # 4 comparable en/EUR t-shirts in band (p_de other language, p_hood other type, p_boxy out of the +/-30% band)
        rk = b["rank"]
        self.assertEqual((rk["position"], rk["total"]), (4, 5))
        self.assertEqual(rk["components"]["facts_stated"], 12)
        pts = rk["components"]["points"]
        self.assertAlmostEqual(rk["score"], pts["facts"] + pts["description"] + pts["structured_data"], places=1)
        self.assertIn("not an AI-visibility or search rank", rk["formula"])
        board = b["leaderboard"]
        self.assertEqual(len(board), 5)
        self.assertEqual(sum(r["is_you"] for r in board), 1)
        self.assertTrue(board[rk["position"] - 1]["is_you"])
        self.assertEqual([r["score"] for r in board], sorted((r["score"] for r in board), reverse=True))

    def test_table_omits_nulls(self):
        t = self.audit(html=HTML, url=URL)["table"]
        self.assertTrue(t["rows"][0]["is_you"])
        for row in t["rows"]:
            self.assertTrue(set(row["values"]) <= set(t["fields"]))
            self.assertNotIn(None, row["values"].values())
        for f in t["fields"]:
            self.assertTrue(any(f in r["values"] for r in t["rows"]))
        self.assertEqual(t["rows"][0]["values"]["content.full_description"], 90)

    def test_actions_ranked_labeled_and_honest(self):
        b = self.audit(html=HTML, url=URL)
        acts = b["actions"]
        self.assertTrue(acts)
        order = [KINDS.index(a["kind"]) for a in acts]
        self.assertEqual(order, sorted(order))
        self.assertEqual([a["priority"] for a in acts], sorted(a["priority"] for a in acts))
        for a in acts:
            self.assertIn(a["label"], ("OBSERVED_FACT", "SUPPORTED_HYPOTHESIS", "UNKNOWN"))
            self.assertIn(a["effort"], ("low", "med", "high"))
            self.assertRegex(a["why"], r"\d")
            self.assertNotRegex(a["why"].lower(), r"will (rank|improve|increase)|guarantee")
        miss = [a for a in acts if a["kind"] == "missing_attribute"]
        self.assertEqual([a["field"] for a in miss[:3]], ["identity.audience", "fit_and_style.pattern", "variants.sizes"])
        self.assertTrue(all("if you can verify it" in a["title"] for a in miss))
        self.assertEqual((miss[0]["evidence"]["peers_with_attribute"], miss[0]["evidence"]["of"]), (4, 4))
        # price 35 EUR vs signals group t_shirt|en|EUR|observed p25-p75 24-29 -> above
        self.assertEqual(b["price_position"]["position"], "above")
        self.assertEqual(b["price_position"]["source"], "signals")
        self.assertIn("not a recommended price", next(a for a in acts if a["kind"] == "price")["why"])

    def test_facts_have_evidence_and_not_found_is_not_absent(self):
        b = self.audit(html=HTML, url=URL)
        gsm = next(f for f in b["facts"] if f["field"] == "materials.fabric_weight_gsm")
        self.assertEqual((gsm["value"], gsm["source_text"]), (240, "240 gsm"))
        self.assertTrue(all(f["value"] not in (None, "", [], {}) for f in b["facts"]))
        nf = {x["field"]: x for x in b["not_found"]}
        self.assertIn("identity.audience", nf)
        self.assertIsNone(nf["identity.audience"]["predicted"])  # no model wired: never a fabricated value
        self.assertFalse(set(nf) & {f["field"] for f in b["facts"]})
        self.assertFalse(b["visibility"]["available"])

    def test_draft_listing(self):
        b = self.audit(title="Heavyweight organic cotton tee </script><b>x", text="Oversized fit.\n100% organic cotton, 240 gsm jersey.",
                       price="35", currency="EUR", language="en")
        self.assertTrue(b["product"]["draft"])
        self.assertEqual(b["product"]["product_type"], "t_shirt")
        self.assertEqual(b["product"]["price"], 35.0)
        self.assertEqual(b["rank"]["weights"]["structured_data"], 0)
        self.assertFalse(any(a["kind"] == "structured_data" for a in b["actions"]))
        self.assertFalse(b["comparison"]["structured_data"]["product_schema_present"]["target"])

    def test_no_peers(self):
        with mock.patch.dict(os.environ, {"PRODUCTLENS_DATA": str(FIX / "nope")}):
            b = self.audit(html=HTML, url=URL)
        self.assertEqual((b["rank"]["position"], b["rank"]["total"]), (1, 1))
        self.assertFalse(any(a["kind"] == "missing_attribute" for a in b["actions"]))

    def test_errors(self):
        self.assertEqual(client.post("/v1/audit", json={}).status_code, 422)
        r = client.post("/v1/audit", json={"html": "<html><title>About us</title><body>Our story</body></html>"})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json()["detail"].startswith("not_a_product_page"))
        with mock.patch.object(safe_fetch, "fetch_page", side_effect=safe_fetch.FetchError(403, "robots.txt disallows this URL")):
            r = client.post("/v1/audit", json={"url": URL})
        self.assertEqual((r.status_code, r.json()["detail"]), (403, "robots.txt disallows this URL"))
        self.assertEqual(client.post("/v1/audit", json={"url": "file:///etc/passwd"}).status_code, 400)

    def test_url_path_uses_safe_fetch(self):
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(URL, HTML)) as fp:
            b = self.audit(url=URL)
        fp.assert_called_once_with(URL)
        self.assertEqual(b["product"]["url"], URL)

    def test_ui_routes(self):
        import audit_api
        with mock.patch.object(audit_api, "WEB", FIX / "nope"):
            self.assertEqual(client.get("/").status_code, 503)
            self.assertEqual(client.get("/assets/x.js").status_code, 404)
        self.assertEqual(client.get("/assets/..%2Fmain.py").status_code, 404)
        self.assertEqual(client.get("/v1/health").status_code, 200)


if __name__ == "__main__":
    unittest.main()
