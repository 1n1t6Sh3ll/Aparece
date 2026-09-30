import json
import tempfile
import unittest
from pathlib import Path

from benchmark import harness
from benchmark.claims import (CONTRADICTED, SUPPORTED, UNVERIFIABLE, check, check_response, claims_markdown,
                              claims_report, extract_claims)



def record(pid, brand, name, domain, **over):
    rec = {"product_id": pid,
           "source": {"canonical_url": f"https://{domain}/p/{pid}", "merchant_domain": domain, "language": "en"},
           "identity": {"brand": brand, "product_name": name, "audience": None},
           "content": {"full_description": None, "bullet_points": []}, "features": [],
           "materials": {"material_percentages": {}, "fabric_weight_gsm": None},
           "fit_and_style": {"fit": None, "sleeve_length": None, "neckline": None},
           "variants": {"colors": [], "sizes": [], "items": []},
           "commerce": {"price": None, "sale_price": None, "currency": None}, "evidence": []}
    for path, value in over.items():
        sec, key = path.split("__")
        rec[sec][key] = value
    return rec


HEAVY = record("p_heavy", "Solana Basics", "Heavy Tee", "solanabasics.com",
               materials__material_percentages={"cotton": 60, "polyester": 40},
               materials__fabric_weight_gsm=240, fit_and_style__fit="relaxed",
               fit_and_style__sleeve_length="short", commerce__price=25.0, commerce__currency="USD",
               variants__colors=[{"original_color_name": "Black", "normalized": "black"}],
               variants__sizes=[{"raw_size": s, "normalized_size": s} for s in ("S", "M", "L")],
               content__bullet_points=["Made in Portugal", "OEKO-TEX certified"])
HEAVY["evidence"] = [{"field": "materials.material_percentages", "value": {"cotton": 60, "polyester": 40},
                      "source_text": "60% cotton, 40% polyester", "source_location": "raw_bullet_points[0]"}]
ORGANIC = record("p_org", "Northwind Tees", "Classic Organic Tee", "northwindtees.com",
                 materials__material_percentages={"organic_cotton": 100})
GOLD = {r["product_id"]: r for r in (HEAVY, ORGANIC)}


def products():
    return [{"product_id": r["product_id"], "brand": r["identity"]["brand"], "name": r["identity"]["product_name"],
             "url": r["source"]["canonical_url"], "site": r["source"]["merchant_domain"], "aliases": []}
            for r in GOLD.values()]


class ExtractTests(unittest.TestCase):
    def test_extracts_fields(self):
        c = dict((f, v) for f, v in extract_claims(
            "100% cotton, slim fit, long sleeve, 180 gsm, $19.99, in sizes XS-XL. Made in Spain, GOTS certified."))
        self.assertEqual(c["materials.material_percentages"], {"cotton": 100})
        self.assertEqual(c["fit_and_style.fit"], "slim")
        self.assertEqual(c["fit_and_style.sleeve_length"], "long")
        self.assertEqual(c["materials.fabric_weight_gsm"], 180)
        self.assertEqual(c["commerce.price"][0], 19.99)
        self.assertEqual(c["origin"], "spain")
        self.assertEqual(c["certification"], "gots")
        sizes = [v for f, v in extract_claims("sizes XS-XL") if f == "variants.sizes"]
        self.assertEqual(sizes, ["XS", "S", "M", "L", "XL"])

    def test_spanish_price_and_composition(self):
        c = dict(extract_claims("Camiseta de algodón 100%, cuesta 29,90 €. Hecho en España."))
        self.assertEqual(c["materials.material_percentages"], {"cotton": 100})
        self.assertEqual(c["commerce.price"], (29.9, ["EUR"]))
        self.assertEqual(c["origin"], "spain")


