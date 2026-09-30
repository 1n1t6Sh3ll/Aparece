"""TEAM-47 shoot-out: mock adapters only, synthetic records, no network, no spend."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from benchmark.shootout import report, run, score

GOLD = {"identity.product_type": "t_shirt", "materials.primary_material": "cotton",
        "materials.material_percentages": {"cotton": 100}, "fit_and_style.fit": "regular",
        "fit_and_style.sleeve_length": "short", "variants.colors": ["black", "white"]}
EVIDENCE = [{"field": "materials.material_percentages", "source_text": "100% cotton"},
            {"field": "materials.primary_material", "source_text": "100% cotton"},
            {"field": "fit_and_style.fit", "source_text": "Regular fit"},
            {"field": "fit_and_style.sleeve_length", "source_text": "Short sleeve"},
            {"field": "variants.colors", "source_text": "Black, White"},
            {"field": "identity.product_type", "source_text": "T-Shirt"}]


def row(pid, lang, desc, gold=True):
    return {"product_id": pid, "source": "wdc", "language": lang, "domain": f"{pid}.example",
            "provenance": {"url": f"https://{pid}.example/p", "scraped_at": "2026-09-01T00:00:00Z"},
            "raw": {"brand": f"Brand {pid}", "raw_product_name": f"Tee {pid}", "raw_full_description": desc},
            "gold": GOLD if gold else {"identity.product_type": "t_shirt"}, "evidence": EVIDENCE if gold else []}


def cat(pid, lang, role, group):
    return {"product_id": pid, "source": {"canonical_url": f"https://{pid}.example/p", "merchant_domain": f"{pid}.example",
                                          "language": lang},
            "identity": {"brand": f"Brand {pid}", "product_name": f"Tee {pid}"}, "aliases": [], "role": role, "group": group}


class Liar:
    """Generator mock that adds unsupported claims."""

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        text = json.dumps({"title": "Tee", "description": "Award-winning luxury tee. Made in Italy from 100% silk.",
                           "tags": ["black", "Black", "eco-friendly", "t-shirt"]})
        return {"text": text, "model_version": "liar", "input_tokens": 10, "output_tokens": 10}


class Boom:
    def complete(self, *a, **k):
        raise AssertionError("no model call expected")


def fixture(d):
    d = Path(d)
    cats, rows = [], []
    for g, lang in (("g1", "en"), ("g2", "es")):
        cats.append(cat(f"{g}t", lang, "target", g))
        rows.append(row(f"{g}t", lang, "The best tee ever, loved by thousands. 100% cotton."))
        for i in range(4):
            cats.append(cat(f"{g}c{i}", lang, "competitor", g))
            rows.append(row(f"{g}c{i}", lang, f"Competitor {i} shirt.", gold=False))
    (d / "data").mkdir()
    (d / "data" / "train.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    (d / "cat.jsonl").write_text("\n".join(json.dumps(c) for c in cats), encoding="utf-8")
    prompts = []
    for lang, q in (("en", "black cotton tee regular fit"), ("es", "camiseta negra algodon")):
        for i, split in enumerate(("dev", "val", "dev", "hidden")):
            prompts.append({"id": f"P{i}_{lang}", "text": f"{q} {i}", "language": lang, "market": "US",
                            "canonical_intent": f"P{i}", "split": split})
    (d / "prompts.jsonl").write_text("\n".join(json.dumps(p) for p in prompts), encoding="utf-8")
    return d


def args(d, *extra):
    return ["--catalog", str(d / "cat.jsonl"), "--data", str(d / "data"), "--prompts", str(d / "prompts.jsonl"),
            "--out-dir", str(d / "out"), "--prompts-per-product", "2", "--repeats", "2", "--bootstrap", "50",
            "--min-interval", "0", *extra]


def parse(argv):
    return run.parser().parse_args(argv)


def factory_with(gen_adapter):
    def factory(provider, model, products=(), role="judge"):
        if role == "gen" and model == "liar":
            return gen_adapter
        return run.make_adapter(provider, model, products, role)
    return factory


class ShootoutTests(unittest.TestCase):
    def test_dry_run_counts_and_no_calls(self):
        with tempfile.TemporaryDirectory() as d:
            d = fixture(d)
            a = parse(args(d, "--generators", "original,productlens,openai:gpt-4o-mini,anthropic:claude-haiku-4-5-20251001",
                           "--dry-run"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                res = run.run(a, factory=lambda *x, **k: Boom())
            self.assertEqual(res["products"], 2)
            self.assertEqual(res["gen_calls"], 4)  # 2 products x 2 paid LLM generators
            self.assertEqual(res["judge_calls"], 2 * 4 * 2 * 2 * 2)  # products x gens x prompts x repeats x judges
            self.assertGreater(res["est_usd"], 0)
            self.assertIn("est max $", buf.getvalue())
            self.assertFalse((d / "out").exists())

    def test_paid_needs_cap(self):
        with tempfile.TemporaryDirectory() as d:
            d = fixture(d)
            with self.assertRaises(SystemExit):
                run.run(parse(args(d)), log=lambda *_: None)

    def test_spend_cap_stops_before_any_call(self):
        with tempfile.TemporaryDirectory() as d:
            d = fixture(d)
            a = parse(args(d, "--generators", "original", "--judges", "openai:gpt-4o-mini", "--holdout-judge", "",
                           "--max-usd", "0.000001"))
            with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test"}):
                rep = run.run(a, factory=lambda *x, **k: Boom(), log=lambda *_: None)
            self.assertEqual(rep["cost"]["judge_calls"], 0)
            self.assertIsNone(rep["overall"]["winner"])

    def test_mock_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            d = fixture(d)
            a = parse(args(d, "--generators", "original,productlens,productlens@mock:mock-gen,mock:liar,mock:mock-gen",
                           "--judges", "mock:mock-1,mock:mock-2", "--holdout-judge", "mock:mock-2"))
            rep = run.run(a, factory=factory_with(Liar()), log=lambda *_: None)
            gens = rep["generators"]
            self.assertTrue(gens["productlens"]["qualified"])
            self.assertEqual(gens["productlens"]["flagged"], 0)
            self.assertFalse(gens["mock:liar"]["qualified"])
            self.assertGreater(gens["mock:liar"]["unsupported_claims"], 0)
            self.assertEqual(gens["mock:liar"]["tags"]["duplicates"], 2)  # "Black" twice (2 products)
            self.assertEqual(gens["mock:liar"]["tags"]["false"], 2)  # "eco-friendly" is not a verified fact
            self.assertFalse(gens["original"]["qualified"])  # "best tee ever, loved by thousands" is not grounded
            self.assertNotIn("mock:liar", rep["overall"]["ranking"])
            self.assertNotIn("original", rep["overall"]["ranking"])
            self.assertIn(rep["overall"]["winner"], ("productlens", "mock:mock-gen"))
            self.assertEqual(rep["overall"]["holdout_judge"]["judge"], "mock:mock-2")
            self.assertGreater(gens["productlens"]["description"]["jsonld_completeness"], 0)
            self.assertIsNone(gens["mock:liar"]["description"]["jsonld_completeness"])
            for p in rep["products"]:  # merged recommendation uses guardrail-passing parts only
                r, c = p["recommended"], p["candidates"]
                self.assertTrue(c[r["title"]["from"]]["title"]["passes"])
                self.assertTrue(c[r["description"]["from"]]["description"]["passes"])
                self.assertNotIn("eco-friendly", r["tags"]["list"])
                self.assertEqual(len({t.lower() for t in r["tags"]["list"]}), len(r["tags"]["list"]))
            self.assertIn(rep["overall"]["parts"]["title"]["winner"], ("productlens", "mock:mock-gen"))
            calls = report.load_rows(d / "out" / "judge_calls.jsonl")
            self.assertEqual(len(calls), 2 * 5 * 2 * 2 * 2)
            self.assertTrue(gens["productlens@mock:mock-gen"]["qualified"])
            self.assertTrue(all(c["split"] in ("dev", "val") for c in calls))  # hidden never asked
            pos = {}
            for c in calls:  # paired design: target position does not depend on the candidate
                pos.setdefault((c["group"], c["prompt_id"], c["repeat"]), set()).add(c["target_position"])
            self.assertTrue(all(len(v) == 1 for v in pos.values()))
            v = gens["productlens"]["visibility"]
            self.assertLessEqual(v["mrr"]["lo"], v["mrr"]["value"])
            self.assertLessEqual(v["mrr"]["value"], v["mrr"]["hi"])
            self.assertTrue((d / "out" / "report.md").read_text(encoding="utf-8").count("Controlled evaluation"))
            # resume: nothing new is called
            a.generators = "original,productlens,mock:mock-gen"
            run.run(a, factory=lambda *x, **k: Boom(), log=lambda *_: None)
            self.assertEqual(len(report.load_rows(d / "out" / "judge_calls.jsonl")), len(calls))


class ScoreTests(unittest.TestCase):
    def test_quality_helpers(self):
        self.assertGreater(score.readability("The cat sat. It ran.", "en"), score.readability(
            "Extraordinarily sophisticated manufacturing methodologies characterize contemporary production.", "en"))
        self.assertEqual(score.jsonld_completeness({"name": 1, "brand": 2}), round(2 / 9, 4))
        self.assertIsNone(score.jsonld_completeness(None))
        prompts = [{"text": "black cotton tee please"}, {"text": "linen shirt for summer"}]
        self.assertEqual(score.intent_coverage("A black cotton tee.", prompts), 0.5)

    def test_title_and_tags_audit(self):
        from optimizer.truth import product_truth
        rec = run.prepare(__import__("dashboard_api").adapt(row("x", "en", "d")), cat("x", "en", "target", "g"))
        truth = product_truth(rec)
        t = score.title_audit("Brand x Tee x - 100% cotton regular fit t-shirt", truth, "en")
        self.assertTrue(t["passes"])
        self.assertEqual(t["has"], {"brand": True, "type": True, "material": True, "fit": True})
        self.assertFalse(score.title_audit("Best luxury tee", truth, "en")["passes"])
        tags = score.fact_tags(truth, "es")
        self.assertIn("camiseta", tags)
        self.assertTrue(score.tags_audit(tags, truth, "es", [])["passes"])
        self.assertEqual(score.tags_audit(["manga corta"], truth, "en", [])["language_match"], 0.0)

    def test_guard_numeric_sizes_are_sizes_not_numbers(self):
        from optimizer import guard
        from optimizer.truth import product_truth
        r = row("s", "en", "d")
        r["gold"] = {**GOLD, "variants.sizes": ["S", "XXL", "3XL"]}
        r["evidence"] = EVIDENCE + [{"field": "variants.sizes", "source_text": "S, XXL, 3XL"}]
        truth = product_truth(run.prepare(__import__("dashboard_api").adapt(r), cat("s", "en", "target", "g")))
        for ok in ("Sizes: S, 2XL, 3XL.", "Sizes: XXL."):
            self.assertEqual(guard.check_sentence(ok, truth)[1], [], ok)
        self.assertTrue(guard.check_sentence("Sizes: S, 5XL.", truth)[1])  # 5XL is not a verified size
        self.assertTrue(guard.check_sentence("Loved by 2 people.", truth)[1])  # plain numbers still need a field

    def test_paired_diff(self):
        mk = lambda rank, i: {"group": "g", "prompt_id": f"p{i}", "target": "T1",  # noqa: E731
                              "mentions": ["x"] * (rank - 1) + ["T1"]}
        a = [mk(1, i) for i in range(10)]
        b = [mk(3, i) for i in range(10)]
        d = score.paired_diff(a, b, b=100)
        self.assertAlmostEqual(d["value"], 1 - 1 / 3, places=3)
        self.assertGreater(d["lo"], 0)
        self.assertEqual(score.metrics(a)["top3_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
