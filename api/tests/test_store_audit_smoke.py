"""Browser-free smoke test for the website's audit route (POST /v1/audits), over real HTTP with urllib.

The app runs in a local uvicorn thread on a free port; the store fetch is stubbed (no network). Checks what the web UI
relies on: a stored audit, 422 (never 500) for bad input, a coded reason for every fetch failure, and our own rate limit.
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

import main  # noqa: E402
import profile_api  # noqa: E402
import safe_fetch  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "heavy_tee.html").read_text(encoding="utf-8")
URL = "https://shop.example.com/products/heavy-tee"


class StoreAuditSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = mock.patch.dict(os.environ, {
            "PROFILE_DB": os.path.join(cls.tmp.name, "p.db"), "GOVERNANCE_DB": os.path.join(cls.tmp.name, "g.db"),
            "PRODUCTLENS_DATA": str(FIX / "dashboard_records.jsonl"), "PRODUCTLENS_SIGNALS": str(FIX / "dashboard_signals.jsonl"),
            "PRODUCTLENS_VISIBILITY": str(FIX / "nope"), "AUDIT_STORE_RATE_LIMIT": "1000"})
        cls.env.start()
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        cls.base = "http://127.0.0.1:%d" % sock.getsockname()[1]
        cls.server = uvicorn.Server(uvicorn.Config(main.app, log_level="warning"))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(5)
        cls.env.stop()
        cls.tmp.cleanup()

    def setUp(self):
        profile_api._hits.clear()

    def post(self, body):
        req = urllib.request.Request(self.base + "/v1/audits", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read()), r.headers
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_url_audit_is_stored(self):
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(URL, HTML)):
            status, body, _ = self.post({"url": URL})
        self.assertEqual(status, 201, body)
        self.assertGreaterEqual(len(body["id"]), 16)
        self.assertIn("rank", body["audit"])
        with urllib.request.urlopen(f"{self.base}/v1/audits/{body['id']}", timeout=10) as r:
            self.assertEqual(json.loads(r.read())["audit"], body["audit"])

    def test_bad_input_is_422_not_500(self):
        for bad in ({}, {"url": ""}, {"text": ""}, {"language": "es"}, {"url": 123}, {"html": 5},
                    {"html": "<p>x</p>", "language": 5}):
            status, body, _ = self.post(bad)
            self.assertEqual(status, 422, (bad, body))
            self.assertIsInstance(body["detail"], str)

    def test_fetch_failures_keep_their_reason(self):
        """Each store-side failure reaches the UI with the status and reason it maps to a specific message."""
        cases = [(403, "robots.txt disallows this URL"), (502, "upstream HTTP 429"), (502, "upstream HTTP 429 (robots.txt)"),
                 (403, safe_fetch.BLOCKED), (422, safe_fetch.NO_AMAZON), (404, safe_fetch.NOT_FOUND.format(404)),
                 (404, safe_fetch.GONE), (400, safe_fetch.NO_HOST), (504, "fetch deadline exceeded"),
                 (415, safe_fetch.NOT_HTML)]
        for code, detail in cases:
            with mock.patch.object(safe_fetch, "fetch_page", side_effect=safe_fetch.FetchError(code, detail)):
                status, body, _ = self.post({"url": URL})
            self.assertEqual((status, body["detail"]), (code, detail))

    def test_not_a_product_and_not_a_shirt(self):
        page = "<html><head><title>About us</title></head><body><p>We are a small shop.</p></body></html>"
        with mock.patch.object(safe_fetch, "fetch_page", return_value=(URL, page)):
            status, body, _ = self.post({"url": URL})
        self.assertEqual(status, 422)
        self.assertTrue(body["detail"].startswith("not_a_product_page:"), body)
        status, body, _ = self.post({"title": "Ceramic coffee mug", "description": "Stoneware, 350 ml."})
        self.assertEqual(status, 422)
        self.assertTrue(body["detail"].startswith("not_a_shirt:"), body)

    def test_our_rate_limit_is_coded(self):
        with mock.patch.dict(os.environ, {"AUDIT_STORE_RATE_LIMIT": "1"}):
            draft = {"title": "Cotton tee", "description": "100% cotton t-shirt."}
            self.assertEqual(self.post(draft)[0], 201)
            status, body, headers = self.post(draft)
        self.assertEqual(status, 429)
        self.assertTrue(body["detail"].startswith("too_many_requests:"), body)
        self.assertEqual(headers["Retry-After"], "60")


if __name__ == "__main__":
    unittest.main()
