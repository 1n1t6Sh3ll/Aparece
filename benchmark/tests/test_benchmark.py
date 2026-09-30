import json
import tempfile
import unittest
from unittest import mock
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

    def test_host_boundary_not_substring(self):
        dup = dict(self.products[0], product_id="p_dup", site="northwindtees.de", aliases=[])
        products = load_catalog(CATALOG) + [dup]
        line = "Northwind Tees Classic Organic Tee (northwindtees.com.au)"
        m = match_response(line, products)
        self.assertEqual(m["mentions"], [])  # .com.au is neither .com nor .de
        self.assertEqual(m["cited_sites"], [])
        m = match_response(line.replace(".com.au", ".com"), products)
        self.assertEqual(m["mentions"], ["p_nw_classic_com"])
        m = match_response("https://northwindtees.com.au/products/classic-organic-tee", products)
        self.assertEqual((m["mentions"], m["cited_sites"]), ([], []))

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

    def test_spend_cap_uses_actual_usage(self):
        class Costly(harness.MockAdapter):
            def complete(self, *a, **k):
                return dict(super().complete(*a, **k), output_tokens=1_000_000)  # far above estimate

        orig = harness.make_adapter
        harness.make_adapter = lambda prov, model, products=(): Costly(model, products)
        try:
            with tempfile.TemporaryDirectory() as d:
                prices = Path(d) / "prices.json"
                prices.write_text(json.dumps({"models": {"mock-1": {"input": 0, "output": 1.0}}}), encoding="utf-8")
                res = harness.main(run_args(str(Path(d) / "r.jsonl"), "--prices", str(prices),
                                            "--max-usd", "0.5", "--max-tokens", "10"))
                self.assertEqual(res["calls"], 1)
                self.assertGreaterEqual(res["spent"], 0.5)
        finally:
            harness.make_adapter = orig

    def _mocked(self, fn):
        orig = harness.make_adapter  # every provider served by the mock: no network, no spend
        harness.make_adapter = lambda prov, model, products=(): harness.MockAdapter(model, products)
        try:
            with tempfile.TemporaryDirectory() as d:
                return fn(Path(d))
        finally:
            harness.make_adapter = orig

    def test_multiple_models_per_provider_side_by_side(self):
        models = ["openai:model-a", "openai:model-b", "anthropic:model-c", "anthropic:model-d"]

        def body(d):
            prices = d / "prices.json"
            prices.write_text(json.dumps({"models": {m.split(":")[1]: {"input": 0, "output": 0} for m in models}}),
                              encoding="utf-8")
            env = {"OPENAI_API_KEY": "test", "ANTHROPIC_API_KEY": "test"}
            with mock.patch.dict(harness.os.environ, env):
                res = harness.main(run_args(str(d / "r.jsonl"), "--models", ",".join(models), "--repeats", "1",
                                            "--prices", str(prices), "--max-usd", "1"))
            self.assertEqual(res["calls"], 32)
            rep = harness.main(["report", "--results", str(d / "r.jsonl"), "--catalog", CATALOG, "--out-dir", str(d)])
            ids = sorted(m.split(":")[1] for m in models)  # bare model ids: backward-compatible keys
            self.assertEqual(list(rep["models"]), ids)
            self.assertTrue(all(m["responses"] == 8 for m in rep["models"].values()))
            md = (d / "report.md").read_text(encoding="utf-8")
            self.assertIn("| site | " + " | ".join(ids) + " |", md)
        self._mocked(body)

    def test_qwen_free_by_default_capped_when_priced(self):
        def body(d):
            base = ["run", "--prompts", PROMPTS, "--models", "qwen:qwen2.5:7b", "--repeats", "1", "--min-interval", "0"]
            self.assertEqual(harness.main(base + ["--out", str(d / "a.jsonl")])["calls"], 8)
            prices = d / "prices.json"
            prices.write_text(json.dumps({"models": {"qwen2.5:7b": {"input": 1e6, "output": 0}}}), encoding="utf-8")
            res = harness.main(base + ["--out", str(d / "b.jsonl"), "--prices", str(prices), "--max-usd", "100"])
            self.assertLess(res["calls"], 8)
        self._mocked(body)

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


class AnthropicTemperatureTests(unittest.TestCase):
    """#112: SDKs/models that reject `temperature` must not break runs (fake SDK; no network, no key)."""

    def adapter(self, reject):
        import sys
        import types
        calls = []

        class BadRequestError(Exception):
            pass

        def create(**kw):
            calls.append(kw)
            if "temperature" in kw and reject == "type":
                raise TypeError("create() got an unexpected keyword argument 'temperature'")
            if "temperature" in kw and reject == "bad":
                raise BadRequestError("temperature is not supported for this model")
            block = types.SimpleNamespace(type="text", text="ok")
            usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
            return types.SimpleNamespace(content=[block], model=kw["model"], usage=usage, model_dump=lambda mode: {})

        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        fake = types.SimpleNamespace(Anthropic=lambda: client, BadRequestError=BadRequestError)
        with mock.patch.dict(sys.modules, {"anthropic": fake}):
            a = harness.AnthropicAdapter("claude-x")
        return a, calls, BadRequestError

    def test_type_error_retries_without_temperature_and_remembers(self):
        a, calls, _ = self.adapter("type")
        self.assertEqual(a.complete("s", "p", 0.7, 10)["text"], "ok")
        self.assertEqual(["temperature" in c for c in calls], [True, False])
        a.complete("s", "p", 0.7, 10)
        self.assertNotIn("temperature", calls[-1])
        self.assertEqual(len(calls), 3)

    def test_bad_request_naming_temperature_retries(self):
        a, calls, _ = self.adapter("bad")
        self.assertEqual(a.complete("s", "p", 0.7, 10)["text"], "ok")
        self.assertEqual(["temperature" in c for c in calls], [True, False])

    def test_unrelated_errors_and_supported_temperature(self):
        a, calls, _ = self.adapter(None)
        a.complete("s", "p", 0.5, 10)
        self.assertEqual(calls[0]["temperature"], 0.5)
        a.client.messages.create = mock.Mock(side_effect=TypeError("bad messages"))
        with self.assertRaises(TypeError):
            a.complete("s", "p", 0.5, 10)


class MetricTests(unittest.TestCase):
    def test_same_model_id_under_two_providers_stays_distinct(self):
        recs = [{"provider": p, "model": "x", "language": "en", "prompt_id": "q", "variant": "original",
                 "response_text": "NW Classic Tee"} for p in ("openai", "qwen")]
        self.assertEqual(sorted(build_report(recs, load_catalog(CATALOG))["models"]), ["openai:x", "qwen:x"])

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
