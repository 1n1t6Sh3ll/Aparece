import unittest
from pathlib import Path

from benchmark.match import load_catalog
from benchmark.metrics import (claim_accuracy_passthrough, competitor_win_rate,
                               language_visibility_gap)

CATALOG = str(Path(__file__).resolve().parent.parent / "examples" / "catalog.example.jsonl")


def resp(text, lang="en", model="m1"):
    return {"provider": "mock", "model": model, "prompt_id": "p", "variant": 0,
            "language": lang, "response_text": text}


class CompetitorMetricTests(unittest.TestCase):
    def setUp(self):
        self.products = load_catalog(CATALOG)

    def test_cwr(self):
        recs = [resp("1. Solana Basics Heavy Tee\n2. NW Classic Tee"),   # A first
                resp("1. NW Classic Tee\n2. Solana Basics Heavy Tee"),   # B first
                resp("1. Solana Basics Heavy Tee"),                      # A only
                resp("nothing relevant")]                                # no contest
        out = competitor_win_rate(recs, self.products, "p_solana_heavy", "p_nw_classic_com")
        o = out["overall"]
        self.assertEqual((o["a_wins"], o["b_wins"], o["contests"], o["responses"]), (2, 1, 3, 4))
        self.assertAlmostEqual(o["cwr"], 0.6667)
        rev = competitor_win_rate(recs, self.products, "p_nw_classic_com", "p_solana_heavy")
        self.assertAlmostEqual(rev["overall"]["cwr"], 0.3333)
        none = competitor_win_rate([resp("x")], self.products, "p_solana_heavy", "p_nw_classic_com")
        self.assertIsNone(none["overall"]["cwr"])

    def test_lvg(self):
        recs = [resp("1. Solana Basics Heavy Tee"), resp("nada"),
                resp("nada", lang="es"), resp("nada", lang="es")]
        g = language_visibility_gap(recs, self.products)["models"]["m1"]["p_solana_heavy"]
        self.assertEqual((g["v_en"], g["v_es"], g["lvg"]), (0.5, 0.0, 0.5))
        only_en = language_visibility_gap([resp("x")], self.products)["models"]["m1"]["p_solana_heavy"]
        self.assertIsNone(only_en["lvg"])

    def test_claim_passthrough(self):
        rep = {"overall": {"claim_accuracy": 0.8},
               "models": {"m1": {"claim_accuracy": 0.75, "languages": {"en": {"claim_accuracy": 1.0}}}}}
        out = claim_accuracy_passthrough(rep)
        self.assertEqual(out["overall"], 0.8)
        self.assertEqual(out["models"]["m1"], {"claim_accuracy": 0.75, "languages": {"en": 1.0}})


if __name__ == "__main__":
    unittest.main()