class CheckTests(unittest.TestCase):
    def test_composition(self):
        self.assertEqual(check("materials.material_percentages", {"cotton": 100}, HEAVY)[0], CONTRADICTED)
        st, gold, ev = check("materials.material_percentages", {"cotton": 60, "polyester": 40}, HEAVY)
        self.assertEqual((st, ev["source_text"]), (SUPPORTED, "60% cotton, 40% polyester"))
        self.assertEqual(check("materials.material_percentages", {"cotton": 100}, ORGANIC)[0], SUPPORTED)
        self.assertEqual(check("materials.material_percentages", {"organic_cotton": 100},
                               record("x", "a", "b", "c.com", materials__material_percentages={"cotton": 100}))[0],
                         UNVERIFIABLE)

    def test_null_gold_is_unverifiable(self):
        for field, value in (("fit_and_style.fit", "slim"), ("materials.fabric_weight_gsm", 200),
                             ("commerce.price", (20.0, ["USD"])), ("variants.colors", "red"),
                             ("variants.sizes", "XL"), ("origin", "china"), ("certification", "gots")):
            self.assertEqual(check(field, value, ORGANIC)[0], UNVERIFIABLE, field)

    def test_other_fields(self):
        self.assertEqual(check("fit_and_style.fit", "slim", HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("materials.fabric_weight_gsm", 237, HEAVY)[0], SUPPORTED)  # 7 oz
        self.assertEqual(check("materials.fabric_weight_gsm", 150, HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("commerce.price", (24.99, ["AUD", "CAD", "MXN", "USD"]), HEAVY)[0], SUPPORTED)
        self.assertEqual(check("commerce.price", (40.0, ["USD"]), HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("commerce.price", (22.0, ["EUR"]), HEAVY)[0], UNVERIFIABLE)
        self.assertEqual(check("commerce.currency", ["EUR"], HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("variants.colors", "white", HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("variants.sizes", "XXL", HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("origin", "portugal", HEAVY)[0], SUPPORTED)
        self.assertEqual(check("origin", "china", HEAVY)[0], CONTRADICTED)
        self.assertEqual(check("certification", "oeko_tex", HEAVY)[0], SUPPORTED)
        self.assertEqual(check("certification", "gots", HEAVY)[0], UNVERIFIABLE)


MOCK = ("Here are two picks:\n"
        "1. Solana Basics Heavy Tee - 100% cotton, relaxed fit, about $25. Comes in black.\n"
        "2. Northwind Tees Classic Organic Tee (https://northwindtees.com/p/p_org) is made of 100% cotton.\n"
        "   It has a slim fit.\n"
        "3. Some Other Brand Tee - 100% polyester.\n")


class ResponseTests(unittest.TestCase):
    def test_attribution_and_status(self):
        cs = check_response(MOCK, products(), GOLD)
        got = {(c["product_id"], c["field"], c["status"]) for c in cs}
        self.assertIn(("p_heavy", "materials.material_percentages", CONTRADICTED), got)
        self.assertIn(("p_heavy", "fit_and_style.fit", SUPPORTED), got)
        self.assertIn(("p_heavy", "commerce.price", SUPPORTED), got)
        self.assertIn(("p_heavy", "variants.colors", SUPPORTED), got)
        self.assertIn(("p_org", "materials.material_percentages", SUPPORTED), got)
        self.assertIn(("p_org", "fit_and_style.fit", UNVERIFIABLE), got)  # continuation line
        # Item 3 is an unmatched product: its polyester claim is not attributed to Northwind.
        self.assertFalse(any(c["claim"] == {"polyester": 100} for c in cs))

    def test_report_metrics_and_markdown(self):
        recs = [{"provider": "mock", "model": "m1", "language": "en", "prompt_id": "a", "response_text": MOCK},
                {"provider": "mock", "model": "m1", "language": "es", "prompt_id": "b",
                 "response_text": "Solana Basics Heavy Tee: 100% algodón, corte entallado."}]
        rep = claims_report(recs, products(), GOLD)
        m = rep["models"]["m1"]
        self.assertEqual(m["claims"], m["supported"] + m["contradicted"] + m["unverifiable"])
        self.assertAlmostEqual(m["claim_accuracy"] + m["hallucination_rate"], 1.0, places=3)
        es = m["languages"]["es"]
        self.assertEqual((es["supported"], es["contradicted"]), (0, 2))
        self.assertEqual(es["hallucination_rate"], 1.0)
        self.assertTrue(m["examples"][CONTRADICTED])
        md = claims_markdown(rep)
        self.assertIn("Claim accuracy", md)
        self.assertIn("60% cotton, 40% polyester", md)

    def test_harness_report_includes_claims(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "cat.jsonl").write_text("\n".join(json.dumps(r) for r in GOLD.values()), encoding="utf-8")
            (d / "r.jsonl").write_text(json.dumps({"provider": "mock", "model": "m1", "language": "en", "variant": "base",
                                                   "prompt_id": "a", "response_text": MOCK}) + "\n", encoding="utf-8")
            rep = harness.main(["report", "--results", str(d / "r.jsonl"), "--catalog", str(d / "cat.jsonl"),
                                "--out-dir", str(d)])
            self.assertGreater(rep["claims"]["overall"]["contradicted"], 0)
            self.assertIn("Claim accuracy", (d / "report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
