"""Guardrail fairness: harmless restatements of verified facts pass; real unsupported claims are still caught."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "api"), str(ROOT / "dataset" / "collect")]

from benchmark.shootout import score  # noqa: E402
from optimizer import guard  # noqa: E402


FIX = Path(__file__).parent / "fixtures_guard_record.json"  # a real audited record, facts only (no page prose)


def truth():
    import json
    from optimizer.truth import product_truth
    return product_truth(json.loads(FIX.read_text(encoding="utf-8")))


def problems(sentence):
    return guard.check_sentence(sentence, truth())[1]


class GuardFairnessTests(unittest.TestCase):
    def test_possessive_of_verified_word_passes(self):
        self.assertEqual(problems("Men's short sleeve t-shirt in black with a crew neck."), [])

    def test_verified_care_temperatures_pass(self):
        self.assertEqual(problems("Wash at 30°C maximum, iron at 110°C maximum."), [])

    def test_unverified_care_temperature_is_caught(self):
        self.assertTrue(problems("Wash at 60°C."))

    def test_marketing_claims_still_caught(self):
        self.assertTrue(problems("Made from premium viscose, it ensures a soft and breathable feel."))

    def test_navy_blue_is_one_colour(self):
        from benchmark import claims
        cols = [v for f, v in claims.extract_claims("A navy blue knit polo.") if f == "variants.colors"]
        self.assertEqual(cols, ["navy"])

    def test_tag_naming_the_product_passes(self):
        out = score.tags_audit(["Laredo t-shirt", "EDUARDO RIVERA"], truth(), "en", [])
        self.assertEqual(out["false"], [])

    def test_tag_with_unsupported_claim_is_caught(self):
        out = score.tags_audit(["organic cotton"], truth(), "en", [])
        self.assertEqual(out["false"], ["organic cotton"])


if __name__ == "__main__":
    unittest.main()
