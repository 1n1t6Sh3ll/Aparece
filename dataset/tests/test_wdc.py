"""Unit tests for the WDC N-Quads adapter (no network). Run: python -m unittest discover -s dataset/tests -v"""
import json
import sys
import unittest
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATASET / "collect"))

from jsonschema import Draft202012Validator  # noqa: E402

from wdc import (build_normalized_wdc, build_raw_wdc, decode, detect_language, is_tee, page_nodes,  # noqa: E402
                 pages, parse_quad, products, to_tree)

PAGE = "https://shop.example.com/products/tee"
LINES = f"""_:b0 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Product> <{PAGE}>   .
_:b0 <http://schema.org/name> "Organic Tee \\"Classic\\" caf\\u00E9 &amp; co" <{PAGE}>   .
_:b0 <http://schema.org/description> "Relaxed fit crew neck.\\n100% organic cotton, 180 gsm." <{PAGE}>   .
_:b0 <http://schema.org/brand> _:b2 <{PAGE}>   .
_:b0 <http://schema.org/Offers> _:b1 <{PAGE}>   .
_:b0 <http://schema.org/image> <https://cdn.example.com/tee.jpg> <{PAGE}>   .
_:b1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://schema.org/Offer> <{PAGE}>   .
_:b1 <http://schema.org/price> "25.00" <{PAGE}>   .
_:b1 <http://schema.org/priceCurrency> "USD" <{PAGE}>   .
_:b1 <http://schema.org/Availability> "https://schema.org/InStock" <{PAGE}>   .
_:b2 <http://schema.org/name> "Acme" <{PAGE}>   .
""".splitlines()


def schema(name):
    return Draft202012Validator(json.loads((DATASET / "schema" / name).read_text(encoding="utf-8")))


class QuadParser(unittest.TestCase):
    def test_literal_iri_bnode(self):
        s, p, o, g = parse_quad(LINES[1])
        self.assertEqual((s, p, g), ("_:b0", "http://schema.org/name", PAGE))
        self.assertEqual(o, ("lit", 'Organic Tee "Classic" café &amp; co'))  # N-Quads escapes decoded, HTML kept
        self.assertEqual(parse_quad(LINES[5])[2], ("iri", "https://cdn.example.com/tee.jpg"))
        self.assertEqual(parse_quad(LINES[3])[2], ("bnode", "_:b2"))

    def test_typed_and_language_literals(self):
        q = parse_quad(f'_:x <http://schema.org/name> "true"^^<http://www.w3.org/2001/XMLSchema#boolean> <{PAGE}> .')
        self.assertEqual(q[2], ("lit", "true"))
        q = parse_quad(f'_:x <http://schema.org/name> "Camiseta"@es <{PAGE}> .')
        self.assertEqual(q[2], ("lit", "Camiseta"))

    def test_malformed_is_none(self):
        self.assertIsNone(parse_quad("not a quad"))
        self.assertIsNone(parse_quad(""))

    def test_tree_and_top_level_product(self):
        nodes = page_nodes([parse_quad(ln) for ln in LINES])
        self.assertEqual(products(nodes), ["_:b0"])
        tree = to_tree(nodes, "_:b0")
        self.assertEqual(tree["offers"]["priceCurrency"], "USD")  # 'Offers' -> 'offers'
        self.assertEqual(tree["brand"]["name"], "Acme")

    def test_pages_group_by_graph(self):
        other = LINES[1].replace(PAGE, "https://other.example.org/p")
        got = list(pages(LINES + [other]))
        self.assertEqual([g for g, _ in got], [PAGE, "https://other.example.org/p"])
        self.assertEqual(len(got[0][1]), len(LINES))


class Records(unittest.TestCase):
    def test_raw_and_normalized_validate(self):
        nodes = page_nodes([parse_quad(ln) for ln in LINES])
        raw = build_raw_wdc(to_tree(nodes, "_:b0"), PAGE)
        norm = build_normalized_wdc(raw)
        self.assertEqual(list(schema("raw_record.schema.json").iter_errors(raw)), [])
        self.assertEqual(list(schema("normalized_record.schema.json").iter_errors(norm)), [])
        self.assertEqual((raw["merchant_domain"], raw["raw_price_text"], raw["brand"]), ("shop.example.com", "25.00", "Acme"))
        self.assertIsNone(raw["raw_title"])  # no page HTML in WDC
        self.assertEqual(norm["identity"]["product_name"], 'Organic Tee "Classic" café & co')
        self.assertEqual(norm["materials"]["material_percentages"], {"organic_cotton": 100})
        self.assertEqual((norm["fit_and_style"]["fit"], norm["commerce"]["availability"]), ("relaxed", "in_stock"))

    def test_filters_and_language(self):
        self.assertTrue(is_tee("Playera Dri-Fit", None))
        self.assertFalse(is_tee("Golf Tees 50 pack", None))
        self.assertFalse(is_tee("T-shirt SVG download", None))
        self.assertFalse(is_tee("Hoodie", "T-Shirts"))
        self.assertEqual(detect_language("Camiseta de algodón con manga corta para hombre"), "es")
        self.assertEqual(detect_language("Soft cotton tee made for you and your friends"), "en")
        self.assertEqual(decode("Caf&amp;amp;e \\u00e9"), "Caf&e é")


if __name__ == "__main__":
    unittest.main()
