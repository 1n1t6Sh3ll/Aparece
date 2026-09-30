"""TEAM-46 merchant chat. Stub LLM only; no network, no paid calls."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from chat import engine, llm  # noqa: E402
from governance import audit  # noqa: E402
from monitor import store  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
client = TestClient(main.app)


def content(price, chars, vis=None):
    return {"title": "Everyday Tee", "language": "en", "price": price, "currency": "EUR", "description_chars": chars,
            "attributes": {"identity.brand": "Northwind"}, "schema": {"json_ld": True}, "languages": ["en"],
            "description_sha256": f"sha-{chars}", "visibility": vis}


class TrendTest(unittest.TestCase):
    def test_delta_needs_two_dated_points(self):
        self.assertEqual(engine.trends({"price": [("2026-09-01", 20.0, "snapshot:1")]}), [])
        self.assertEqual(engine.trends({"price": [("2026-09-01", 20.0, "s:1"), ("2026-09-01", 25.0, "s:2")]}), [])
        self.assertEqual(engine.trends({"price": [("2026-09-01", 20.0, "s:1"), ("2026-09-02", None, "s:2")]}), [])

    def test_delta_first_to_last_sorted_by_date(self):
        [t] = engine.trends({"price": [("2026-09-03", 24.5, "snapshot:3"), ("2026-09-01", 20.0, "snapshot:1"),
                                       ("2026-09-02", 30.0, "snapshot:2")]})
        self.assertEqual((t["first"], t["last"], t["delta"], t["points"]), (20.0, 24.5, 4.5, 3))
        self.assertIn("+22.5%", t["text"])
        self.assertIn("increased from 20 on 2026-09-01 (snapshot:1) to 24.5 on 2026-09-03", t["text"])
        [d] = engine.trends({"m": [("2026-01-01", 0.5, "a"), ("2026-02-01", 0.25, "b")]})
        self.assertEqual(d["delta"], -0.25)
        self.assertIn("decreased", d["text"])
        self.assertIn("-50%", d["text"])


class EnforceTest(unittest.TestCase):
    ctx = [engine.record("snapshot", 1, "price 25.0 EUR", "2026-09-01", merchant_stated=True),
           engine.record("signals", "p", "peer percentile 29.2", "2024-05"),
           engine.record("trend", "price", "price increased from 20 to 25; delta +5", "2026-09-02")]

    def run_(self, text):
        return engine.enforce(text, self.ctx)

    def test_uncited_or_unknown_or_unsupported_number_dropped(self):
        for bad in ("Your price is 25 EUR.", "Price is 25 [snapshot:9].", "Price is 30 EUR [snapshot:1].",
                    "Your product is great."):
            self.assertEqual(self.run_(bad)[0], "", bad)

    def test_supported_sentence_kept_and_merchant_label_added(self):
        text, cited, dropped = self.run_("Price is 25 EUR [snapshot:1]. Percentile is 29.2 [signals:p].")
        self.assertEqual(text, "Price is 25 EUR (merchant-stated). [snapshot:1] Percentile is 29.2. [signals:p]")
        self.assertEqual(([c["type"] for c in cited], dropped), (["snapshot", "signals"], 0))

    def test_trend_needs_trend_record(self):
        self.assertEqual(self.run_("Your price increased to 25 [snapshot:1].")[0], "")
        self.assertIn("[trend:price]", self.run_("Your price increased by 5 [trend:price].")[0])

    def test_numbers_inside_dates_and_ids_are_not_facts(self):
        ctx = [engine.record("snapshot", 7, {"taken_at": "2026-09-30", "id": 30, "price": 25, "currency": "EUR"},
                             "2026-09-30")]
        for bad in ("Price is 30 dollars [snapshot:7].", "Price is 30 [snapshot:7].", "Price is 9 [snapshot:7].",
                    "Price is 25 dollars [snapshot:7].", "Price was 25 EUR on 2026-10-01 [snapshot:7]."):
            self.assertEqual(engine.enforce(bad, ctx)[0], "", bad)
        for good in ("Price is 25.00 EUR [snapshot:7].", "Price is €25 [snapshot:7].", "Price is 25 [snapshot:7].",
                     "Price was 25 EUR on 2026-09-30 [snapshot:7]."):
            self.assertNotEqual(engine.enforce(good, ctx)[0], "", good)
        text_ctx = [engine.record("snapshot", 8, "price 25.0 EUR on 2026-09-30 for EXP-000030", "2026-09-30")]
        self.assertEqual(engine.enforce("Price is 30 dollars [snapshot:8].", text_ctx)[0], "")

    def test_causal_ranking_claim_dropped(self):
        self.assertEqual(self.run_("Your visibility rose because of the price of 25 [trend:price].")[0], "")


class ChatApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"MONITOR_DB": os.path.join(self.tmp.name, "m.db"), "GOVERNANCE_DB": os.path.join(self.tmp.name, "g.db"),
               "PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"),
               "PRODUCTLENS_SIGNALS": str(FIX / "dashboard_signals.jsonl"),
               "PRODUCTLENS_VISIBILITY": str(FIX / "dashboard_visibility.json"),
               "CHAT_LLM": "stub", "CHAT_TOKEN": "", "CHAT_COMPANY_PROFILE": ""}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        p, self.token = store.enroll("https://shop.example.com/p/p_target")
        self.pid, self.internal = p["public_id"], p["id"]
        for day, price, vis in (("2026-09-01", 20.0, 0.25), ("2026-09-08", 24.0, 0.5)):
            with mock.patch.object(store, "utcnow", return_value=f"{day}T00:00:00Z"):
                store.add_snapshot(p["id"], {"content": content(price, 300, {"mock:mock-1": {"mention_rate": vis}}),
                                             "product_id": "p_target"}, [])

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def post(self, mt=None, **body):
        return client.post("/v1/chat", json=body, headers={"X-Manage-Token": mt} if mt else {})

    def mpost(self, **body):
        return self.post(mt=self.token, product_id=self.pid, **body)

    def test_outside_context_refused_without_llm_call(self):
        called = []
        with mock.patch.dict(llm.BACKENDS, {"stub": lambda m: called.append(m) or "x"}):
            r = self.mpost(message="What will the weather be in Paris tomorrow?")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["answer"], r.json()["refused"], r.json()["citations"]), (engine.REFUSAL, True, []))
        self.assertEqual(called, [])
        self.assertEqual(audit.entries(1)[0]["outcome"], "refused")

    def test_trend_answer_cites_computed_delta(self):
        r = self.mpost(message="How has my price trend changed over time?").json()
        self.assertFalse(r["refused"])
        refs = {f"{c['type']}:{c['id']}" for c in r["citations"]}
        self.assertTrue(refs & {"trend:price", "trend:visibility.mock:mock-1.mention_rate"}, r)
        trend = next(t for t in main.chat_api.collect(self.pid, self.internal) if t["id"] == "price")
        self.assertEqual((trend["delta"], trend["first"], trend["last"]), (4.0, 20.0, 24.0))
        self.assertTrue(r["audit_logged"])
        self.assertEqual(audit.entries(1)[0]["action"], "chat_answer")

    def test_hallucinating_llm_is_filtered(self):
        lie = "Your price is 99 EUR [snapshot:1]. Visibility rose because you cut the price [trend:price]."
        with mock.patch.dict(llm.BACKENDS, {"stub": lambda m: lie}):
            r = self.mpost(message="price trend").json()
        self.assertEqual((r["answer"], r["refused"], r["dropped_sentences"]), (engine.REFUSAL, True, 2))

    def test_sources_dataset_signals_visibility(self):
        types = {r["type"] for r in main.chat_api.collect(self.pid, self.internal)}
        self.assertTrue({"snapshot", "trend", "product", "gaps", "competitors", "signals", "visibility"} <= types,
                        types)
        r = self.post(product_id="p_target", message="What is my peer percentile in signals?").json()
        self.assertIn("signals:p_target", {f"{c['type']}:{c['id']}" for c in r["citations"]})

    def test_experiment_results_and_analysis_in_context(self):
        from experiments import store as exp
        with mock.patch.dict(os.environ, {"EXPERIMENTS_DB": os.path.join(self.tmp.name, "e.db")}):
            e = exp.create({"product_id": "p_target", "language": "en", "market": "DE", "problem": "p",
                            "intervention": "i", "optimization_models": ["mock:mock-1"], "holdout_models": [],
                            "control_products": ["p_heavy"], "accuracy_before": 0.9})
            exp.add_result(e["id"], "accuracy", {"phase": "after", "accuracy": 0.95})
            exp.create({"product_id": "p_other", "language": "en", "market": "DE", "problem": "p",
                        "intervention": "i", "optimization_models": ["mock:mock-1"]})
            recs = main.chat_api.collect("p_target")
            r = self.post(product_id="p_target", message="What is the status of my experiment analysis?").json()
        exp_recs = [x for x in recs if x["type"].startswith("experiment")]
        self.assertEqual({(x["type"], x["id"]) for x in exp_recs if x["type"] != "experiment_result"},
                         {("experiment", e["id"]), ("experiment_analysis", e["id"])})
        self.assertEqual(sum(x["type"] == "experiment_result" for x in exp_recs), 1)
        analysis = next(x for x in exp_recs if x["type"] == "experiment_analysis")
        self.assertIn('"status":"pending"', analysis["text"])
        self.assertIn(f"experiment_analysis:{e['id']}", r["context"])

    def test_monitored_product_needs_public_id_and_manage_token(self):
        self.assertEqual(self.post(product_id=self.pid, message="price trend").status_code, 401)
        self.assertEqual(self.post(mt="wrong", product_id=self.pid, message="price trend").status_code, 403)
        _, other = store.enroll("https://shop.example.com/p/other")
        self.assertEqual(self.post(mt=other, product_id=self.pid, message="price trend").status_code, 403)
        r = self.post(product_id=str(self.internal), message="price trend snapshot").json()  # internal id: no access
        self.assertFalse(any(c.startswith(("snapshot", "trend", "change_event")) for c in r["context"]), r)
        r = self.mpost(message="price trend snapshot diff")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(c.startswith("trend:") for c in r.json()["context"]), r.json())

    def test_product_detail_canned_question_is_cited(self):
        """#115: the product-detail chat sends the monitored public id + X-Manage-Token (web/src/history.ts), so its
        canned question is answered from this product's snapshots/trends; without them there is no monitor data."""
        q = "What changed and what's required now?"
        r = self.mpost(message=q).json()
        self.assertFalse(r["refused"], r)
        self.assertTrue(any(c["type"] in ("trend", "snapshot", "snapshot_diff", "change_event") for c in r["citations"]), r)
        anon = self.post(product_id=None, message=q).json()  # what the old client sent
        self.assertFalse(any(c.startswith(("snapshot", "trend")) for c in anon["context"]), anon)

    def test_monitor_context_has_snapshots_diff_trends(self):
        by_type = {}
        for x in main.chat_api.collect(self.pid, self.internal):
            by_type.setdefault(x["type"], []).append(x)
        self.assertEqual(len(by_type["snapshot"]), 2)
        self.assertIn('"metrics"', by_type["snapshot"][0]["text"])
        [d] = by_type["snapshot_diff"]
        self.assertIn('"price":{"changed":true', d["text"])
        self.assertEqual(by_type["monitored_product"][0]["id"], self.pid)
        self.assertTrue({"price", "attribute_completeness_pct", "description_chars"}
                        <= {t["id"] for t in by_type["trend"]}, by_type["trend"])
        self.assertIn("product", by_type)  # dataset record linked through the snapshot's product_id

    def test_token_and_validation(self):
        with mock.patch.dict(os.environ, {"CHAT_TOKEN": "s3cret"}):
            self.assertEqual(self.post(message="price").status_code, 401)
            self.assertEqual(self.post(message="price", token="s3cret").status_code, 200)
        self.assertEqual(self.post(message="").status_code, 422)
        self.assertEqual(self.post(message="x", history=[{"role": "system", "content": "x"}]).status_code, 422)


if __name__ == "__main__":
    unittest.main()
