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
