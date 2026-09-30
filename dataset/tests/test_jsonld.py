"""Lenient JSON-LD reading and non-JSON-LD product fallbacks (no network).

Run from the repo root: python -m unittest discover -s dataset/tests -v
"""
import sys
import unittest
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DATASET / "collect"))

from bs4 import BeautifulSoup  # noqa: E402

from extract import build_raw, json_ld_nodes, ld_type, lenient_json  # noqa: E402
from normalize import build_normalized  # noqa: E402

CT = (Path(__file__).parent / "fixtures" / "charles_tyrwhitt_pdp.html").read_text(encoding="utf-8")
CT_URL = "https://www.charlestyrwhitt.com/us/non-iron-stretch-trafalgar-weave-shirt---sky-blue/FOA0026SKY.html"
STORE = {"merchant": "example", "domain": "example.com"}


def nodes(html):
    return json_ld_nodes(BeautifulSoup(html, "html.parser"))[1]


def product(html):
    return next((n for n in nodes(html) if ld_type(n, "Product")), None)


def page(script, attrs='type="application/ld+json"'):
    return f"<html><head><script {attrs}>{script}</script></head><body></body></html>"


class LenientJson(unittest.TestCase):
    def test_malformed_variants(self):
        good = '{"@type": "Product", "name": "Tee", "offers": {"price": "20"}}'
        cases = {
            "comment": f"<!-- {good} -->",
            "cdata": f"//<![CDATA[\n{good}\n//]]>",
            "trailing commas": '{"@type": "Product", "name": "Tee", "offers": {"price": "20",},}',
            "control chars": '{"@type": "Product", "name": "Te\x01e\x0b", "offers": {"price": "20"}}',
            "raw newline in string": '{"@type": "Product", "name": "Tee\nshirt", "offers": {"price": "20"}}',
            "two objects": '{"@type": "Organization", "name": "Shop"}\n' + good,
            "array": f'[{{"@type": "WebSite"}}, {good}]',
            "graph": f'{{"@context": "https://schema.org", "@graph": [{{"@type": "BreadcrumbList"}}, {good}]}}',
            "nested graph list": f'[{{"@graph": [[{good}]]}}]',
        }
        for label, script in cases.items():
            with self.subTest(label):
                p = product(page(script))
                self.assertIsNotNone(p, label)
                self.assertNotIn("@fallback", p)
                self.assertTrue(p["name"].startswith("Te"))

    def test_script_type_spelling(self):
        good = '{"@type": ["Thing", "Product"], "name": "Tee"}'
        for attrs in ("type='application/ld+json'", 'data-x="1" type=application/ld+json',
                      'type=" Application/LD+JSON; charset=utf-8 "'):
            with self.subTest(attrs):
                self.assertIsNotNone(product(page(good, attrs)))

    def test_type_url_forms(self):
        self.assertIsNotNone(product(page('{"@type": "https://schema.org/Product", "name": "Tee"}')))
        self.assertIsNotNone(product(page('{"@type": "schema:Product", "name": "Tee"}')))

    def test_garbage_is_skipped(self):
        self.assertEqual(lenient_json("not json at all"), [])
        self.assertEqual(lenient_json('{"a": 1} trailing {"b": 2}'), [{"a": 1}, {"b": 2}])


