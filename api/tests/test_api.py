import itertools
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
import safe_fetch  # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures" / "heavy_tee.html").read_text(encoding="utf-8")
PUBLIC_DNS = mock.Mock(return_value=[(2, 1, 6, "", ("93.184.216.34", 443))])
EXT = "chrome-extension://" + "a" * 32
client = TestClient(main.app)


def resp(status, body="", headers=None):
    r = mock.MagicMock(is_redirect=False, status_code=status, headers=headers or {}, encoding="utf-8")
    r.iter_content.return_value = [body.encode()]
    r.__enter__.return_value = r
    return r


SHOPIFY = ('{"product": {"title": "Heavyweight Organic Cotton Tee", "vendor": "Example", "product_type": "T-shirts",'
           ' "body_html": "<p>100% organic cotton, 240 gsm.</p>", "images": [],'
           ' "variants": [{"title": "M", "price": "35.00", "price_currency": "EUR", "sku": "HT-M"}]}}')


class FetchLimitTest(unittest.TestCase):
    """Rate-limited stores: Retry-After retry, page cache, robots 429, Shopify JSON fallback (all mocked)."""
    URL = "https://shop.example.com/products/heavy-tee"

    def setUp(self):
        safe_fetch.clear_cache()
        self.addCleanup(safe_fetch.clear_cache)

    def run_fetch(self, responses):
        calls = []
        def fake(url, **kw):
            calls.append(url)
            return responses[url].pop(0)
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), \
                mock.patch.object(safe_fetch.requests, "get", side_effect=fake), \
                mock.patch.object(safe_fetch.time, "sleep") as sleep:
            r = client.post("/v1/extract", json={"url": self.URL})
        return r, calls, sleep

    def test_429_then_200_honours_retry_after_and_caches(self):
        r, calls, sleep = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(404)],
            self.URL: [resp(429, headers={"retry-after": "2"}), resp(200, FIXTURE)]})
        self.assertEqual(r.status_code, 200, r.text)
        sleep.assert_called_once_with(2.0)
        self.assertEqual(calls.count(self.URL), 2)
        r, calls, _ = self.run_fetch({})  # served from the 10-minute cache, no request
        self.assertEqual((r.status_code, calls), (200, []))

    def test_429_twice_gives_rate_limit_error(self):
        r, calls, sleep = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(404)],
            "https://shop.example.com/products/heavy-tee.json": [resp(429), resp(429)],
            self.URL: [resp(429, headers={"retry-after": "1"}), resp(429)]})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.json()["detail"], "upstream HTTP 429")

    def test_long_retry_after_not_waited(self):
        r, _, sleep = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(404)],
            "https://shop.example.com/products/heavy-tee.json": [resp(404)],
            self.URL: [resp(429, headers={"retry-after": "120"})]})
        self.assertEqual(r.json()["detail"], "upstream HTTP 429")
        sleep.assert_not_called()

    def test_robots_429_is_retry_later(self):
        r, calls, _ = self.run_fetch({"https://shop.example.com/robots.txt": [resp(429), resp(429)]})
        self.assertEqual(r.json()["detail"], "upstream HTTP 429 (robots.txt)")
        self.assertNotIn(self.URL, calls)

    def test_shopify_json_fallback(self):
        r, calls, _ = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(200, "User-agent: *\nDisallow: /cart")],
            "https://shop.example.com/products/heavy-tee.json": [resp(200, SHOPIFY)],
            self.URL: [resp(429), resp(429)]})
        self.assertEqual(r.status_code, 200, r.text)
        n = r.json()["normalized"]
        self.assertEqual(n["commerce"]["price"], 35.0)
        self.assertEqual(n["commerce"]["currency"], "EUR")
        self.assertIn("Heavyweight", n["identity"]["product_name"])

    def test_shopify_json_respects_robots(self):
        r, calls, _ = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(200, "User-agent: *\nDisallow: /products/*.json")],
            self.URL: [resp(429), resp(429)]})
        self.assertEqual(r.json()["detail"], "upstream HTTP 429")
        self.assertNotIn("https://shop.example.com/products/heavy-tee.json", calls)


