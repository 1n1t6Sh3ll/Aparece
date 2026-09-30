import os
import re
import sys
import tempfile
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
        self.assertNotIn("content.full_description", {f["field"] for f in b["facts"]})
        self.assertEqual(b["comparison"]["description_chars"]["target"], 90)
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

    def test_draft_title_description_only(self):
        b = self.audit(title="Heavyweight organic cotton tee", description="Oversized fit. 100% organic cotton, 240 gsm.",
                       language="en")
        self.assertTrue(b["product"]["draft"])
        self.assertEqual(b["product"]["product_type"], "t_shirt")
        self.assertIn("position", b["rank"])
        self.assertGreater(b["rank"]["total"], 1)
        self.assertTrue(b["actions"])

    def test_draft_plain_text(self):
        b = self.audit(text="Delvik Black T-shirt\nPrice: 29.90 EUR\nMen t-shirt. 100% organic cotton.", language="en")
        self.assertTrue(b["product"]["draft"])
        self.assertEqual(b["product"]["product_type"], "t_shirt")
        self.assertEqual(b["product"]["price"], 29.9)

    def test_draft_type_from_description_or_unknown(self):
        b = self.audit(title="Delvik Black", description="A relaxed polo in pique cotton.", language="en")
        self.assertEqual(b["product"]["product_type"], "polo")
        b = self.audit(title="Delvik Black shirt", description="Soft and warm.", language="en")  # generic, no sleeve
        self.assertEqual(b["product"]["product_type"], "unknown")
        self.assertTrue(b["notes"])

    def test_draft_states_only_what_the_text_says(self):
        """#69: no invented availability, currency only from an explicit symbol/code, never a schema.org source."""
        b = self.audit(text="Unisex heavyweight tee\n240 gsm 100% cotton, boxy fit, dropped shoulders. $35")
        facts = {f["field"]: f for f in b["facts"]}
        self.assertNotIn("commerce.availability", facts)
        self.assertEqual((facts["commerce.price"]["value"], facts["commerce.currency"]["value"]), (35.0, "USD"))
        self.assertEqual(facts["commerce.currency"]["source_location"], "draft text")
        self.assertEqual(facts["commerce.currency"]["source_text"], "$35")
        for f in b["facts"]:
            self.assertNotIn("schema", str(f["source_location"]))
        b = self.audit(title="Heavy tee", description="100% cotton, 240 gsm. Price 35", language="en")
        self.assertIsNone(b["context"]["currency"])  # no symbol or code -> no currency (and no price)
        b = self.audit(title="Heavy tee", description="100% cotton. Sold out.", price=35, currency="aud", language="en")
        facts = {f["field"]: f for f in b["facts"]}
        self.assertEqual((facts["commerce.availability"]["value"], facts["commerce.availability"]["source_text"]),
                         ("out_of_stock", "Sold out"))
        self.assertEqual((facts["commerce.currency"]["value"], facts["commerce.currency"]["source_location"]),
                         ("AUD", "draft.currency"))
        self.assertEqual(self.audit(text="Heavy tee\n29,90 EUR. In stock.", language="en")["context"]["currency"], "EUR")

    def test_draft_rejects_bad_price_currency_and_types(self):
        cases = [({"price": -5, "currency": "EUR"}, "invalid_price"), ({"price": 0}, "invalid_price"),
                 ({"price": "abc"}, "invalid_price"), ({"price": True}, "invalid_price"),
                 ({"price": 5, "currency": "ZZZ"}, "invalid_currency"), ({"currency": 5}, "invalid_field"),
                 ({"title": ["a"]}, "invalid_field"), ({"description": {"x": 1}}, "invalid_field"),
                 ({"language": 1}, "invalid_field")]
        for extra, err in cases:
            r = client.post("/v1/audit", json={"title": "Cotton t-shirt", "description": "cotton", **extra})
            self.assertEqual(r.status_code, 422, extra)
            self.assertTrue(r.json()["detail"].startswith(err), (extra, r.text))

    def test_language_codes_normalized_or_detected(self):
        """#71: en-US / EN / missing give the same peers as en; es-MX -> es."""
        body = {"title": "Men's slim fit t-shirt", "description": "100% cotton jersey, crew neck, short sleeves."}
        base = self.audit(**body, language="en")
        self.assertGreater(base["rank"]["total"], 1)
        for lang in ("en-US", "EN", "en_gb", None):
            b = self.audit(**body, **({"language": lang} if lang else {}))
            self.assertEqual(b["context"]["language"], "en", lang)
            self.assertEqual([p["product_id"] for p in b["peers"]], [p["product_id"] for p in base["peers"]], lang)
            self.assertEqual(b["rank"]["total"], base["rank"]["total"])
        self.assertTrue(any("detected" in n for n in b["notes"]))
        es = self.audit(title="Camiseta de algodón para hombre", description="Manga corta, cuello redondo.")
        self.assertEqual(es["context"]["language"], "es")
        self.assertEqual(self.audit(title="Camiseta", description="algodón", language="es-MX")["context"]["language"], "es")
        page = HTML.replace("<html", '<html lang="en-US"', 1) if "<html lang" not in HTML else \
            re.sub(r'<html lang="[^"]*"', '<html lang="EN-us"', HTML, count=1)
        self.assertEqual(self.audit(html=page, url=URL)["context"]["language"], "en")

    def test_not_a_shirt_is_not_ranked(self):
        """#72: non-shirts get a clear 422 instead of 'rank 1 of 1'."""
        for body in ({"title": "Stainless steel water bottle 750ml", "description": "Double-wall insulated"},
                     {"title": "123456", "description": "789 1011"},
                     {"html": '<html lang="en"><head><title>Men\'s Tree Runners</title><script type="application/ld+json">'
                              '{"@type":"Product","name":"Men\'s Tree Runners","offers":{"@type":"Offer","price":"98",'
                              '"priceCurrency":"USD"}}</script></head><body><h1>Men\'s Tree Runners</h1>'
                              '<p>Breathable sneakers.</p></body></html>', "url": "https://shoes.example.com/p/runner"}):
            r = client.post("/v1/audit", json=body)
            self.assertEqual(r.status_code, 422, body)
            self.assertTrue(r.json()["detail"].startswith("not_a_shirt"), r.text)

    def test_product_never_ranked_against_itself(self):
        """The dataset row of the audited page (same URL up to www/slash/query/case) is not a peer."""
        import json
        recs = [json.loads(x) for x in (FIX / "dashboard_records.jsonl").read_text(encoding="utf-8").splitlines() if x]
        me = {**recs[1], "product_id": "p_me", "source": {**recs[1]["source"], "url": "https://WWW.shop.example.com/products/heavy-tee/?v=1"}}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in recs + [me]), encoding="utf-8")
            with mock.patch.dict(os.environ, {"PRODUCTLENS_DATA": str(p)}):
                b = self.audit(html=HTML, url=URL)
        ids = [r["product_id"] for r in b["leaderboard"] if not r["is_you"]] + [x["product_id"] for x in b["peers"]]
        self.assertNotIn("p_me", ids)
        self.assertEqual(sum(r["is_you"] for r in b["leaderboard"]), 1)

    def test_url_and_draft_of_same_dataset_tee_get_same_peers(self):
        """#73 regression: a saved dataset page (merchjungle.com Shopify JSON, 50 AUD) vs the same text as a draft.
        Root cause was the same-currency hard filter: the page states AUD, dataset rows have no recorded currency."""
        import json
        prod = json.loads((FIX / "shopify_blink_tee.json").read_text(encoding="utf-8"))["product"]
        u = "https://merchjungle.com/products/blink-182-roger-rabbit-tee"
        with mock.patch.dict(os.environ, {"PRODUCTLENS_DATA": str(FIX / "dataset_blink_peers.jsonl")}), \
                mock.patch.object(safe_fetch, "fetch_page", return_value=(u, safe_fetch.shopify_html(prod))):
            page = self.audit(url=u)
            draft = self.audit(title="Blink-182 Roger Rabbit Tee - Fun Design Cotton T-Shirt",
                               description="100% cotton tee. printed", language="en", price=50, currency="AUD")
        self.assertEqual((page["product"]["product_type"], page["context"]["language"], page["context"]["currency"]),
                         ("t_shirt", "en", "AUD"))
        self.assertEqual((len(page["peers"]), len(draft["peers"])), (10, 10))
        # a draft is new text, so the published product's dataset row may be its peer; the page's own row is not
        self.assertEqual(draft["rank"]["total"], 14)
        self.assertEqual(page["rank"]["total"], 13)
        self.assertNotIn("p_808368fc7073d41d", [x["product_id"] for x in page["peers"]])

    def test_peers_without_recorded_currency(self):
        """Dataset rows with no currency must still be peers of a priced page (was: #1 of 1, 0 actions)."""
        import json
        import tempfile
        rows = [json.loads(x) for x in (FIX / "dashboard_records.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        for r in rows:
            r["commerce"]["currency"] = None
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "recs.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
            with mock.patch.dict(os.environ, {"PRODUCTLENS_DATA": str(p)}):
                b = self.audit(html=HTML, url=URL)
        self.assertGreater(b["rank"]["total"], 1)
        self.assertTrue(b["actions"])
        self.assertTrue(any("no recorded currency" in n for n in b["notes"]))
        self.assertEqual(b["context"]["currency"], "EUR")  # the page's own facts are unchanged
        self.assertFalse(any(x["url"] == URL for x in b["peers"]))  # never its own peer

    def test_shopify_json_page_audit(self):
        """Saved Shopify /products/<handle>.json (sepiia.com) through the fallback mapping and the normal audit."""
        import json
        prod = json.loads((FIX / "shopify_product.json").read_text(encoding="utf-8"))["product"]
        page = safe_fetch.shopify_html(prod)
        u = "https://sepiia.com/products/camiseta-hombre-cuello-redondo-negra-soft"
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(u, page)):
            r = client.post("/v1/extract", json={"url": u})
            b = self.audit(url=u)
        n = r.json()["normalized"]
        self.assertEqual((n["identity"]["product_type"], n["source"]["language"]), ("t_shirt", "es"))
        self.assertEqual((n["commerce"]["price"], n["commerce"]["currency"]), (49.9, "EUR"))
        self.assertEqual(n["identity"]["brand"], "Sepiia")
        self.assertTrue(n["content"]["full_description"])
        self.assertEqual(b["rank"]["total"], 1)  # the fixture dataset has no Spanish shirts
        self.assertTrue(any(x.startswith("No comparable shirts") for x in b["notes"]))

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
