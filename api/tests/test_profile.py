import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import profile_api  # noqa: E402
import safe_fetch  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "heavy_tee.html").read_text(encoding="utf-8")
URL = "https://shop.example.com/products/heavy-tee"
client = TestClient(main.app)
BODY = {"person": {"name": "Ana Ruiz", "role": "Founder", "about": "Two-person apparel brand."},
        "company": {"name": "Example Shop", "website": "https://shop.example.com", "sells": "T-shirts",
                    "markets": ["ES", "US"], "languages": ["en", "es"], "price_positioning": "mid",
                    "claims": ["Organic cotton", " "], "competitors": ["https://rival.example.com"], "platform": "shopify"},
        "language": "es",
        "products": [{"url": URL}, {"title": "Camiseta Heavy", "text": "100% algodón. Corte oversize.", "price": "35",
                                    "currency": "EUR", "language": "es"}]}


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"PROFILE_DB": os.path.join(self.tmp.name, "p.db"), "GOVERNANCE_DB": os.path.join(self.tmp.name, "g.db"),
               "PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"),
               "PRODUCTLENS_SIGNALS": str(FIX / "dashboard_signals.jsonl"), "PRODUCTLENS_VISIBILITY": str(FIX / "nope"), "PROFILE_CREATE_RATE_LIMIT": "1000", "AUDIT_STORE_RATE_LIMIT": "1000"}
        profile_api._hits.clear()
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def create(self):
        r = client.post("/v1/profile", json=BODY)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def h(self, token):
        return {"X-Profile-Token": token}

    def test_create_token_once_and_hashed(self):
        b = self.create()
        tok = b["token"]
        self.assertGreaterEqual(len(tok), 40)
        self.assertNotIn(tok, str(b["profile"]))
        db = sqlite3.connect(os.environ["PROFILE_DB"])
        dump = "\n".join(db.iterdump())
        db.close()
        self.assertNotIn(tok, dump)
        g = client.get("/v1/profile", headers=self.h(tok)).json()
        self.assertNotIn("token", g)
        self.assertEqual(g["company"]["name"], "Example Shop")

    def test_auth_required(self):
        self.create()
        self.assertEqual(client.get("/v1/profile").status_code, 401)
        self.assertEqual(client.get("/v1/profile", headers=self.h("wrong")).status_code, 401)
        self.assertEqual(client.put("/v1/profile", json=BODY, headers=self.h("wrong")).status_code, 401)
        self.assertEqual(client.delete("/v1/profile", headers=self.h("wrong")).status_code, 401)

    def test_claims_and_manual_products_are_merchant_stated(self):
        p = self.create()["profile"]
        self.assertEqual(p["company"]["claims"], [{"text": "Organic cotton", "source": "merchant_stated", "verified": False}])
        self.assertTrue(p["merchant_stated"])
        url_p, manual = p["products"]
        self.assertEqual((url_p["source"], url_p["merchant_stated"]), ("url", False))
        self.assertEqual((manual["source"], manual["merchant_stated"]), ("manual", True))

    def test_validation(self):
        bad = {**BODY, "company": {**BODY["company"], "name": ""}}
        self.assertEqual(client.post("/v1/profile", json=bad).status_code, 422)
        self.assertEqual(client.post("/v1/profile", json={**BODY, "products": [{"url": "ftp://x"}]}).status_code, 422)
        self.assertEqual(client.post("/v1/profile", json={**BODY, "products": [{}]}).status_code, 422)

    def test_put_and_delete(self):
        tok = self.create()["token"]
        new = {**BODY, "company": {**BODY["company"], "name": "Renamed"}}
        new.pop("products")
        r = client.put("/v1/profile", json=new, headers=self.h(tok))
        self.assertEqual(r.json()["company"]["name"], "Renamed")
        self.assertEqual(len(r.json()["products"]), 2)  # PUT edits the profile, not the product list
        self.assertEqual(client.delete("/v1/profile", headers=self.h(tok)).status_code, 200)
        self.assertEqual(client.get("/v1/profile", headers=self.h(tok)).status_code, 401)
        db = sqlite3.connect(os.environ["PROFILE_DB"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM products").fetchone()[0], 0)
        db.close()

    def test_audit_url_product_fetches_once_and_stores_record(self):
        b = self.create()
        tok, pid = b["token"], b["profile"]["products"][0]["id"]
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(URL, HTML)) as f:
            r = client.post(f"/v1/profile/products/{pid}/audit", headers=self.h(tok))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(f.call_count, 1)
        p = r.json()
        self.assertEqual(p["audit"]["rank"], client.post("/v1/audit", json={"html": HTML, "url": URL}).json()["rank"])  # same as /v1/audit
        self.assertEqual(p["record"]["source"]["url"], URL)
        # the stored record is valid Product Truth for POST /v1/optimize (stub backend, no spend)
        o = client.post("/v1/optimize", json={"product": p["record"], "language": "en"})
        self.assertEqual(o.status_code, 200, o.text)
        self.assertEqual(o.json()["status"], "draft")

    def test_audit_manual_product_is_a_draft(self):
        b = self.create()
        tok, pid = b["token"], b["profile"]["products"][1]["id"]
        with mock.patch.object(safe_fetch, "fetch_page", side_effect=AssertionError("no fetch for manual")):
            r = client.post(f"/v1/profile/products/{pid}/audit", headers=self.h(tok))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["audit"]["product"]["draft"])

    def test_products_are_scoped_to_their_profile(self):
        a, b = self.create(), self.create()
        pid = a["profile"]["products"][0]["id"]
        self.assertEqual(client.post(f"/v1/profile/products/{pid}/audit", headers=self.h(b["token"])).status_code, 404)
        self.assertEqual(client.delete(f"/v1/profile/products/{pid}", headers=self.h(b["token"])).status_code, 404)
        self.assertEqual(client.delete(f"/v1/profile/products/{pid}", headers=self.h(a["token"])).status_code, 200)

    def test_add_product_and_suggestion_decision(self):
        tok = self.create()["token"]
        r = client.post("/v1/profile/products", json={"url": "https://shop.example.com/p/2"}, headers=self.h(tok))
        self.assertEqual(r.status_code, 201)
        pid = r.json()["id"]
        d = client.put(f"/v1/profile/products/{pid}/suggestion", headers=self.h(tok),
                       json={"field": "title", "status": "accepted", "original": "Old", "suggested": "New"})
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.json()["suggestions"]["title"]["status"], "accepted")
        self.assertIn("never publishes", d.json()["note"])
        bad = client.put(f"/v1/profile/products/{pid}/suggestion", headers=self.h(tok), json={"field": "title", "status": "published"})
        self.assertEqual(bad.status_code, 422)

    def test_stored_audit_stable_link(self):
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(URL, HTML)) as f:
            r = client.post("/v1/audits", json={"url": URL})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(f.call_count, 1)
        b = r.json()
        self.assertGreaterEqual(len(b["id"]), 16)
        self.assertEqual(b["audit"]["rank"], client.post("/v1/audit", json={"html": HTML, "url": URL}).json()["rank"])  # same as /v1/audit
        g = client.get(f"/v1/audits/{b['id']}")
        self.assertEqual(g.status_code, 200)
        self.assertIn("noindex", g.headers["x-robots-tag"])
        self.assertEqual(g.json()["audit"], b["audit"])
        self.assertEqual(g.json()["record"]["source"]["url"], URL)
        self.assertEqual(client.get("/v1/audits/" + "x" * 22).status_code, 404)
        self.assertEqual(client.get("/v1/audits/short").status_code, 404)

    def test_stored_audit_draft_and_errors(self):
        r = client.post("/v1/audits", json={"title": "Camiseta Heavy", "description": "100% algodón. Corte oversize.", "language": "es"})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(r.json()["audit"]["product"]["draft"])
        with mock.patch.object(safe_fetch, "fetch_page", side_effect=safe_fetch.FetchError(403, "robots.txt disallows this URL")):
            e = client.post("/v1/audits", json={"url": URL})
        self.assertEqual(e.status_code, 403)

    def test_rate_limits(self):
        with mock.patch.dict(os.environ, {"PROFILE_CREATE_RATE_LIMIT": "2", "AUDIT_STORE_RATE_LIMIT": "1"}):
            profile_api._hits.clear()
            self.assertEqual([client.post("/v1/profile", json=BODY).status_code for _ in range(3)], [201, 201, 429])
            d = {"title": "Tee", "description": "100% cotton."}
            self.assertEqual([client.post("/v1/audits", json=d).status_code for _ in range(2)], [201, 429])

    def test_stored_audit_expires(self):
        rid = client.post("/v1/audits", json={"title": "Tee", "description": "100% cotton."}).json()["id"]
        self.assertEqual(client.get(f"/v1/audits/{rid}").status_code, 200)
        with mock.patch.dict(os.environ, {"AUDIT_RESULT_TTL_DAYS": "-1"}):  # everything is older than "tomorrow"
            self.assertEqual(client.get(f"/v1/audits/{rid}").status_code, 404)
            client.post("/v1/audits", json={"title": "Tee 2", "description": "100% cotton."})  # a save purges expired rows
        db = sqlite3.connect(os.environ["PROFILE_DB"])
        self.assertEqual(db.execute("SELECT COUNT(*) FROM results WHERE id = ?", (rid,)).fetchone()[0], 0)
        db.close()

    def test_share_link_opt_in_revocable_no_personal_data(self):
        tok = self.create()["token"]
        self.assertFalse(client.get("/v1/profile", headers=self.h(tok)).json()["shared"])
        s = client.post("/v1/profile/share", headers=self.h(tok)).json()["share_token"]
        self.assertGreaterEqual(len(s), 24)
        r = client.get(f"/v1/share/{s}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("noindex", r.headers["x-robots-tag"])
        text = r.text
        for secret in ("Ana Ruiz", "Founder", "Two-person", tok, "Organic cotton", "record"):
            self.assertNotIn(secret, text)
        self.assertEqual(r.json()["company"]["name"], "Example Shop")
        self.assertEqual(client.post("/v1/profile/share", headers=self.h(tok)).json()["share_token"], s)  # stable
        client.delete("/v1/profile/share", headers=self.h(tok))
        gone = client.get(f"/v1/share/{s}")
        self.assertEqual(gone.status_code, 404)
        self.assertIn("noindex", gone.headers["x-robots-tag"])


if __name__ == "__main__":
    unittest.main()
