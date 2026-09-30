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
ADMIN = {"X-Governance-Admin-Token": "adm1n"}


class GovernanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "g.db")
        p = mock.patch.dict(os.environ, {"GOVERNANCE_DB": self.db, "GOVERNANCE_TOKEN": "t0k", "BENCHMARK_MAX_USD": "2",
                                         "GOVERNANCE_ADMIN_TOKEN": "adm1n", "MONITOR_DB": os.path.join(self.tmp.name, "m.db")})
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
        e = client.get("/v1/audit-log?limit=1", headers=ADMIN).json()["entries"][0]
        self.assertEqual((e["actor"], e["action"], e["details_hash"]), ("sched", "monitor_crawl", audit.details_hash({"a": 1})))
        self.assertEqual(client.get("/v1/audit-log?limit=0", headers=ADMIN).status_code, 422)

    def paid(self, max_usd, **kw):
        return Namespace(models=["anthropic:claude-haiku-4-5"], max_usd=max_usd, prompts="p.jsonl", **kw)

    def test_benchmark_gate(self):
        self.assertEqual(hooks.gate_benchmark_run(Namespace(models=["mock:m"], max_usd=None, prompts="p"))["action"],
                         "benchmark_free_run")
        self.assertEqual(hooks.gate_benchmark_run(self.paid(1.5))["action"], "benchmark_paid_run")
        with self.assertRaises(policy.ApprovalRequired) as cm:
            hooks.gate_benchmark_run(self.paid(10), actor="alice")
        aid = cm.exception.approval_id
        self.assertEqual(client.get("/v1/approvals", headers=ADMIN).json()["pending"][0]["id"], aid)
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


class TenantScopeTest(GovernanceTest):
    def setUp(self):
        super().setUp()
        from monitor import store
        a, self.tok_a = store.enroll("https://a.example.com/p/1")
        b, self.tok_b = store.enroll("https://b.example.com/p/2")
        self.a, self.b = a["id"], b["id"]
        chat_env = mock.patch.dict(os.environ, {"CHAT_LLM": "stub", "CHAT_TOKEN": ""})
        chat_env.start()
        self.addCleanup(chat_env.stop)

    def log_as(self, token):
        return client.get("/v1/audit-log", headers={"X-Manage-Token": token} if token else {})

    def test_audit_log_requires_owner_token(self):
        policy.require("monitor_crawl", "sched", target="a", owner=self.a)
        policy.require("monitor_crawl", "sched", target="b", owner=self.b)
        policy.require("monitor_crawl", "sched", target="global")
        self.assertEqual(self.log_as(None).status_code, 401)
        self.assertEqual(self.log_as("wrong").status_code, 403)
        self.assertEqual([e["target"] for e in self.log_as(self.tok_a).json()["entries"]], ["a"])
        self.assertEqual([e["target"] for e in self.log_as(self.tok_b).json()["entries"]], ["b"])
        both = self.log_as(f"{self.tok_a},{self.tok_b}").json()["entries"]
        self.assertEqual({e["target"] for e in both}, {"a", "b"})
        self.assertEqual(len(client.get("/v1/audit-log", headers=ADMIN).json()["entries"]), 3)
        self.assertEqual(client.get("/v1/audit-log", headers={"X-Governance-Admin-Token": "bad"}).status_code, 401)
        with mock.patch.dict(os.environ, {"GOVERNANCE_ADMIN_TOKEN": ""}):  # admin view off when unset
            self.assertEqual(client.get("/v1/audit-log", headers={"X-Governance-Admin-Token": ""}).status_code, 401)

    def test_approvals_scoped(self):
        body = {"record_id": str(self.a), "field": "material", "value": "cotton", "actor": "ops"}
        client.post("/v1/predictions/confirm", json=body, headers={"X-Manage-Token": self.tok_a})
        client.post("/v1/predictions/confirm", json={**body, "record_id": str(self.b)},  # b's product, a's token
                    headers={"X-Manage-Token": self.tok_a})
        self.assertEqual(len(client.get("/v1/approvals", headers={"X-Manage-Token": self.tok_a}).json()["pending"]), 1)
        self.assertEqual(client.get("/v1/approvals", headers={"X-Manage-Token": self.tok_b}).json()["pending"], [])
        self.assertEqual(client.get("/v1/approvals").status_code, 401)

    def test_chat_cannot_write_into_another_tenant(self):
        msg = {"product_id": str(self.b), "message": "price trend"}
        for headers in ({}, {"X-Manage-Token": "bogus"}, {"X-Manage-Token": self.tok_a}):
            self.assertEqual(client.post("/v1/chat", json=msg, headers=headers).status_code, 200)
        self.assertEqual(self.log_as(self.tok_b).json()["entries"], [])
        rows = client.get("/v1/audit-log", headers=ADMIN).json()["entries"]
        self.assertEqual({(e["actor"], e["target"], e["owner_pid"]) for e in rows}, {("anonymous", None, None)})
        client.post("/v1/chat", json=msg, headers={"X-Manage-Token": self.tok_b})
        e = self.log_as(self.tok_b).json()["entries"][0]
        self.assertEqual((e["actor"], e["target"], e["owner_pid"]), ("merchant_chat", str(self.b), self.b))


if __name__ == "__main__":
    unittest.main()
