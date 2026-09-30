"""TEAM-42 experiments. All metrics below are SYNTHETIC, TEST-ONLY numbers; no benchmark or model is run."""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from experiments import __main__ as cli, lift  # noqa: E402

CATALOG = Path(__file__).parent / "fixtures" / "dashboard_records.jsonl"
client = TestClient(main.app)


def synthetic_report(values, k=3):
    """Test-only report in benchmark/metrics.py shape. values: {model: {product_id: mention_rate}}."""
    return {"k": k, "responses": 10, "models": {
        m: {"products": {p: {"mention_rate": v, f"top{k}_rate": v / 2, "mrr": v / 3, "citation_rate": 0.0}
                         for p, v in prods.items()}, "languages": {}}
        for m, prods in values.items()}}


class ExperimentsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "e.db")
        p = mock.patch.dict(os.environ, {"EXPERIMENTS_DB": self.db, "EXPERIMENTS_CATALOG": str(CATALOG)})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def create(self, **kw):
        body = {"product_id": "p_target", "language": "en", "market": "US", "problem": "missing fabric weight",
                "intervention": "added GSM to description", "before_snapshot": "monitor:snapshot:1",
                "after_snapshot": "monitor:snapshot:2", "optimization_models": ["opt"], "holdout_models": ["hold"],
                "changed_products": ["p_heavy"], "accuracy_before": 0.9, **kw}
        r = client.post("/v1/experiments", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["experiment"]

    def bench(self, eid, phase, split, t, c, hold_t=None, runs=(0.0, 0.01, -0.01)):
        """Post one synthetic report per run; treatment t, each control c (+ small per-run jitter)."""
        for i, j in enumerate(runs):
            vals = {"opt": {"p_target": t + j, "p_slim": c + j, "p_boxy": c, "p_linen": c - j},
                    "hold": {"p_target": (t if hold_t is None else hold_t) + j, "p_slim": c, "p_boxy": c, "p_linen": c}}
            r = client.post(f"/v1/experiments/{eid}/results",
                            json={"kind": "benchmark", "phase": phase, "split": split, "run": f"r{i}",
                                  "report": synthetic_report(vals)})
            self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def scenario(self, dev_post, hidden_post, hold_post=None, acc_after=0.92):
        eid = self.create()["id"]
        for split, post in (("dev", dev_post), ("hidden", hidden_post)):
            self.bench(eid, "baseline", split, 0.30, 0.20)
            self.bench(eid, "post", split, post, 0.25, hold_t=hold_post)
        r = client.post(f"/v1/experiments/{eid}/results", json={"kind": "accuracy", "phase": "after", "accuracy": acc_after})
        self.assertEqual(r.status_code, 201, r.text)
        return eid, r.json()["analysis"]

    def test_create_ids_and_auto_controls_exclude_changed(self):
        exp = self.create()
        self.assertEqual(exp["id"], "EXP-000001")
        self.assertEqual(exp["control_products"], ["p_slim", "p_boxy", "p_linen"])  # p_heavy changed -> excluded
        self.assertEqual(exp["control_source"], "auto: analysis/peers.py")
        self.assertEqual(self.create(control_products=["p_boxy"])["control_products"], ["p_boxy"])
        self.assertEqual(client.get("/v1/experiments/EXP-000002").json()["experiment"]["id"], "EXP-000002")

    def test_adjusted_lift_generalizes(self):
        _, a = self.scenario(dev_post=0.50, hidden_post=0.50)
        m = a["lifts"]["hidden"]["holdout"]["mention_rate"]
        self.assertEqual((m["raw_change_pp"], m["control_change_pp"], m["adjusted_lift_pp"]), (20.0, 5.0, 15.0))
        lo, hi = m["ci95_pp"]
        self.assertTrue(lo <= 15.0 <= hi and hi - lo < 5)
        self.assertEqual(a["status"], "reported")
        self.assertTrue(a["statement"].startswith("Observed adjusted visibility lift: +15.00 pp (95% bootstrap CI"))
        self.assertNotIn("caus", a["statement"].lower())
        self.assertFalse(a["dev_vs_hidden"]["overfitting_flag"])
        self.assertTrue(a["generalization"]["generalizes"])
        self.assertEqual(a["accuracy"], {"before": 0.9, "after": 0.92, "guardrail": "pass"})
        self.assertIsNotNone(a["lifts"]["dev"]["optimization"]["topk_rate"])

    def test_overfitting_flag(self):
        _, a = self.scenario(dev_post=0.50, hidden_post=0.35)  # hidden adjusted = 0 pp
        self.assertTrue(a["dev_vs_hidden"]["overfitting_flag"])
        self.assertEqual(a["status"], "flagged")

    def test_holdout_models_do_not_generalize(self):
        _, a = self.scenario(dev_post=0.50, hidden_post=0.50, hold_post=0.35)
        self.assertFalse(a["generalization"]["generalizes"])
        self.assertEqual(a["status"], "flagged")

    def test_accuracy_guardrail_rejects(self):
        _, a = self.scenario(dev_post=0.50, hidden_post=0.50, acc_after=0.85)
        self.assertEqual(a["accuracy"]["guardrail"], "fail")
        self.assertEqual(a["status"], "rejected")

    def test_results_append_only(self):
        self.scenario(dev_post=0.5, hidden_post=0.5)
        db = sqlite3.connect(self.db)
        for sql in ("UPDATE results SET kind = 'x'", "DELETE FROM results", "UPDATE experiments SET data = '{}'"):
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(sql)
        db.close()

    def test_export_dataset_jsonl(self):
        self.scenario(dev_post=0.5, hidden_post=0.5)
        out = os.path.join(self.tmp.name, "rows.jsonl")
        with mock.patch("builtins.print"):
            cli.main(["export", out])
        rows = [json.loads(line) for line in Path(out).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["id"], rows[0]["intervention"], rows[0]["adjusted_lift_pp"]),
                         ("EXP-000001", "added GSM to description", 15.0))
        self.assertEqual(rows[0]["before_snapshot"], "monitor:snapshot:1")

    def test_single_run_has_no_ci(self):
        eid = self.create()["id"]
        self.bench(eid, "baseline", "dev", 0.3, 0.2, runs=(0.0,))
        a = self.bench(eid, "post", "dev", 0.4, 0.2, runs=(0.0,))["analysis"]
        self.assertIsNone(a["lifts"]["dev"]["optimization"]["mention_rate"]["ci95_pp"])
        self.assertIn("no CI", a["statement"])

    def test_errors(self):
        self.assertEqual(client.get("/v1/experiments/EXP-000999").status_code, 404)
        self.assertEqual(client.get("/v1/experiments/nope").status_code, 404)
        self.assertEqual(client.post("/v1/experiments", json={"product_id": "p"}).status_code, 422)
        bad = {"product_id": "p_target", "language": "en", "market": "US", "problem": "x", "intervention": "y",
               "optimization_models": ["a"], "holdout_models": ["a"]}
        self.assertEqual(client.post("/v1/experiments", json=bad).status_code, 422)
        eid = self.create()["id"]
        url = f"/v1/experiments/{eid}/results"
        self.assertEqual(client.post(url, json={"kind": "benchmark", "phase": "post"}).status_code, 422)
        other = synthetic_report({"opt": {"p_other": 0.5}})
        r = client.post(url, json={"kind": "benchmark", "phase": "post", "split": "dev", "report": other})
        self.assertEqual(r.status_code, 422)

    def test_language_rows_preferred(self):
        rep = synthetic_report({"opt": {"p_target": 0.1}})
        rep["models"]["opt"]["languages"] = {"de": {"products": {"p_target": {"mention_rate": 0.7, "top3_rate": 0.1, "mrr": 0.2}}}}
        self.assertEqual(lift.extract_metrics(rep, {"p_target"}, "de")[0]["opt"]["p_target"]["mention_rate"], 0.7)
        self.assertEqual(lift.extract_metrics(rep, {"p_target"}, "en")[1], "all_languages")


if __name__ == "__main__":
    unittest.main()
