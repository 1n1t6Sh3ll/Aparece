"""Unit tests for the collector's deterministic rules (no network).

Run from the repo root: python -m unittest discover -s dataset/tests -v
"""
import json
import sys
import unittest
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATASET / "collect"))

from jsonschema import Draft202012Validator  # noqa: E402

from extract import build_raw, canonical_key, html_lines  # noqa: E402
from fetch import robots_allows  # noqa: E402
from normalize import (FIT, NECKLINE, SLEEVE, is_size_option, lang_code, map_availability, match_lookup,  # noqa: E402
                       normalize_color, normalize_size, parse_composition, parse_weight, primary_material,
                       build_normalized)
from run import is_shirt  # noqa: E402


class Materials(unittest.TestCase):
    def test_percentages(self):
        self.assertEqual(parse_composition("Composition: 55% hemp, 45% Tencel")[0], {"hemp": 55, "other": 45})
        self.assertEqual(parse_composition("100% algodón orgánico")[0], {"organic_cotton": 100})
        self.assertEqual(parse_composition("Cotton 95% Elastane 5%")[0], {"cotton": 95, "elastane": 5})
        self.assertEqual(parse_composition("91% Organic Cotton")[0], None)  # does not sum to 100 on its own
        self.assertEqual(parse_composition("100% ecovero viscose")[0], {"viscose": 100})

    def test_cotton_is_not_organic_without_claim(self):
        self.assertEqual(parse_composition("100% cotton")[0], {"cotton": 100})

    def test_marketing_percentages_ignored(self):
        self.assertEqual(parse_composition("It needs 95% less water than cotton"), (None, None))

    def test_span_is_exact_substring(self):
        line = "Fabric: 60% cotton, 40% polyester (soft)"
        self.assertIn(parse_composition(line)[1], line)

    def test_primary(self):
        self.assertEqual(primary_material({"cotton": 60, "polyester": 40}), "cotton")
        self.assertIsNone(primary_material({"cotton": 50, "linen": 50}))
        self.assertIsNone(primary_material({}))


class Weight(unittest.TestCase):
    def test_gsm_direct(self):
        self.assertEqual(parse_weight("Tejido: algodón, gramaje 220 gsm")[:3], (220, "220 gsm", "direct"))
        self.assertEqual(parse_weight("180 g/m²")[0], 180)

    def test_oz_conversion(self):
        self.assertEqual(parse_weight("8.5 oz/yd² cotton")[:4], (288, "8.5 oz/yd²", "conversion", 1.0))
        self.assertEqual(parse_weight("6.5 oz cotton jersey")[:4], (220, "6.5 oz", "conversion", 0.9))

    def test_ambiguous_oz_not_converted(self):
        self.assertIsNone(parse_weight("The shirt weighs 8 oz fabric")[0])
        self.assertIsNone(parse_weight("no weight here"))


class Lookups(unittest.TestCase):
    def test_lang_code(self):
        for tag, want in (("en-US", "en"), ("EN", "en"), ("es_MX", "es"), (" es-419 ", "es"), ("other", "other"),
                          ("", None), (None, None), (5, None)):
            self.assertEqual(lang_code(tag), want, tag)

    def test_fit(self):
        self.assertEqual(match_lookup("Camiseta oversize", FIT)[0][0], "oversized")
        self.assertEqual(match_lookup("Regular fit", FIT)[0][0], "regular")
        self.assertEqual(match_lookup("regular length", FIT), [])

    def test_sleeve(self):
        self.assertEqual(match_lookup("→ Manga corta", SLEEVE)[0][0], "short")
        self.assertEqual(match_lookup("Long Sleeve Shirts", SLEEVE)[0][0], "long")

    def test_neckline(self):
        self.assertEqual(match_lookup("Cuello redondo", NECKLINE)[0][0], "crew")
        self.assertEqual(match_lookup("V-neckline with shirt collar", NECKLINE)[0][0], "v_neck")

    def test_colors_and_sizes(self):
        self.assertEqual(normalize_color("Snow White"), "white")
        self.assertEqual(normalize_color("azul marino"), "navy")
        self.assertIsNone(normalize_color("dark blue with white"))
        self.assertIsNone(normalize_color("Northern Lights"))
        self.assertEqual(normalize_size("xl"), "XL")
        self.assertIsNone(normalize_size("44 XL"))
        self.assertTrue(is_size_option("Title", "M"))
        self.assertFalse(is_size_option("Title", "Default Title"))

    def test_availability(self):
        self.assertEqual(map_availability("http://schema.org/InStock"), "in_stock")
        self.assertEqual(map_availability("false"), "out_of_stock")
        self.assertIsNone(map_availability(None))


