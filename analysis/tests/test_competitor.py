import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analysis import competitor as C
from analysis.peers import (SIM_WEIGHTS, similar_peers, similarity_components,
                            token_cosine, weighted_similarity)

EXAMPLE = json.loads((Path(__file__).resolve().parents[2] / "dataset" / "examples"
                      / "normalized_record.example.json").read_text(encoding="utf-8"))


def rec(pid, **over):
    r = copy.deepcopy(EXAMPLE)
    r["product_id"] = pid
    for path, v in over.items():
        sec, key = path.split("__")
        r[sec][key] = v
    return r


class SimilarityTests(unittest.TestCase):
    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(SIM_WEIGHTS.values()), 1.0)

    def test_identical_scores_one_and_unknown_skipped(self):
        a, b = rec("a"), rec("b")
        comp = similarity_components(a, b, text=1.0)
        self.assertIsNone(comp["subcategory"])  # null on both sides: skipped
        self.assertEqual(weighted_similarity(comp), 1.0)

    def test_price_market_language_lower_score(self):
        a = rec("a")
        far = rec("far", commerce__price=250.0)
        es = rec("es", source__language="es", source__merchant_domain="thinkingmu.es")
        ca, cf, ce = (similarity_components(a, x, 1.0) for x in (a, far, es))
        self.assertEqual(cf["price_band"], 0.0)
        self.assertEqual(ce["market"], 0.5)  # TLD differs, currency same
        self.assertEqual(ce["language"], 0.0)
        self.assertLess(weighted_similarity(cf), weighted_similarity(ca))

    def test_ranking_and_text_methods(self):
        a, near = rec("a"), rec("near")
        other = rec("other", identity__product_type="hoodie", fit_and_style__fit="oversized")
        for use in (True, False):
            out = similar_peers(a, [a, other, near], use_sklearn=use)
            self.assertEqual([p["product_id"] for p in out["peers"]], ["near", "other"])
        self.assertEqual(out["text_method"], "token_cosine")
        self.assertAlmostEqual(token_cosine("a b", "a b"), 1.0)
        self.assertIsNone(token_cosine("", "a"))


class CompetitorTests(unittest.TestCase):
    def test_profile_of_example(self):
        p = C.profile(EXAMPLE, [EXAMPLE])
        self.assertIn("productGroupID", C.jsonld_fields(EXAMPLE))
        self.assertEqual(p["independent_evidence"], "not measured")
        self.assertEqual(p["spanish_content"], "none")
        self.assertEqual(p["entity_consistency_pct"], 100.0)
        self.assertEqual(p["contradictions"], 0)
        self.assertGreater(p["verified_facts"], 10)

    def test_spanish_sibling_and_text(self):
        es = rec("es", source__language="es")
        self.assertEqual(C.spanish_content(EXAMPLE, [EXAMPLE, es]), "full")
        es_title = rec("es2", source__language="es", content__full_description=None)
        self.assertEqual(C.spanish_content(EXAMPLE, [es_title]), "partial")
        mixed = rec("m", content__full_description="Camiseta de algodón con manga corta para el verano y la playa")
        mixed["variants"]["product_group_id"] = "other"
        mixed["variants"]["items"] = []
        self.assertEqual(C.spanish_content(mixed, [EXAMPLE]), "partial")

    def test_independent_evidence_counted(self):
        r = rec("r")
        r["evidence"].append({"field": "x", "source_url": "https://www.review.example/a", "confidence": 1.0})
        self.assertEqual(C.independent_evidence(r), 1)

    def test_gap_issues(self):
        target = rec("t", content__h1="Something else entirely", fit_and_style__neckline=None)
        target["structured_data"]["raw_json_ld"] = []
        target["conflicts"] = [{"field": "commerce.price", "status": "conflicting",
                                "observations": [], "resolution": None}]
        target["variants"]["product_group_id"] = "t_grp"
        target["variants"]["items"] = []
        peers = [rec(f"p{i}", source__language="es") for i in range(3)]
        out = C.gap_issues(target, peers, [target] + peers)
        kinds = {(i["kind"], i["type"]) for i in out["issues"]}
        for k in ("missing_attributes", "entity_inconsistency", "incomplete_structured_data",
                  "weak_language_coverage", "factual_contradictions"):
            self.assertIn((k, "OBSERVED_FACT"), kinds)
        self.assertIn(("weak_language_coverage", "SUPPORTED_HYPOTHESIS"), kinds)
        self.assertIn(("independent_evidence", "UNKNOWN"), kinds)
        self.assertEqual(out["table"]["target"]["contradictions"], 1)
        text = json.dumps(out).lower()
        self.assertIn("associated with the observed visibility gap", text)
        for bad in ("causes the", "because of", "will improve", "leads to"):
            self.assertNotIn(bad, text)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for r in (EXAMPLE, rec("p_b"), rec("p_c")):
                    f.write(json.dumps(r) + "\n")
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(C.main(["--data", path, "--product-id", EXAMPLE["product_id"]]), 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(len(out["similarity"]["peers"]), 2)
            self.assertEqual(C.main(["--data", path, "--product-id", "nope"]), 2)


if __name__ == "__main__":
    unittest.main()
