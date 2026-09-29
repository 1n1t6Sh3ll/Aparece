"""Amazon Reviews 2023 source: filter, raw mapping, normalize + validate, dedupe (no network)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "collect"))

from amazon_source import build_raw_amazon, clean, collect, errors, is_tee, normalize_amazon  # noqa: E402

META = {
    "main_category": "AMAZON FASHION", "title": "Men's Crew Neck Short Sleeve Regular Fit T-Shirt",
    "average_rating": 4.5, "rating_number": 120,
    "features": ["60% Cotton, 40% Polyester", "Machine Wash"], "description": ["Soft everyday tee."],
    "price": 14.99, "store": "Acme", "categories": ["Clothing, Shoes & Jewelry", "Men", "Clothing", "Shirts", "T-Shirts"],
    "details": {"Fabric Type": "60% Cotton, 40% Polyester", "Department": "mens"},
    "images": [{"large": "https://m.media-amazon.com/images/I/a.jpg", "hi_res": None, "variant": "MAIN"}],
    "parent_asin": "B0TEST0001",
}
TS = "2026-01-01T00:00:00Z"


class Amazon(unittest.TestCase):
    def test_filter_keeps_tees_only(self):
        self.assertTrue(is_tee(META))
        self.assertFalse(is_tee({**META, "title": "Men's Polo Shirt"}))
        self.assertFalse(is_tee({**META, "title": "Graphic Tee Hoodie"}))
        self.assertFalse(is_tee({**META, "categories": ["Clothing, Shoes & Jewelry", "Women", "Shoes"]}))

    def test_raw_keeps_original_values_and_validates(self):
        raw = build_raw_amazon(META, TS)
        self.assertEqual(raw["raw_product_name"], META["title"])
        self.assertEqual(raw["raw_bullet_points"], META["features"])
        self.assertEqual(raw["raw_breadcrumbs"], META["categories"])
        self.assertEqual(raw["raw_price_text"], "14.99")
        self.assertEqual(raw["raw_material_text"], "60% Cotton, 40% Polyester")
        self.assertIsNone(raw["raw_shipping_text"])
        norm = normalize_amazon(raw)
        self.assertEqual(errors(raw, norm), [])
        self.assertEqual(norm["materials"]["material_percentages"], {"cotton": 60, "polyester": 40})
        self.assertEqual(norm["variants"]["product_group_id"], "B0TEST0001")
        self.assertEqual(norm["fit_and_style"]["sleeve_length"], "short")

    def test_dedupe_brand_cap_and_reject(self):
        lines = [META, META, {**META, "parent_asin": "B0TEST0002", "title": "Acme Graphic Tee"},
                 {**META, "parent_asin": "B0TEST0003", "title": "Acme V-Neck Tee"},
                 {**META, "parent_asin": "B0TEST0004", "store": "Other", "title": "Plain Tee", "price": None}]
        rows, scanned = collect(lines, target=10, per_brand=2, scraped_at=TS)
        self.assertEqual(scanned, 5)
        self.assertEqual([r["sku"] for r, _, _ in rows], ["B0TEST0001", "B0TEST0002", "B0TEST0004"])
        kept = clean([n for _, n, _ in rows])
        self.assertEqual([n["commerce"]["sku"] for n in kept], ["B0TEST0001", "B0TEST0002"])  # no price -> reject


if __name__ == "__main__":
    unittest.main()
