"""Validate the T-shirt AI-visibility prompt set (benchmark/prompts)."""
import csv
import re
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from benchmark.harness import load_prompts
from benchmark.prompts.split import assign_splits

ROOT = Path(__file__).resolve().parents[2]
PDIR = ROOT / "benchmark" / "prompts"
MARKETS = {"en": {"US", "GB"}, "es": {"ES", "MX"}}
CURRENCY = {r"\$": "US", "£": "GB", r"\beuros?\b": "ES", r"\bpesos?\b": "MX"}
# Our dataset merchants plus well-known apparel brands/trademarks that would lead the model.
EXTRA_BRANDS = ["Northwind", "Solana Basics", "Uniqlo", "Hanes", "Gildan", "Fruit of the Loom", "Comfort Colors",
                "Bella+Canvas", "Champion", "Carhartt", "Patagonia", "Everlane", "Nike", "Adidas", "Puma", "Under Armour",
                "Lululemon", "Zara", "H&M", "Primark", "Mango", "Pull&Bear", "Bershka", "Lacoste", "Ralph Lauren",
                "Levi's", "Gap", "Icebreaker", "Smartwool", "Asket", "Kotn", "Pact", "Quince", "Buck Mason", "Decathlon",
                "Supima", "Tencel", "Dri-FIT", "CrossFit", "Lycra", "Coolmax", "Gore-Tex"]


def brands():
    with open(ROOT / "dataset" / "collect" / "stores.csv", encoding="utf-8") as f:
        merchants = [r["merchant"] for r in csv.DictReader(f)]
    return merchants + EXTRA_BRANDS


class PromptSetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pub = load_prompts(PDIR / "tshirts.jsonl")
        cls.hid = load_prompts(PDIR / "hidden.jsonl")
        cls.rows = cls.pub + cls.hid

    def test_unique_ids_and_120_intents(self):
        ids = [r["id"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len({r["canonical_intent"] for r in self.rows}), 120)
        self.assertTrue(all(re.fullmatch(r"INTENT_\d{3}", r["canonical_intent"]) for r in self.rows))

    def test_both_languages_per_intent_and_valid_market(self):
        by = defaultdict(list)
        for r in self.rows:
            by[r["canonical_intent"]].append(r)
            self.assertIn(r["market"], MARKETS[r["language"]], r["id"])
        for intent, rs in by.items():
            self.assertEqual(sorted(r["language"] for r in rs), ["en", "es"], intent)
            self.assertEqual(len({r["split"] for r in rs}), 1, intent)

    def test_split_ratios_deterministic_and_hidden_separate(self):
        self.assertTrue(all(r["split"] == "hidden" for r in self.hid))
        self.assertTrue(all(r["split"] in {"dev", "val"} for r in self.pub))
        expected = assign_splits({r["canonical_intent"] for r in self.rows})
        for r in self.rows:
            self.assertEqual(r["split"], expected[r["canonical_intent"]], r["id"])
        counts = Counter(expected.values())
        self.assertEqual(counts, {"dev": 72, "val": 24, "hidden": 24})

    def test_no_brand_names(self):
        pats = [re.compile(r"(?<!\w)" + re.escape(b) + r"(?!\w)", re.I) for b in brands()]
        for r in self.rows:
            hits = [p.pattern for p in pats if p.search(r["text"])]
            self.assertEqual(hits, [], r["id"])

    def test_currency_matches_market(self):
        for r in self.rows:
            for sym, mkt in CURRENCY.items():
                if re.search(sym, r["text"], re.I):
                    self.assertEqual(r["market"], mkt, r["id"])


if __name__ == "__main__":
    unittest.main()
