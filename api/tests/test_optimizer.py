import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from governance import audit, policy  # noqa: E402
from optimizer import fix, guard  # noqa: E402
from optimizer.truth import json_ld, product_truth  # noqa: E402

client = TestClient(main.app)


def ev(field, value, text):
    return {"field": field, "value": value, "source_text": text, "source_location": "raw_full_description"}


RECORD = {
    "product_id": "p_1",
    "source": {"language": "en", "canonical_url": "https://shop.example.com/p/p_1"},
    "identity": {"brand": "Northwind", "product_name": "Everyday Tee", "audience": "men"},
    "content": {"title": "Everyday Tee", "full_description": "The best tee ever. Waterproof and award-winning. "
                "60% cotton, 40% polyester. Made in Portugal.", "bullet_points": []},
    "materials": {"material_percentages": {"cotton": 60, "polyester": 40}, "primary_material": "cotton",
                  "fabric_weight_gsm": 180},
    "fit_and_style": {"fit": "regular", "sleeve_length": "short", "neckline": None},
    "variants": {"colors": [{"original_color_name": "Black", "normalized": "black"}],
                 "sizes": [{"raw_size": s, "normalized_size": s} for s in ("S", "M", "L")]},
    "commerce": {"price": 25.0, "currency": "EUR", "availability": "in_stock"},
    "evidence": [ev("identity.brand", "Northwind", "Northwind"), ev("identity.product_name", "Everyday Tee", "Everyday Tee"),
                 ev("identity.audience", "men", "men's"),
                 ev("materials.material_percentages", {"cotton": 60, "polyester": 40}, "60% cotton, 40% polyester"),
                 ev("materials.primary_material", "cotton", "60% cotton"), ev("materials.fabric_weight_gsm", 180, "180 gsm"),
                 ev("fit_and_style.fit", "regular", "Regular fit"), ev("fit_and_style.sleeve_length", "short", "Short sleeve"),
                 ev("variants.colors", "Black", "Black"), ev("variants.sizes", "S", "S"),
                 ev("commerce.price", 25.0, "25.00"), ev("commerce.currency", "EUR", "EUR"),
                 ev("commerce.availability", "in_stock", "InStock")],
}
GAPS = {"issues": [{"type": "OBSERVED_FACT", "field": "fit_and_style.neckline",
                    "evidence": {"peers_with_attribute": ["a", "b"], "count": 2, "of": 3}}]}


def hallucinating(system, user):
    return json.dumps({"title": "Northwind Everyday Tee - 100% Organic Cotton, Waterproof",
                       "description": "Made of 100% organic cotton. Regular fit. Waterproof and award-winning. "
                                      "Made in Italy. Available in red. Price: 25.00 EUR."})


class OptimizerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.dict(os.environ, {"GOVERNANCE_DB": os.path.join(self.tmp.name, "g.db"),
                                         "GOVERNANCE_TOKEN": "t0k", "OPTIMIZER_BACKEND": "stub",
                                         "OPTIMIZER_PAIRS_LOG": os.path.join(self.tmp.name, "pairs.jsonl")})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_truth_uses_evidence_only(self):
        rec = copy.deepcopy(RECORD)
        rec["evidence"] = [e for e in rec["evidence"] if e["field"] != "fit_and_style.fit"]
        facts = product_truth(rec)["facts"]
        self.assertNotIn("fit_and_style.fit", facts)
        self.assertEqual(facts["materials.fabric_weight_gsm"], 180)
        self.assertEqual(product_truth(rec)["origins"], ["portugal"])

    def test_stub_en_and_es_fully_grounded(self):
        for lang in ("en", "es"):
            out = fix.generate(RECORD, lang, GAPS, backend="stub")
            self.assertEqual(out["removed_sentences"], [], out)
            self.assertEqual(out["accuracy_after"]["accuracy"], 1.0)
            self.assertGreaterEqual(out["accuracy_after"]["accuracy"], out["accuracy_before"]["accuracy"])
            self.assertIn("Northwind Everyday Tee", out["title"])
        self.assertIn("Tallas: S, M, L.", out["description"])
        self.assertIn("Hecho en Portugal.", out["description"])
        self.assertIn("Corte regular.", out["description"])

    def test_before_accuracy_penalises_marketing(self):
        out = fix.generate(RECORD, "en", None, backend="stub")
        self.assertLess(out["accuracy_before"]["accuracy"], 1.0)  # "Waterproof", "award-winning" unsupported

    def test_hallucinating_backend_rejected_then_stripped(self):
        calls = []

        def spy(system, user):
            calls.append(user)
            return hallucinating(system, user)
        out = fix.generate(RECORD, "en", None, backend=spy, candidates=1)
        self.assertEqual(len(calls), 1 + fix.MAX_RETRIES)
        self.assertIn("rejected", calls[1])
        text = out["title"] + " " + out["description"]
        for bad in ("Organic", "organic", "Waterproof", "award", "Italy", "red"):
            self.assertNotIn(bad, text)
        self.assertEqual(out["title"], "Northwind Everyday Tee - 60% cotton, 40% polyester")  # fallback title
        self.assertIn("Regular fit.", out["description"])
        self.assertIn("Price: 25.00 EUR.", out["description"])
        self.assertTrue(out["removed_sentences"])
        self.assertEqual(out["accuracy_after"]["accuracy"], 1.0)

    def test_regeneration_recovers(self):
        seq = iter([hallucinating(None, None), json.dumps({"title": "Northwind Everyday Tee",
                                                           "description": "Regular fit. Short sleeves. 180 gsm."})])
        out = fix.generate(RECORD, "en", None, backend=lambda s, u: next(seq), candidates=1)
        self.assertEqual(len(out["attempts"]), 2)
        self.assertEqual(out["removed_sentences"], [])
        self.assertEqual(out["description"], "Regular fit. Short sleeves. 180 gsm.")

    def test_best_of_n_by_reward_hallucination_never_wins(self):
        outs = [hallucinating(None, None),  # hallucinating (highest raw coverage claims, but flagged)
                json.dumps({"title": "Northwind Everyday Tee", "description": "Regular fit. Short sleeves."}),
                json.dumps({"title": "Northwind Everyday Tee - 60% cotton, 40% polyester",
                            "description": "Regular fit. Short sleeves. 180 gsm. Sizes: S, M, L. Price: 25.00 EUR."})]
        calls = []

        def three(system, user):
            calls.append(user)
            return outs[(len(calls) - 1) % 3]
        out = fix.generate(RECORD, "en", None, backend=three)
        self.assertEqual(len(calls), 3)  # one round: a grounded candidate exists
        self.assertIn("candidate 1 of 3", calls[0])
        c = out["candidates"]
        self.assertEqual([x["chosen"] for x in c], [False, False, True])
        self.assertFalse(c[0]["guard_passed"])
        self.assertLess(c[0]["reward"]["hallucination"], 0)
        self.assertTrue(c[0]["reward"]["hallucinated"])
        self.assertGreater(c[2]["reward"]["coverage"], c[1]["reward"]["coverage"])
        self.assertGreater(c[2]["reward"]["total"], c[1]["reward"]["total"])
        self.assertEqual(out["reward"], c[2]["reward"])
        self.assertEqual(out["description"], "Regular fit. Short sleeves. 180 gsm. Sizes: S, M, L. Price: 25.00 EUR.")
        self.assertEqual(out["removed_sentences"], [])
        rows = [json.loads(x) for x in Path(os.environ["OPTIMIZER_PAIRS_LOG"]).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(json.loads(r["chosen"])["description"] == out["description"] for r in rows))
        self.assertTrue(all(r["chosen_reward"] > r["rejected_reward"] for r in rows))
        self.assertNotIn("actor", rows[0])
        # hallucination never wins even when it is the only one with a high claim count and others are sparse
        seq = iter([hallucinating(None, None)] * 2 + [json.dumps({"title": "Northwind Everyday Tee",
                                                                 "description": "Regular fit."})])
        out = fix.generate(RECORD, "en", None, backend=lambda s, u: next(seq))
        self.assertEqual(out["description"], "Regular fit.")

    def test_all_flagged_winner_not_logged(self):
        fix.generate(RECORD, "en", None, backend=hallucinating)
        self.assertFalse(os.path.exists(os.environ["OPTIMIZER_PAIRS_LOG"]))

    def test_api_candidates_param(self):
        r = client.post("/v1/optimize", json={"product": RECORD, "candidates": 2})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(r.json()["candidates"]), 2)
        self.assertEqual(client.post("/v1/optimize", json={"product": RECORD, "candidates": 9}).status_code, 422)

    def test_unparseable_backend_falls_back_to_facts(self):
        out = fix.generate(RECORD, "en", None, backend=lambda s, u: "not json")
        self.assertTrue(out["used_fallback"])
        self.assertIn("Material: 60% cotton, 40% polyester.", out["description"])

    def test_guard_flags(self):
        truth = product_truth(RECORD)
        for s in ("Made of 100% silk.", "Weighs 250 gsm.", "Eco-friendly fabric.", "Rated 5 stars.", "Slim fit.",
                  "Made in Italy.", "GOTS certified.", "Price: 30.00 EUR."):
            self.assertTrue(guard.check_text(s, truth)[0]["problems"], s)
        for s in ("60% cotton, 40% polyester.", "Short sleeves.", "Sizes S, M and L.", "Made in Portugal."):
            self.assertEqual(guard.check_text(s, truth)[0]["problems"], [], s)

    def test_allowlist_rejects_ungrounded_claims(self):
        truth = product_truth(RECORD)
        for s in ("Good for your health.", "Relieves back pain.", "Ideal for sensitive skin.", "Made from bamboo.",
                  "Eco-conscious.", "Free shipping.", "Bueno para tu salud.", "Alivia el dolor de espalda.",
                  "Ideal para pieles sensibles.", "Hecho de bambú.", "Eco-consciente.", "Envío gratis.",
                  "This tee is made with 60% cotton and ships free.", "Regular fit, not slim."):
            self.assertTrue(guard.check_text(s, truth)[0]["problems"], s)
        for s in ("This tee is made with 60% cotton, 40% polyester.", "Available in black, sizes S to L.",
                  "Esta camiseta de corte regular tiene manga corta.", "Precio: 25.00 EUR."):
            self.assertEqual(guard.check_text(s, truth)[0]["problems"], [], s)

    def test_values_bound_to_their_field(self):
        truth = product_truth(RECORD)
        for s in ("Sale price: 25.00 EUR.", "Precio rebajado: 25.00 EUR.", "Available in 25 colors.", "180 sizes.",
                  "Price: 180 EUR.", "Fabric weight: 25 gsm.", "60% polyester, 40% cotton.", "Out of stock.",
                  "Regular fit with 3/4 sleeves.", "Rated 60 by customers."):
            self.assertTrue(guard.check_text(s, truth)[0]["problems"], s)
        rec = copy.deepcopy(RECORD)
        rec["commerce"]["availability"] = None
        self.assertTrue(guard.check_text("In stock.", product_truth(rec))[0]["problems"])
        rec["commerce"]["sale_price"] = 20.0
        rec["evidence"].append(ev("commerce.sale_price", 20.0, "20.00"))
        self.assertEqual(guard.check_text("Price: 25.00 EUR. Sale price: 20.00 EUR.", product_truth(rec))[1]["problems"], [])

    def test_product_name_is_not_attribute_evidence(self):
        rec = copy.deepcopy(RECORD)
        rec["identity"]["product_name"] = "Organic Eco Tee"
        rec["content"]["title"] = "Organic Eco Tee"
        rec["evidence"] = [e for e in rec["evidence"] if e["field"] != "identity.product_name"]
        rec["evidence"].append(ev("identity.product_name", "Organic Eco Tee", "Organic Eco Tee"))
        truth = product_truth(rec)
        for s in ("Organic cotton tee.", "Eco tee.", "Camiseta de algodón orgánico."):
            self.assertTrue(guard.check_text(s, truth)[0]["problems"], s)
        self.assertEqual(guard.check_text("The Organic Eco Tee has short sleeves.", truth)[0]["problems"], [])
        out = fix.generate(rec, "en", None, backend="stub")
        self.assertEqual(out["removed_sentences"], [])

    def test_all_stripped_uses_template(self):
        bad = json.dumps({"title": "", "description": "Good for your health. Free shipping."})
        for lang, first in (("en", "Material: 60% cotton"), ("es", "Material: 60% algodón")):
            out = fix.generate(RECORD, lang, None, backend=lambda s, u: bad)
            self.assertTrue(out["used_fallback"])
            self.assertTrue(out["title"])
            self.assertTrue(out["description"].startswith(first), out["description"])
            self.assertEqual(guard.accuracy(guard.check_text(out["description"], product_truth(RECORD)))["accuracy"], 1.0)

    def test_not_enough_verified_facts(self):
        thin = dict(RECORD, evidence=[ev("identity.brand", "Northwind", "Northwind")])
        with self.assertRaisesRegex(ValueError, "not enough verified facts"):
            fix.generate(thin, "en", None, backend="stub")
        r = client.post("/v1/optimize", json={"product": thin})
        self.assertEqual(r.status_code, 422)
        self.assertIn("not enough verified facts", r.text)

    def test_missing_attributes_and_jsonld(self):
        out = fix.generate(RECORD, "en", GAPS, backend="stub")
        first = out["missing_attributes"][0]
        self.assertEqual((first["field"], first["peers_with_attribute"]), ("fit_and_style.neckline", "2/3"))
        fields = {m["field"] for m in out["missing_attributes"]}
        self.assertIn("commerce.gtin", fields)
        self.assertNotIn("materials.fabric_weight_gsm", fields)
        ld = out["json_ld"]
        self.assertEqual(ld["@type"], "Product")
        self.assertEqual(ld["offers"], {"@type": "Offer", "price": "25.00", "priceCurrency": "EUR",
                                        "availability": "https://schema.org/InStock",
                                        "url": "https://shop.example.com/p/p_1"})
        self.assertEqual(ld["material"], "60% cotton, 40% polyester")
        self.assertNotIn("gtin", ld)
        self.assertNotIn("description", ld)

    def test_api_optimize_and_publish_needs_merchant(self):
        r = client.post("/v1/optimize", json={"product": RECORD, "language": "es", "gaps": GAPS})
        self.assertEqual(r.status_code, 200, r.text)
        s = r.json()
        self.assertEqual(s["status"], "draft")
        sug = {k: s[k] for k in ("language", "title", "description", "json_ld")}
        body = {"product": RECORD, "suggestion": sug, "actor": "operator@x"}
        r = client.post("/v1/optimize/publish", json=body)
        self.assertEqual(r.status_code, 403)
        aid = r.json()["detail"]["approval_id"]
        tok = {"X-Governance-Token": "t0k"}
        self.assertEqual(client.post("/v1/approvals", json={"approval_id": aid, "approver": "ops@x",
                                                            "role": policy.OPERATOR}, headers=tok).status_code, 409)
        self.assertEqual(client.post("/v1/approvals", json={"approval_id": aid, "approver": "merchant@x",
                                                            "role": policy.MERCHANT}, headers=tok).status_code, 200)
        r = client.post("/v1/optimize/publish", json=dict(body, approval_id=aid))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["approved_by"], "merchant@x")
        changed = dict(body, approval_id=aid, suggestion=dict(sug, title="Northwind Everyday Tee"))
        self.assertEqual(client.post("/v1/optimize/publish", json=changed).status_code, 403)  # approval was single-use

    def test_api_publish_rejects_fabrication(self):
        sug = {"language": "en", "title": "Northwind Everyday Tee", "description": "Waterproof. Made in Italy.",
               "json_ld": json_ld(product_truth(RECORD))}
        r = client.post("/v1/optimize/publish", json={"product": RECORD, "suggestion": sug, "actor": "m@x"})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(any(e["action"] == "fabricate_claims" and e["outcome"] == "denied" for e in audit.entries(20)))
        bad_ld = dict(sug, description="Regular fit.", json_ld=dict(sug["json_ld"], award="Best tee"))
        self.assertEqual(client.post("/v1/optimize/publish",
                                     json={"product": RECORD, "suggestion": bad_ld, "actor": "m@x"}).status_code, 422)

    def test_api_bad_language(self):
        self.assertEqual(client.post("/v1/optimize", json={"product": RECORD, "language": "fr"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
