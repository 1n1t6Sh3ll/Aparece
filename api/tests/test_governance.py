import os
import sqlite3
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from governance import audit, hooks, policy  # noqa: E402

client = TestClient(main.app)
TOKEN = {"X-Governance-Token": "t0k"}


class GovernanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "g.db")
        p = mock.patch.dict(os.environ, {"GOVERNANCE_DB": self.db, "GOVERNANCE_TOKEN": "t0k", "BENCHMARK_MAX_USD": "2"})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def approve(self, aid, approver="owner@x", role=policy.ACCOUNT_OWNER, headers=TOKEN):
        return client.post("/v1/approvals", json={"approval_id": aid, "approver": approver, "role": role}, headers=headers)

    def test_policy_endpoint_and_modes(self):
        body = client.get("/v1/governance/policy").json()
        self.assertEqual(body["default"], "deny")
        self.assertEqual({a["mode"] for a in body["actions"].values()}, {"auto", "approve", "forbidden"})
        self.assertTrue(all(a["owner"] in policy.ROLES for a in body["actions"].values()))

    def test_auto_forbidden_unknown(self):
        self.assertEqual(policy.require("monitor_crawl", "sched")["mode"], "auto")
        with self.assertRaises(policy.Forbidden):
            policy.require("auto_publish_to_storefront", "bot")
        with self.assertRaises(policy.Forbidden):
            policy.require("no_such_action", "bot")
        outcomes = [e["outcome"] for e in audit.entries()]
        self.assertEqual(outcomes, ["denied", "denied", "allowed"])

    def test_audit_log_is_append_only(self):
        policy.require("monitor_crawl", "sched", details={"a": 1})
        db = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("UPDATE audit_log SET actor='x'")
        with self.assertRaises(sqlite3.DatabaseError):
            db.execute("DELETE FROM audit_log")
        db.close()
        e = client.get("/v1/audit-log?limit=1").json()["entries"][0]
        self.assertEqual((e["actor"], e["action"], e["details_hash"]), ("sched", "monitor_crawl", audit.details_hash({"a": 1})))
        self.assertEqual(client.get("/v1/audit-log?limit=0").status_code, 422)

    def paid(self, max_usd, **kw):
        return Namespace(models=["anthropic:claude-haiku-4-5"], max_usd=max_usd, prompts="p.jsonl", **kw)

    def test_benchmark_gate(self):
        self.assertEqual(hooks.gate_benchmark_run(Namespace(models=["mock:m"], max_usd=None, prompts="p"))["action"],
                         "benchmark_free_run")
        self.assertEqual(hooks.gate_benchmark_run(self.paid(1.5))["action"], "benchmark_paid_run")
        with self.assertRaises(policy.ApprovalRequired) as cm:
            hooks.gate_benchmark_run(self.paid(10), actor="alice")
        aid = cm.exception.approval_id
        self.assertEqual(client.get("/v1/approvals").json()["pending"][0]["id"], aid)
        self.assertEqual(self.approve(aid, approver="alice").status_code, 409)  # no self-approval
        self.assertEqual(self.approve(aid, approver=" Alice ").status_code, 409)  # case/space-insensitive
        self.assertEqual(self.approve(aid, role=policy.MERCHANT).status_code, 409)  # wrong role
        self.assertEqual(self.approve(aid, headers={"X-Governance-Token": "bad"}).status_code, 401)
        self.assertEqual(self.approve(aid).json()["status"], "approved")
        with self.assertRaises(policy.ApprovalRequired):  # approval is bound to the exact request details
            hooks.gate_benchmark_run(self.paid(20, approval_id=aid), actor="alice")
        d = hooks.gate_benchmark_run(self.paid(10, approval_id=aid), actor="alice")
        self.assertEqual(d["approved_by"], "owner@x")
        with self.assertRaises(policy.ApprovalRequired):  # single use
            hooks.gate_benchmark_run(self.paid(10, approval_id=aid), actor="alice")

    def test_prediction_confirmation_via_api(self):
        body = {"record_id": "r1", "field": "material", "value": "cotton", "actor": "ops"}
        r = client.post("/v1/predictions/confirm", json=body)
        self.assertEqual(r.status_code, 403)
        aid = r.json()["detail"]["approval_id"]
        self.assertEqual(self.approve(aid, approver="merchant@x", role=policy.MERCHANT).status_code, 200)
        r = client.post("/v1/predictions/confirm", json={**body, "value": "wool", "approval_id": aid})
        self.assertEqual(r.status_code, 403)  # different value is not what was approved
        r = client.post("/v1/predictions/confirm", json={**body, "approval_id": aid})
        self.assertEqual((r.status_code, r.json()["approved_by"]), (200, "merchant@x"))

    def test_approvals_disabled_without_token(self):
        with mock.patch.dict(os.environ, {"GOVERNANCE_TOKEN": ""}):
            self.assertEqual(self.approve("x").status_code, 503)


if __name__ == "__main__":
    unittest.main()
