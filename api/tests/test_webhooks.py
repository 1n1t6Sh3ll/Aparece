"""Outgoing webhooks (TEAM-51) against a local mock receiver. No network beyond 127.0.0.1, no paid calls."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import monitor_api  # noqa: E402
import safe_fetch  # noqa: E402
from monitor import crawl, store as monitor_store  # noqa: E402
from webhooks import core, store  # noqa: E402

FIX = Path(__file__).resolve().parents[2] / "monitor" / "fixtures"
PAGES = {v: (FIX / f"tee_{v}.html").read_text(encoding="utf-8") for v in ("v1", "v2")}
URL = "https://shop.example.com/products/everyday-tee"
EMAIL = "shop@example.com"
client = TestClient(main.app)
REAL_CHECK = safe_fetch.check_url


class Receiver:
    """Local HTTP server that records every POST and answers with the next queued status (default 200)."""

    def __init__(self):
        self.requests, self.statuses = [], []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                outer.requests.append({"headers": dict(self.headers), "body": body})
                code = outer.statuses.pop(0) if outer.statuses else 200
                self.send_response(code)
                if 300 <= code < 400:
                    self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/hook"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def bodies(self):
        return [json.loads(r["body"]) for r in self.requests]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class WebhooksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(__file__).parent / "fixtures" / "dashboard_records.jsonl"
        env = {"MONITOR_DB": os.path.join(self.tmp.name, "m.db"), "WEBHOOKS_DB": os.path.join(self.tmp.name, "w.db"),
               "PRODUCTLENS_DATA": str(data), "MONITOR_DELAY": "0", "WEBHOOKS_WORKER": "0",
               "ANTHROPIC_API_KEY": "", "OPENAI_API_KEY": "", "BENCHMARK_MAX_USD": ""}
        self.page = PAGES["v1"]
        # check_url is patched to allow the loopback mock receiver; SSRF tests use REAL_CHECK explicitly.
        for p in (mock.patch.dict(os.environ, env), mock.patch.object(safe_fetch, "check_url"),
                  mock.patch.object(safe_fetch, "fetch_page", side_effect=lambda u: (u, self.page))):
            p.start()
            self.addCleanup(p.stop)
        self.rx = Receiver()
        self.addCleanup(self.rx.close)
        self.addCleanup(self.tmp.cleanup)
        monitor_api._hits.clear()
        r = client.post("/v1/enroll", json={"url": URL, "email": EMAIL, "crawl_now": False})
        self.assertEqual(r.status_code, 201, r.text)
        self.product, self.token = r.json()["product"]["id"], r.json()["manage_token"]
        self.auth = {"X-Manage-Token": self.token}

    def hook(self, events=None, url=None):
        r = client.post("/v1/webhooks", headers=self.auth,
                        json={"product_id": self.product, "url": url or self.rx.url, "events": events or list(core.EVENTS)})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def test_auth_validation_and_secret_shown_once(self):
        body = {"product_id": self.product, "url": self.rx.url, "events": ["product.changed"]}
        self.assertEqual(client.post("/v1/webhooks", json=body).status_code, 401)
        self.assertEqual(client.post("/v1/webhooks", json=body, headers={"X-Manage-Token": "nope"}).status_code, 403)
        bad = client.post("/v1/webhooks", json={**body, "events": ["order.paid"]}, headers=self.auth)
        self.assertEqual(bad.status_code, 422)
        h = self.hook(["product.changed"])
        self.assertTrue(h["secret"].startswith("whsec_"))
        listed = client.get("/v1/webhooks", headers=self.auth).json()["results"]
        self.assertEqual([w["id"] for w in listed], [h["webhook"]["id"]])
        self.assertNotIn(h["secret"], json.dumps(listed))
        self.assertEqual(client.get("/v1/webhooks", headers={"X-Manage-Token": "other"}).json()["results"], [])
        wid = h["webhook"]["id"]
        self.assertEqual(client.get(f"/v1/webhooks/{wid}/deliveries", headers={"X-Manage-Token": "x"}).status_code, 403)
        self.assertEqual(client.delete(f"/v1/webhooks/{wid}", headers={"X-Manage-Token": "x"}).status_code, 403)
        self.assertEqual(client.delete(f"/v1/webhooks/{wid}", headers=self.auth).status_code, 204)
        self.assertEqual(client.get("/v1/webhooks", headers=self.auth).json()["results"], [])
        self.assertEqual(client.get(f"/v1/webhooks/{wid}/deliveries", headers=self.auth).status_code, 404)

    def test_test_event_is_signed_and_timed_out_at_5s(self):
        h = self.hook(["product.changed"])
        with mock.patch.object(core.requests, "post", wraps=core.requests.post) as post:
            r = client.post(f"/v1/webhooks/{h['webhook']['id']}/test", headers=self.auth)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["delivery"]["status"], "delivered")
        self.assertEqual(post.call_args.kwargs["timeout"], 5)
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        req = self.rx.requests[0]
        body = json.loads(req["body"])
        self.assertEqual(body["type"], "webhook.test")
        self.assertEqual(body["product"], {"id": self.product})
        self.assertEqual(req["headers"]["X-ProductLens-Event-Id"], body["id"])
        sig = req["headers"]["X-ProductLens-Signature"]
        self.assertRegex(sig, r"^t=\d+,v1=[0-9a-f]{64}$")
        self.assertTrue(core.verify(h["secret"], req["body"], sig))
        self.assertFalse(core.verify(h["secret"], req["body"] + b" ", sig))
        self.assertFalse(core.verify("whsec_wrong", req["body"], sig))
        self.assertFalse(core.verify(h["secret"], req["body"], sig, now=time.time() + 3600))

    def test_crawl_emits_changed_snapshot_audit_without_pii(self):
        self.hook()
        pid = monitor_store.pid_for(self.product)
        crawl.crawl(pid)
        self.page = PAGES["v2"]
        crawl.crawl(pid)
        types = [b["type"] for b in self.rx.bodies()]
        self.assertEqual(types.count("snapshot.created"), 2)
        self.assertEqual(types.count("audit.completed"), 2)
        changed = [b for b in self.rx.bodies() if b["type"] == "product.changed"]
        self.assertEqual(len(changed), 1)
        self.assertIn("PRICE_CHANGED", changed[0]["data"]["change_types"])
        for r in self.rx.requests:
            self.assertNotIn(EMAIL.encode(), r["body"])
            self.assertNotIn(self.token.encode(), r["body"])
        self.assertEqual(len({b["id"] for b in self.rx.bodies()}), len(self.rx.requests))

    def test_visibility_changed(self):
        self.hook(["visibility.changed"])
        pid = monitor_store.pid_for(self.product)
        crawl.crawl(pid)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake", "BENCHMARK_MAX_USD": "1"}):
            crawl.visibility_all(runner=lambda urls, max_usd: {URL: {"m": {"hit_rate": 0.5}}})
        self.assertEqual([b["type"] for b in self.rx.bodies()], ["visibility.changed"])
        self.assertEqual(self.rx.bodies()[0]["data"]["after"], {"m": {"hit_rate": 0.5}})

    def test_subscription_filter(self):
        self.hook(["visibility.changed"])
        crawl.crawl(monitor_store.pid_for(self.product))
        self.assertEqual(self.rx.requests, [])

    def test_retries_with_backoff_then_dead_letter_same_event_id(self):
        h = self.hook(["snapshot.created"])
        wid = h["webhook"]["id"]
        self.rx.statuses = [500] * 10
        eid = core.emit(self.product, "snapshot.created", {"snapshot_id": 1})
        d = store.deliveries(wid)[0]
        self.assertEqual((d["status"], d["attempts"], d["last_status_code"]), ("pending", 1, 500))
        self.assertAlmostEqual(d["next_attempt_at"] - time.time(), 30, delta=5)
        self.assertEqual(core.deliver_due(), [])  # not due yet
        now = time.time()
        for i in range(2, 6):
            now += 10 ** 5
            out = core.deliver_due(now=now)
            self.assertEqual(out[0]["attempts"], i)
            if i == 2:
                self.assertAlmostEqual(store.deliveries(wid)[0]["next_attempt_at"] - now, 120, delta=1)
        self.assertEqual(store.deliveries(wid)[0]["status"], "dead")
        self.assertEqual(core.deliver_due(now=now + 10 ** 6), [])
        self.assertEqual(len(self.rx.requests), 5)
        self.assertEqual({r["headers"]["X-ProductLens-Event-Id"] for r in self.rx.requests}, {eid})
        self.assertEqual(len({r["body"] for r in self.rx.requests}), 1)  # identical body on every retry

    def test_redirect_not_followed(self):
        h = self.hook(["snapshot.created"])
        self.rx.statuses = [302]
        core.emit(self.product, "snapshot.created", {})
        d = store.deliveries(h["webhook"]["id"])[0]
        self.assertEqual((d["status"], d["last_status_code"], d["last_error"]), ("pending", 302, "redirect not followed"))
        self.assertEqual(len(self.rx.requests), 1)

    def test_disable_after_repeated_failures(self):
        h = self.hook(["snapshot.created"])
        wid = h["webhook"]["id"]
        self.rx.statuses = [500] * 10
        with mock.patch.dict(os.environ, {"WEBHOOKS_DISABLE_AFTER": "3"}):
            for _ in range(3):
                core.emit(self.product, "snapshot.created", {})
        w = client.get("/v1/webhooks", headers=self.auth).json()["results"][0]
        self.assertFalse(w["active"])
        self.assertIn("3 consecutive", w["disabled_reason"])
        self.assertEqual({d["status"] for d in store.deliveries(wid)}, {"dead"})
        self.assertIsNone(core.emit(self.product, "snapshot.created", {}))
        self.assertEqual(client.post(f"/v1/webhooks/{wid}/test", headers=self.auth).status_code, 409)

    def test_ssrf_rejected_on_create_and_every_attempt(self):
        with mock.patch.object(safe_fetch, "check_url", REAL_CHECK):
            for url in (self.rx.url, "file:///etc/passwd", "http://169.254.169.254/"):
                r = client.post("/v1/webhooks", headers=self.auth,
                                json={"product_id": self.product, "url": url, "events": ["snapshot.created"]})
                self.assertEqual(r.status_code, 400, url)
        h = self.hook(["snapshot.created"])  # created while check_url allowed loopback
        with mock.patch.object(safe_fetch, "check_url", REAL_CHECK):
            core.emit(self.product, "snapshot.created", {})
        d = store.deliveries(h["webhook"]["id"])[0]
        self.assertTrue(d["last_error"].startswith("url rejected"))
        self.assertEqual(self.rx.requests, [])


if __name__ == "__main__":
    unittest.main()