class Fallbacks(unittest.TestCase):
    def test_meta_tags(self):
        html = ('<html><head><meta property="og:type" content="product"><meta property="og:title" content="Linen Shirt">'
                '<meta property="product:price:amount" content="45,00"><meta property="product:price:currency" content="EUR">'
                '</head><body><h1>Other</h1></body></html>')
        p = product(html)
        self.assertEqual((p["name"], p["offers"]["price"], p["offers"]["priceCurrency"], p["@fallback"]),
                         ("Linen Shirt", "45.00", "EUR", "page_markup"))

    def test_microdata(self):
        html = ('<html><body><nav itemscope itemtype="http://schema.org/BreadcrumbList"><span itemprop="name">Home</span></nav>'
                '<div itemscope itemtype="https://schema.org/Product"><h1 itemprop="name">Camiseta lisa</h1>'
                '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer"><span itemprop="price" content="9.95">9,95 €</span>'
                '<meta itemprop="priceCurrency" content="EUR"><link itemprop="availability" href="https://schema.org/InStock"></div>'
                '</div></body></html>')
        p = product(html)
        self.assertEqual((p["name"], p["offers"]["price"], p["offers"]["priceCurrency"], p["@fallback"]),
                         ("Camiseta lisa", "9.95", "EUR", "microdata"))

    def test_no_price_no_product(self):
        self.assertIsNone(product("<html><head><title>About</title></head><body><h1>Our story</h1></body></html>"))

    def test_json_ld_product_wins(self):
        html = page('{"@type": "Product", "name": "Real"}').replace("</head>", '<meta property="product:price:amount" content="1"></head>')
        self.assertEqual(product(html)["name"], "Real")


class CharlesTyrwhitt(unittest.TestCase):
    """Saved page whose Product JSON-LD is built in JavaScript from hidden js-product-markup-* spans."""

    def raw(self):
        p = product(CT)
        prod = {"title": p["name"], "variants": [{"id": "1", "price": p["offers"]["price"], "available": True}],
                "body_html": f"<p>{p['description']}</p>"}
        return build_raw(prod, CT, CT_URL, CT_URL, STORE, "2026-09-29T00:00:00Z")

    def test_fallback_product(self):
        p = product(CT)
        self.assertEqual(p["name"], "Non-Iron Stretch Trafalgar Weave Shirt - Sky Blue")
        self.assertEqual((p["offers"]["price"], p["offers"]["priceCurrency"], p["sku"]), ("139.00", "USD", "FOA0026SKY"))
        self.assertEqual(p["aggregateRating"]["ratingValue"], "5")

    def test_normalized(self):
        raw = self.raw()
        self.assertEqual(raw["raw_title"], "Non-Iron Stretch Trafalgar Weave Shirt - Sky Blue | Charles Tyrwhitt US")
        n = build_normalized(raw)
        self.assertEqual(n["identity"]["product_type"], "long_sleeve_shirt")
        self.assertEqual((n["commerce"]["price"], n["commerce"]["currency"]), (139.0, "USD"))
        self.assertEqual(n["materials"]["material_percentages"], {"cotton": 100})
        sd = n["structured_data"]
        self.assertFalse(sd["product_schema_present"])  # read from page markup, not JSON-LD
        self.assertFalse(sd["offer_schema_present"])
        self.assertEqual(len(sd["raw_json_ld"]), 1)  # the Organization block


class DressShirtType(unittest.TestCase):
    def norm(self, name, desc=""):
        prod = {"title": name, "variants": [{"id": "1", "price": "50"}], "body_html": f"<p>{desc}</p>"}
        html = page('{"@type": "Product", "name": "%s", "offers": {"price": "50", "priceCurrency": "USD"}}' % name)
        return build_normalized(build_raw(prod, html, "https://s.example/p", "https://s.example/p", STORE, "2026-09-29T00:00:00Z"))

    def test_types(self):
        for name, desc, want in (("Slim Fit Dress Shirt", "", "long_sleeve_shirt"),
                                 ("Non-Iron Twill Shirt", "", "long_sleeve_shirt"),
                                 ("Non-iron dress shirt", "Short sleeve.", "short_sleeve_shirt"),
                                 ("Camisa de vestir blanca", "", "long_sleeve_shirt"),
                                 ("Non-iron T-shirt", "", "t_shirt"),
                                 ("Oxford Shirt", "", "oxford")):
            with self.subTest(name):
                self.assertEqual(self.norm(name, desc)["identity"]["product_type"], want)


if __name__ == "__main__":
    unittest.main()
