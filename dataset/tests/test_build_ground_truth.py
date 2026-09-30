"""Tests for dataset/build/make_ground_truth.py: evidence check, non-apparel guard, split leakage."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dataset" / "build"))
import make_ground_truth as gt  # noqa: E402

EX = ROOT / "dataset" / "examples"
NORM = json.loads((EX / "normalized_record.example.json").read_text(encoding="utf-8"))
RAW = json.loads((EX / "raw_record.example.json").read_text(encoding="utf-8"))


class EvidenceCheckTest(unittest.TestCase):
    def test_example_evidence_verifies(self):
        drops = gt.collections.Counter()
        gold = gt.target(gt.verify(NORM, RAW, drops))
        self.assertEqual(sum(drops.values()), 0)
        self.assertTrue(any(v is not None for v in gold.values()))

    def test_unsupported_value_becomes_null(self):
        norm = copy.deepcopy(NORM)
        ev = next(e for e in norm["evidence"] if e["field"] in gt.FIELDS)
        ev["source_text"] = "text that is not in the raw record"
        drops = gt.collections.Counter()
        gold = gt.target(gt.verify(norm, RAW, drops))
        self.assertIsNone(gold[ev["field"]])
        self.assertEqual(drops[ev["field"]], 1)

    def test_resolve_path(self):
        raw = {"raw_description": {"sections": [{"text": "a"}, {"text": "100% Cotton"}]}}
        self.assertEqual(gt.resolve(raw, "raw_description.sections[1].text"), "100% Cotton")
        self.assertIsNone(gt.resolve(raw, "raw_description.sections[5].text"))


class GuardTest(unittest.TestCase):
    def test_non_apparel(self):
        self.assertTrue(gt.non_apparel({"raw_title": "Bio schwarzer Tee (100g)"}))
        self.assertTrue(gt.non_apparel({"raw_title": "Green Tea Clear Candle"}))
        self.assertFalse(gt.non_apparel({"raw_title": "Layering Cap Sleeve Tee (Black)"}))
        self.assertFalse(gt.non_apparel({"raw_title": "Coffee Lover T-Shirt"}))
        self.assertFalse(gt.non_apparel({"raw_title": "Luxury Heavy Tee Oversize (240g/m2)"}))


    def test_hardware_and_cd_bundles_dropped(self):
        self.assertTrue(gt.non_apparel({"raw_title": "Propane Tank Y Splitter Adapter Tee Connector"}))
        self.assertTrue(gt.non_apparel({"raw_title": "Love This City CD + T-Shirt"}))
        self.assertFalse(gt.non_apparel({"raw_title": "Album Cover T-Shirt Black"}))

    def test_tank_top_kept_as_other(self):
        raw = {"raw_title": "Women's Racerback Tank Top", "raw_product_name": "Women's Racerback Tank Top"}
        self.assertFalse(gt.non_apparel(raw))
        norm = copy.deepcopy(NORM)
        self.assertTrue(gt.mark_tank(norm, raw))
        self.assertEqual(norm["identity"]["product_type"], "other")
        self.assertEqual(gt.target(gt.verify(norm, raw, gt.collections.Counter()))["identity.product_type"], "other")
        self.assertFalse(gt.mark_tank(copy.deepcopy(NORM), {"raw_title": "Classic Crew Tee"}))


def item(source, domain, brand, title, desc="d"):
    return {"source": source, "language": "en", "gold": {"identity.product_type": "t_shirt"},
            "norm": {"identity": {"brand": brand}, "source": {"merchant_domain": domain}},
            "raw": {"raw_title": title, "raw_full_description": desc}}


class GroupingTest(unittest.TestCase):
    def test_merchant_base(self):
        for d in ("modalova.de", "us.modalova.com", "modalova.co.uk", "www.modalova.com.au"):
            self.assertEqual(gt.merchant_base(d), "modalova")
        self.assertEqual(gt.merchant_base("mundotrabajo.com.uy"), "mundotrabajo")
        self.assertEqual(gt.merchant_base("cool.myshopify.com"), "cool")

    def test_brand_and_text_link_groups_but_tlds_stay_separate(self):
        items = [item("amazon", "amazon.com", "Under Armour", "UA Tech Tee"),
                 item("wdc", "shopa.com", "Under Armour", "UA Tech 2.0"),
                 item("wdc", "shopb.de", "Other", "Exact Dup Tee", "same text"),
                 item("wdc", "shopc.fr", "Third", "Exact  dup tee", "Same text"),
                 item("wdc", "wearmedicine.com", None, "A"),
                 item("wdc", "wearmedicine.com.au", None, "B")]
        gt.assign_groups(items)
        g = [it["group"] for it in items]
        self.assertEqual(g[0], g[1])  # Under Armour on Amazon + WDC -> one group
        self.assertEqual(g[2], g[3])  # identical title+description -> one group
        self.assertNotEqual(g[4], g[5])  # human decision: domain endings stay separate groups
        self.assertEqual(items[4]["merchant_base"], items[5]["merchant_base"])
        for i, it in enumerate(items):
            it["split"] = "test" if i == 5 else "train"
        leak = gt.leakage(items)
        self.assertEqual([leak[k] for k in ("group", "domain", "brand", "title_description")], [0, 0, 0, 0])
        self.assertTrue(items[5]["cross_tld_split"] and items[4]["cross_tld_split"])
        self.assertFalse(items[0]["cross_tld_split"])


class SplitLeakageTest(unittest.TestCase):
    def test_no_group_in_two_splits(self):
        items = []
        for g in range(60):
            for k in range(1 + g % 4):
                items.append({"group": f"domain:d{g}.com", "source": "wdc" if g % 3 else "amazon",
                              "language": "en" if g % 2 else "es",
                              "gold": {"identity.product_type": "t_shirt" if g % 5 else "polo"}})
        split_of = gt.assign_splits(items, seed=1)
        seen = {}
        for it in items:
            self.assertEqual(seen.setdefault(it["group"], it["split"]), it["split"])
        self.assertEqual(set(split_of.values()), set(gt.SPLITS))
        again = [dict(it) for it in items]
        self.assertEqual(gt.assign_splits(again, seed=1), split_of)  # reproducible


if __name__ == "__main__":
    unittest.main()