class ApiTest(unittest.TestCase):
    def setUp(self):
        safe_fetch.clear_cache()

    def test_health(self):
        r = client.get("/v1/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_extract_html(self):
        r = client.post("/v1/extract", json={"html": FIXTURE, "url": "https://shop.example.com/products/heavy-tee"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(set(body), {"product_id", "language", "raw", "normalized", "evidence", "conflicts", "quality_status"})
        self.assertTrue(body["product_id"].startswith("p_"))
        self.assertEqual(body["language"], "en")
        n = body["normalized"]
        self.assertEqual(n["commerce"]["price"], 35.0)
        self.assertEqual(n["commerce"]["currency"], "EUR")
        self.assertEqual(n["materials"]["fabric_weight_gsm"], 240)
        self.assertIn(body["quality_status"], ("high", "medium", "low"))
        self.assertTrue(body["evidence"])

    def test_language_override_and_text(self):
        r = client.post("/v1/extract", json={"text": "100% algodón\nManga corta", "language": "es"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["language"], "es")
        self.assertEqual(r.json()["quality_status"], "reject")  # no name/price in plain text

    def test_missing_input(self):
        self.assertEqual(client.post("/v1/extract", json={}).status_code, 422)

    def test_ssrf_blocked(self):
        for url in ("http://127.0.0.1/x", "http://10.0.0.5/", "http://169.254.169.254/latest", "http://[::1]/",
                    "file:///etc/passwd", "http://localhost:8000/"):
            r = client.post("/v1/extract", json={"url": url})
            self.assertEqual(r.status_code, 400, url)

    def test_robots_disallow(self):
        def fake_get(url, deadline=None):
            return url, 200, "User-agent: *\nDisallow: /products/"
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), mock.patch.object(safe_fetch, "get", fake_get):
            r = client.post("/v1/extract", json={"url": "https://shop.example.com/products/heavy-tee"})
        self.assertEqual(r.status_code, 403)

    def test_url_fetch(self):
        def fake_get(url, deadline=None):
            return (url, 404, "") if url.endswith("/robots.txt") else (url, 200, FIXTURE)
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), mock.patch.object(safe_fetch, "get", fake_get):
            r = client.post("/v1/extract", json={"url": "https://shop.example.com/products/heavy-tee"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["normalized"]["commerce"]["price"], 35.0)

    def test_size_limit_and_redirect_recheck(self):
        big = mock.MagicMock(is_redirect=False, status_code=200)
        big.__enter__.return_value = big
        big.iter_content.return_value = iter([b"x" * 65536] * 60)
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), \
                mock.patch.object(safe_fetch.requests, "get", return_value=big):
            with self.assertRaises(safe_fetch.FetchError) as e:
                safe_fetch.get("https://shop.example.com/p")
        self.assertEqual(e.exception.status, 413)
        hop = mock.MagicMock(is_redirect=True, headers={"location": "http://127.0.0.1/admin"})
        hop.__enter__.return_value = hop
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", side_effect=lambda h, *a, **k: [(2, 1, 6, "", (
                "127.0.0.1" if h == "127.0.0.1" else "93.184.216.34", 80))]), \
                mock.patch.object(safe_fetch.requests, "get", return_value=hop):
            with self.assertRaises(safe_fetch.FetchError) as e:
                safe_fetch.get("https://shop.example.com/p")
        self.assertEqual(e.exception.status, 400)

    def test_total_deadline(self):
        slow = mock.MagicMock(is_redirect=False, status_code=200)
        slow.__enter__.return_value = slow
        slow.iter_content.return_value = iter([b"x"] * 10)
        clock = itertools.count(0, 5)  # each monotonic() call advances 5 s; deadline is 10 s total
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS),                 mock.patch.object(safe_fetch.requests, "get", return_value=slow),                 mock.patch.object(safe_fetch.time, "monotonic", lambda: next(clock)):
            with self.assertRaises(safe_fetch.FetchError) as e:
                safe_fetch.get("https://shop.example.com/p")
        self.assertEqual(e.exception.status, 504)

    def test_redirect_without_location(self):
        hop = mock.MagicMock(is_redirect=True, headers={})
        hop.__enter__.return_value = hop
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS),                 mock.patch.object(safe_fetch.requests, "get", return_value=hop):
            with self.assertRaises(safe_fetch.FetchError) as e:
                safe_fetch.get("https://shop.example.com/p")
        self.assertEqual(e.exception.status, 400)

    def test_qwen_not_implemented(self):
        with mock.patch.dict(os.environ, {"MODEL_BACKEND": "qwen"}):
            self.assertEqual(client.post("/v1/extract", json={"html": FIXTURE}).status_code, 501)

    def test_cors(self):
        pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
        ok = client.options("/v1/extract", headers={"Origin": EXT, **pre})
        self.assertEqual(ok.headers.get("access-control-allow-origin"), EXT)
        bad = client.options("/v1/extract", headers={"Origin": "https://evil.example", **pre})
        self.assertIsNone(bad.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
