"""Keyword boost: boosted text never contains an ungrounded word (fixture: viscose, crew neck, short sleeve, men)."""
import json
import unittest
from pathlib import Path

from benchmark.shootout import boost, score
from optimizer import guard
from optimizer.truth import fallback_title, fact_sentences, product_truth

FIX = Path(__file__).parent / "fixtures_guard_record.json"
PROMPTS = [{"text": t} for t in (
    "Can you recommend an oversized organic cotton unisex t-shirt with a crew neck?",
    "Busco una camiseta de algodon organico oversize con cuello redondo y manga corta",
    "Best printed short sleeve tee, heavy 220 gsm cotton")]


def truth_of(lang="en"):
    return product_truth(json.loads(FIX.read_text(encoding="utf-8"))), lang


class BoostTests(unittest.TestCase):
    def run_boost(self, lang):
        truth, _ = truth_of()
        title, desc = fallback_title(truth, lang), " ".join(fact_sentences(truth, lang))
        return truth, title, desc, boost.boost(truth, lang, PROMPTS, title, desc)

    def test_boosted_text_is_grounded_and_title_in_range(self):
        for lang in ("en", "es"):
            truth, title, desc, (bt, bd) = self.run_boost(lang)
            self.assertFalse(any(r["problems"] for r in guard.check_title(bt, truth)), bt)
            self.assertFalse(any(r["problems"] for r in guard.check_text(bd, truth)), bd)
            self.assertLessEqual(len(bt), score.TITLE_RANGE[1])
            self.assertGreaterEqual(len(bt), score.TITLE_RANGE[0])

    def test_ungrounded_keywords_are_never_added(self):
        truth, title, desc, (bt, bd) = self.run_boost("en")
        for word in ("cotton", "organic", "oversized", "unisex", "printed", "gsm", "algodon"):
            self.assertNotIn(word, (bt + " " + bd).lower())

    def test_grounded_keywords_are_added(self):
        truth, title, desc, (bt, bd) = self.run_boost("en")
        self.assertIn("t-shirt", bd.lower())  # type word is a neutral, grounded keyword
        self.assertNotIn("t-shirt", desc.lower())

    def test_supported_keyword_appears_when_fact_exists(self):
        truth, _ = truth_of()
        truth["facts"]["fit_and_style.fit"] = "oversized"
        truth["facts"]["materials.fabric_weight_gsm"] = 220
        truth["sources"]["fit_and_style.fit"] = ["Oversized fit"]
        truth["sources"]["materials.fabric_weight_gsm"] = ["220 gsm"]
        bt, bd = boost.boost(truth, "en", PROMPTS, "EDUARDO RIVERA Laredo black short sleeve t-shirt - viscose",
                             " ".join(fact_sentences(truth, "en")))
        self.assertIn("oversized", (bt + bd).lower())
        self.assertFalse(any(r["problems"] for r in guard.check_text(bd, truth)))

    def test_idempotent_and_never_worse_for_guard(self):
        truth, title, desc, (bt, bd) = self.run_boost("en")
        self.assertEqual(boost.boost(truth, "en", PROMPTS, bt, bd)[0], bt)


if __name__ == "__main__":
    unittest.main()
