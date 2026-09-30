import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import monitor_api  # noqa: E402
import safe_fetch  # noqa: E402
from monitor import changes, crawl, scheduler, store  # noqa: E402

FIX = Path(__file__).resolve().parents[2] / "monitor" / "fixtures"
PAGES = {v: (FIX / f"tee_{v}.html").read_text(encoding="utf-8") for v in ("v1", "v2")}
URL = "https://shop.example.com/products/everyday-tee"
client = TestClient(main.app)
REAL_CHECK = safe_fetch.check_url  # captured before setUp patches it


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(__file__).parent / "fixtures" / "dashboard_records.jsonl"
        env = {"MONITOR_DB": os.path.join(self.tmp.name, "m.db"), "PRODUCTLENS_DATA": str(data), "MONITOR_DELAY": "0"}
        for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "BENCHMARK_MAX_USD"):
            env[k] = ""
        self.page = PAGES["v1"]
        clock = iter(f"2026-09-{d:02d}T03:00:00Z" for d in range(1, 29))
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(safe_fetch, "check_url"),
                  mock.patch.object(safe_fetch, "fetch_page", side_effect=lambda u: (u, self.page)),
                  mock.patch.object(store, "utcnow", side_effect=lambda: next(clock))):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        monitor_api._hits.clear()

    def enroll(self, **kw):
        r = client.post("/v1/enroll", json={"url": URL, "email": "shop@example.com", **kw})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    @staticmethod
    def auth(body):
        return {"X-Manage-Token": body["manage_token"]}

    def test_enroll_crawl_twice_emits_events(self):
        body = self.enroll(plan="pro")
        pid, h = body["product"]["id"], self.auth(body)
        iid = store.pid_for(pid)
        self.assertEqual(body["crawl"]["status"], "ok")
        self.assertEqual(body["crawl"]["events"], [])  # first snapshot has no baseline
        self.page = PAGES["v2"]
        res = client.post(f"/v1/monitored/{pid}/crawl", headers=h).json()
        types = {e["type"] for e in res["events"]}
        self.assertTrue({"PRICE_CHANGED", "DESCRIPTION_CHANGED", "ATTRIBUTE_ADDED", "LANGUAGE_PAGE_ADDED"} <= types, types)
        price = next(e for e in res["events"] if e["type"] == "PRICE_CHANGED")
        self.assertEqual((price["before"], price["after"]), ([30.0, "EUR"], [25.0, "EUR"]))
        self.assertIn("identity.brand", {e["field"] for e in res["events"] if e["type"] == "ATTRIBUTE_ADDED"})

        hist = client.get(f"/v1/products/{pid}/history").json()
        s1, s2 = hist["snapshots"]
        self.assertEqual((s1["taken_at"], s2["taken_at"]), ("2026-09-04T03:00:00Z", "2026-09-07T03:00:00Z"))
        self.assertNotEqual(s1["content_hash"], s2["content_hash"])
        self.assertEqual(s1["content_hash"], store.content_hash(s1["data"]["content"]))
        self.assertIsNotNone(s2["data"]["gaps"])
        self.assertEqual(len(hist["events"]), len(res["events"]))
        mon = client.get("/v1/monitored").json()["results"][0]
        self.assertEqual((mon["plan"], mon["snapshot_count"], mon["active"]), ("pro", 2, 1))

        # unchanged page -> new snapshot, same hash, no events
        again = client.post(f"/v1/monitored/{pid}/crawl", headers=h).json()
        self.assertEqual(again["events"], [])
        self.assertEqual(store.last_snapshot(iid)["content_hash"], s2["content_hash"])

    def test_snapshots_diff_trends(self):
        body = self.enroll()
        pid, h = body["product"]["id"], self.auth(body)
        self.page = PAGES["v2"]
        client.post(f"/v1/monitored/{pid}/crawl", headers=h)
        for path in ("snapshots", "trends", "snapshots/1/diff/2"):
            self.assertEqual(client.get(f"/v1/products/{pid}/{path}").status_code, 401)
            self.assertEqual(client.get(f"/v1/products/{pid}/{path}", headers={"X-Manage-Token": "x"}).status_code, 403)
        snaps = client.get(f"/v1/products/{pid}/snapshots", headers=h).json()["results"]
        self.assertEqual([s["crawled_at"] for s in snaps], ["2026-09-04T03:00:00Z", "2026-09-07T03:00:00Z"])
        m1, m2 = snaps[0]["metrics"], snaps[1]["metrics"]
        self.assertLess(m1["attribute_completeness_pct"], m2["attribute_completeness_pct"])
        self.assertEqual((m1["price"], m2["price"], m2["currency"]), (30.0, 25.0, "EUR"))
        self.assertEqual(m2["completeness_rank"]["by"], "attribute_completeness_pct")
        self.assertLessEqual(m2["completeness_rank"]["position"], m2["completeness_rank"]["of"])
        a, b = snaps[0]["id"], snaps[1]["id"]
        self.assertIsNotNone(store.cached_metrics(b))  # cached
        with mock.patch("monitor.history.compute", side_effect=AssertionError("not cached")):
            self.assertEqual(client.get(f"/v1/products/{pid}/snapshots", headers=h).json()["results"], snaps)
        d = client.get(f"/v1/products/{pid}/snapshots/{a}/diff/{b}", headers=h).json()
        self.assertTrue(d["price"]["changed"])
        self.assertEqual((d["price"]["old"]["price"], d["price"]["new"]["price"]), (30.0, 25.0))
        brand = next(x for x in d["attributes"]["added"] if x["field"] == "identity.brand")
        self.assertTrue(brand["evidence"] and brand["evidence"][0]["source_text"])
        self.assertTrue(d["description"]["changed"])
        self.assertTrue(any(line.startswith("+") for line in d["description"]["text_diff"]))
        t = client.get(f"/v1/products/{pid}/trends", headers=h).json()
        self.assertEqual([p["attribute_completeness_pct"] for p in t["points"]],
                         [m1["attribute_completeness_pct"], m2["attribute_completeness_pct"]])
        self.assertEqual(client.get(f"/v1/products/{pid}/snapshots/{a}/diff/999", headers=h).status_code, 404)
        self.assertNotIn("record", str(client.get(f"/v1/products/{pid}/history").json()["snapshots"][0]["data"].keys()))

    def test_snapshots_immutable(self):
        pid = store.pid_for(self.enroll()["product"]["id"])
        with self.assertRaises(sqlite3.IntegrityError):
            with store.connect() as db:
                db.execute("UPDATE snapshots SET data = '{}' WHERE product_id = ?", (pid,))
        with self.assertRaises(sqlite3.IntegrityError):
            with store.connect() as db:
                db.execute("DELETE FROM snapshots")

    def test_no_email_or_internal_id_leak(self):
        body = self.enroll(crawl_now=False)
        pid = body["product"]["id"]
        self.assertGreaterEqual(len(pid), 16)
        self.assertFalse(pid.isdigit())
        for r in (body, client.get(f"/v1/products/{pid}/history").json(), client.get("/v1/monitored").json()):
            text = str(r)
            self.assertNotIn("shop@example.com", text)
            self.assertNotIn("token_hash", text)
            self.assertNotIn("merchant_id", text)
        self.assertEqual(client.get("/v1/products/1/history").status_code, 404)  # internal ids are not addressable

    def test_manage_token_required(self):
        body = self.enroll(crawl_now=False)
        pid, token = body["product"]["id"], body["manage_token"]
        self.assertTrue(token)
        self.assertNotIn(token, str(store.product(pid=store.pid_for(pid))))  # stored hashed only
        self.assertIsNone(self.enroll(crawl_now=False)["manage_token"])  # shown once
        self.assertEqual(client.delete(f"/v1/enroll/{pid}").status_code, 401)
        self.assertEqual(client.delete(f"/v1/enroll/{pid}", headers={"X-Manage-Token": "wrong"}).status_code, 403)
        self.assertEqual(client.post(f"/v1/monitored/{pid}/crawl").status_code, 401)
        self.assertEqual(client.post(f"/v1/monitored/{pid}/crawl", headers={"X-Manage-Token": "wrong"}).status_code, 403)
        self.assertEqual(client.get(f"/v1/products/{pid}/history").json()["product"]["active"], 1)
        self.assertEqual(client.delete(f"/v1/enroll/{pid}", headers={"X-Manage-Token": token}).status_code, 204)

    def test_rate_limit(self):
        with mock.patch.dict(os.environ, {"MONITOR_RATE_LIMIT": "2"}):
            self.enroll(crawl_now=False)
            self.enroll(crawl_now=False)
            r = client.post("/v1/enroll", json={"url": URL, "crawl_now": False})
            self.assertEqual(r.status_code, 429)

    def test_legacy_db_migrated(self):
        with closing(sqlite3.connect(os.environ["MONITOR_DB"])) as db, db:
            db.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, merchant_id INTEGER, url TEXT NOT NULL UNIQUE, "
                       "enrolled_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)")
            db.execute("INSERT INTO products (url, enrolled_at) VALUES (?, 'x')", (URL,))
        (row,) = client.get("/v1/monitored").json()["results"]
        self.assertFalse(row["id"].isdigit())
        self.assertIsNotNone(self.enroll(crawl_now=False)["manage_token"])  # legacy product gets a token once

    def test_unenroll_and_reenroll(self):
        body = self.enroll()
        pid = body["product"]["id"]
        self.assertEqual(client.delete(f"/v1/enroll/{pid}", headers=self.auth(body)).status_code, 204)
        self.assertEqual(crawl.crawl_all(), {})  # inactive products are not crawled
        self.assertEqual(client.get(f"/v1/products/{pid}/history").json()["product"]["active"], 0)
        again = self.enroll(crawl_now=False)
        self.assertEqual((again["product"]["id"], again["created"], again["product"]["active"]), (pid, False, 1))
        self.assertEqual(client.delete("/v1/enroll/999", headers=self.auth(body)).status_code, 404)
        self.assertEqual(client.get("/v1/products/999/history").status_code, 404)

    def test_validation(self):
        self.assertEqual(client.post("/v1/enroll", json={"url": URL, "plan": "gold"}).status_code, 422)
        self.assertEqual(client.post("/v1/enroll", json={"url": URL, "email": "nope"}).status_code, 422)
        with mock.patch.object(safe_fetch, "check_url", side_effect=safe_fetch.FetchError(400, "only http(s) URLs are allowed")):
            self.assertEqual(client.post("/v1/enroll", json={"url": "ftp://x"}).status_code, 400)

    def test_real_url_guard(self):
        for bad in ("ftp://example.com/x", "http://127.0.0.1/", "http://10.0.0.1/p", "file:///etc/passwd"):
            with self.assertRaises(safe_fetch.FetchError, msg=bad):
                REAL_CHECK(bad)

    def test_fetch_error_logged(self):
        pid = store.pid_for(self.enroll(crawl_now=False)["product"]["id"])
        with mock.patch.object(safe_fetch, "fetch_page", side_effect=safe_fetch.FetchError(403, "robots.txt disallows this URL")):
            self.assertEqual(crawl.crawl(pid)["status"], "error")
        self.assertEqual(store.history(pid)["runs"][0]["detail"], "403 robots.txt disallows this URL")

    def test_visibility_skipped_without_keys_and_cap(self):
        runner = mock.Mock()
        self.assertEqual(crawl.visibility_all(runner)["detail"], "no API key")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}):
            self.assertEqual(crawl.visibility_all(runner)["detail"], "BENCHMARK_MAX_USD not set")
        runner.assert_not_called()

    def test_visibility_changed(self):
        pid = store.pid_for(self.enroll()["product"]["id"])
        runner = mock.Mock(return_value={URL: {"mentioned": 2, "queries": 10}})
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k", "BENCHMARK_MAX_USD": "1.5"}):
            self.assertEqual(crawl.visibility_all(runner)["status"], "ok")
        runner.assert_called_once_with([URL], max_usd=1.5)
        ev = store.history(pid)["events"]
        self.assertEqual([e["type"] for e in ev], ["VISIBILITY_CHANGED"])

    def test_visibility_with_harness_mock_adapter(self):
        pid = store.pid_for(self.enroll()["product"]["id"])
        env = {"ANTHROPIC_API_KEY": "unused", "BENCHMARK_MAX_USD": "0.5", "BENCHMARK_MODELS": "mock:mock-1",
               "BENCHMARK_MIN_INTERVAL": "0"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(crawl.visibility_all()["status"], "ok")  # mock provider: no network, no spend
        ev = store.history(pid)["events"]
        self.assertEqual([e["type"] for e in ev], ["VISIBILITY_CHANGED"])
        rate = ev[0]["after"]["mock-1"]["mention_rate"]  # mock is deterministic; matches depend on its URL coin-flip
        self.assertTrue(0 < rate <= 1, rate)

    def test_scheduler_env_gate(self):
        with mock.patch.dict(os.environ, {"MONITOR_ENABLED": ""}):
            self.assertIsNone(scheduler.start())
        with mock.patch.dict(os.environ, {"MONITOR_ENABLED": "1"}):
            s = scheduler.start()
            self.addCleanup(scheduler.stop)
            self.assertEqual(sorted(j.id for j in s.get_jobs()), ["daily_crawl", "weekly_visibility"])

    def test_schema_and_attribute_removed(self):
        old = {"description_sha256": "a", "description_chars": 1, "price": 1, "currency": "EUR",
               "attributes": {"materials.fit": "x"}, "schema": {"offer_schema_present": True}, "languages": []}
        new = {**old, "attributes": {}, "schema": {"offer_schema_present": False}}
        self.assertEqual([e["type"] for e in changes.diff(old, new)], ["ATTRIBUTE_REMOVED", "SCHEMA_CHANGED"])


if __name__ == "__main__":
    unittest.main()
