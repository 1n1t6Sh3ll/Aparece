import json
import tempfile
import unittest
from pathlib import Path

from benchmark import harness
from benchmark.match import load_catalog, match_response
from benchmark.metrics import build_report, to_markdown

EX = Path(__file__).resolve().parent.parent / "examples"
PROMPTS, CATALOG = str(EX / "prompts.example.jsonl"), str(EX / "catalog.example.jsonl")


def run_args(out, *extra):
    return ["run", "--prompts", PROMPTS, "--models", "mock:mock-1", "--out", out,
            "--catalog", CATALOG, "--min-interval", "0", *extra]


class PromptTests(unittest.TestCase):
    def test_example_loads(self):
        rows = harness.load_prompts(PROMPTS)
        self.assertEqual(len(rows), 10)
        self.assertEqual({r["language"] for r in rows}, {"en", "es"})
        self.assertEqual({r["split"] for r in rows}, {"dev", "val", "hidden"})

    def test_csv_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.csv"
            p.write_text("id,text,language,market,canonical_intent,split,candidates\n"
                         "a,Pick: {candidates},en,US,x,dev,A|B\n", encoding="utf-8")
            self.assertEqual(harness.load_prompts(p)[0]["candidates"], ["A", "B"])
            p.write_text("id,text,language,market,canonical_intent,split\na,t,en,US,x,test\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                harness.load_prompts(p)


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.products = load_catalog(CATALOG)

    def test_positions_citations_unmatched(self):
        text = ("1. Solana Basics Heavy Tee\n"
                "2. NW Classic Tee - https://northwindtees.com/products/classic-organic-tee/\n"
                "3. Acme Basic Tee\nSee also https://other.example/x")
        m = match_response(text, self.products)
        self.assertEqual(m["mentions"], ["p_solana_heavy", "p_nw_classic_com"])
        self.assertEqual(m["cited_products"], ["p_nw_classic_com"])
        self.assertEqual(m["cited_sites"], ["northwindtees.com"])
        kinds = {(u["kind"], u["text"]) for u in m["unmatched"]}
        self.assertIn(("item", "Acme Basic Tee"), kinds)
        self.assertIn(("url", "https://other.example/x"), kinds)

    def test_country_tld_is_distinct_and_accents_normalized(self):
        m = match_response("Try Northwind Tees Camiseta Organica Clasica (northwindtees.es)", self.products)
        self.assertEqual(m["mentions"], ["p_nw_classic_es"])
        m = match_response("https://northwindtees.es/productos/camiseta-organica-clasica", self.products)
        self.assertEqual(m["cited_sites"], ["northwindtees.es"])

    def test_brand_required_for_name_match(self):
        self.assertEqual(match_response("a generic Heavy Tee", self.products)["mentions"], [])

    def test_ambiguous_same_name_on_two_tlds(self):
        products = load_catalog(CATALOG) + [dict(self.products[0], product_id="p_dup", site="northwindtees.de", aliases=[])]
        m = match_response("Northwind Tees Classic Organic Tee", products)
        self.assertEqual(m["mentions"], [])
        self.assertEqual(m["unmatched"][0]["kind"], "ambiguous")


class HarnessTests(unittest.TestCase):
    def test_dry_run_makes_no_calls(self):
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "r.jsonl")
            res = harness.main(run_args(out, "--dry-run", "--repeats", "2", "--shuffle"))
            # 8 dev/val prompts x 2 repeats + 1 candidate prompt shuffled x 2 = 18
            self.assertEqual(res["calls"], 18)
            self.assertFalse(Path(out).exists())

    def test_run_resume_cap_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            out = str(Path(d) / "r.jsonl")
            self.assertEqual(harness.main(run_args(out, "--repeats", "2"))["calls"], 16)
            self.assertEqual(harness.main(run_args(out, "--repeats", "2"))["calls"], 0)  # resumed
            rec = json.loads(Path(out).read_text(encoding="utf-8").splitlines()[0])
            for k in ("run_id", "model", "model_version", "timestamp", "settings", "raw_response", "canonical_intent"):
                self.assertIn(k, rec)
            rep = harness.main(["report", "--results", out, "--catalog", CATALOG, "--out-dir", d])
            m = rep["models"]["mock-1"]
            self.assertEqual(m["responses"], 16)
            self.assertEqual(set(m["languages"]), {"en", "es"})
            self.assertIsNotNone(m["stability"])
            self.assertIn("northwindtees.es", m["sites"])
            self.assertTrue((Path(d) / "report.md").exists())

    def test_spend_cap_stops(self):
        with tempfile.TemporaryDirectory() as d:
            prices = Path(d) / "prices.json"
            prices.write_text(json.dumps({"models": {"mock-1": {"input": 1e6, "output": 0}}}), encoding="utf-8")
            res = harness.main(run_args(str(Path(d) / "r.jsonl"), "--prices", str(prices), "--max-usd", "100"))
            self.assertLess(res["calls"], 8)

    def test_paid_requires_cap_and_price(self):
        with tempfile.TemporaryDirectory() as d:
            base = ["run", "--prompts", PROMPTS, "--out", str(Path(d) / "r.jsonl")]
            with self.assertRaises(SystemExit):
                harness.main(base + ["--models", "anthropic:unknown-model", "--dry-run"])
            with self.assertRaises(SystemExit):
                harness.main(base + ["--models", "openai:gpt-4o-mini"])  # no --max-usd

    def test_retries(self):
        class Flaky(harness.MockAdapter):
            n = 0

            def complete(self, *a, **k):
                Flaky.n += 1
                if Flaky.n == 1:
                    raise RuntimeError("boom")
                return super().complete(*a, **k)

        orig = harness.make_adapter
        harness.make_adapter = lambda prov, model, products=(): Flaky(model, products)
        try:
            with tempfile.TemporaryDirectory() as d:
                args = harness.argparse.Namespace(
                    prompts=PROMPTS, models=["mock:mock-1"], out=str(Path(d) / "r.jsonl"), catalog=CATALOG,
                    prices=str(harness.HERE / "prices.json"), splits={"dev"}, repeats=1, shuffle=False,
                    system="s", temperature=0.0, max_tokens=10, max_usd=None, dry_run=False,
                    min_interval=0, retries=2)
                res = harness.run(args, sleep=lambda s: None, log=lambda *a: None)
                self.assertEqual(res["calls"], 6)
        finally:
            harness.make_adapter = orig


class MetricTests(unittest.TestCase):
    def test_rates_and_markdown(self):
        products = load_catalog(CATALOG)
        recs = [{"model": "m", "language": "en", "prompt_id": "q", "variant": "original",
                 "response_text": t} for t in ("1. Solana Basics Heavy Tee\n2. NW Classic Tee", "1. NW Classic Tee")]
        rep = build_report(recs, products, k=1)
        nw = rep["models"]["m"]["sites"]["northwindtees.com"]
        self.assertEqual((nw["mention_rate"], nw["top1_rate"], nw["mrr"]), (1.0, 0.5, 0.75))
        self.assertEqual(rep["models"]["m"]["stability"], 0.5)
        self.assertIn("| m | en | northwindtees.com |", to_markdown(rep))


if __name__ == "__main__":
    unittest.main()
