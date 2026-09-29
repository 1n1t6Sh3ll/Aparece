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


class ApiTest(unittest.TestCase):
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
        def fake_get(url):
            return url, 200, "User-agent: *\nDisallow: /products/"
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), mock.patch.object(safe_fetch, "get", fake_get):
            r = client.post("/v1/extract", json={"url": "https://shop.example.com/products/heavy-tee"})
        self.assertEqual(r.status_code, 403)

    def test_url_fetch(self):
        def fake_get(url):
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