class Collection(unittest.TestCase):
    def test_shirt_filter(self):
        self.assertTrue(is_shirt({"title": "Flex Tee - Grey", "product_type": "Tops_T-shirts"}, tees_only=True))
        self.assertFalse(is_shirt({"title": "Camiseta polo henley", "product_type": "Camisetas"}, tees_only=True))
        self.assertFalse(is_shirt({"title": "True Regular Fit Tee 3-Pack", "product_type": "T-shirts"}))
        self.assertFalse(is_shirt({"title": "Organic Sweatshirt", "product_type": "Sweatshirts"}))
        self.assertTrue(is_shirt({"title": "Guayabera Short Sleeve", "product_type": ""}))

    def test_robots(self):
        txt = "User-agent: *\nDisallow: /cart\nDisallow: /*/products/*-remote\nAllow: /cart/ok$\n"
        self.assertTrue(robots_allows(txt, "/products/tee"))
        self.assertFalse(robots_allows(txt, "/cart/x"))
        self.assertTrue(robots_allows(txt, "/cart/ok"))
        self.assertFalse(robots_allows(txt, "/en/products/a-remote"))

    def test_canonical_and_text(self):
        self.assertEqual(canonical_key("HTTPS://Shop.COM/products/a/?v=1#x"), "https://shop.com/products/a")
        self.assertEqual(html_lines("<p>A &amp; B</p><ul><li>one  <b>two</b></li></ul>"), ["A & B", "one two"])


class EndToEnd(unittest.TestCase):
    """A synthetic Shopify product + page must yield schema-valid records with resolvable evidence."""

    def test_no_variants_availability_unknown(self):
        raw = build_raw({"title": "Plain Tee"}, "<html lang='en'><title>Plain Tee</title></html>", "https://shop.com/p/t",
                        "https://shop.com/p/t", {"merchant": "Shop", "domain": "shop.com"}, "2026-09-29T00:00:00Z")
        self.assertIsNone(raw["raw_availability_text"])
        self.assertIsNone(build_normalized(raw)["commerce"]["availability"])

    def test_records_validate(self):
        product = {"title": "Heavy Tee Black", "handle": "heavy-tee", "vendor": "Shop", "product_type": "T-Shirts",
                   "body_html": "<p>Oversized tee.</p><ul><li>100% organic cotton</li><li>240 gsm</li><li>Short sleeves</li></ul>",
                   "options": [{"name": "Size"}], "images": [],
                   "variants": [{"id": 1, "title": "M", "option1": "M", "sku": "T-M", "price": "30.00", "available": True}]}
        html = ('<html lang="en"><head><title>Heavy Tee</title><link rel="canonical" href="https://shop.com/products/heavy-tee">'
                '<script type="application/ld+json">{"@type":"Product","name":"Heavy Tee Black","brand":{"name":"Shop"},'
                '"offers":[{"@type":"Offer","price":"30.00","priceCurrency":"EUR","sku":"T-M","availability":"https://schema.org/InStock"}]}</script>'
                '</head><body><h1>Heavy Tee Black</h1></body></html>')
        raw = build_raw(product, html, "https://shop.com/products/heavy-tee", "https://shop.com/products/heavy-tee",
                        {"merchant": "Shop", "domain": "shop.com"}, "2026-09-29T00:00:00Z")
        norm = build_normalized(raw)
        for name, rec in (("raw_record", raw), ("normalized_record", norm)):
            schema = json.loads((DATASET / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))
            self.assertEqual([e.message for e in Draft202012Validator(schema).iter_errors(rec)], [])
        self.assertEqual(norm["materials"]["material_percentages"], {"organic_cotton": 100})
        self.assertEqual(norm["materials"]["fabric_weight_gsm"], 240)
        self.assertEqual(norm["fit_and_style"]["fit"], "oversized")
        self.assertEqual(norm["identity"]["product_type"], "t_shirt")
        self.assertEqual(norm["commerce"]["currency"], "EUR")
        from run import evidence_errors
        self.assertEqual(evidence_errors(raw, norm), [])


if __name__ == "__main__":
    unittest.main()
