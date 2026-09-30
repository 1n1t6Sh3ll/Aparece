import itertools
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("AUDIT_RATE_LIMIT", "100000")  # per-client limit: test_api.RateLimitTest
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


class FetchCase(unittest.TestCase):
    URL = "https://shop.example.com/products/heavy-tee"

    def setUp(self):
        safe_fetch.clear_cache()
        self.addCleanup(safe_fetch.clear_cache)
        self.archive = mock.patch.object(safe_fetch.commoncrawl, "fetch_archived", return_value=None).start()
        self.addCleanup(mock.patch.stopall)

    def run_fetch(self, responses, path="/v1/extract"):
        calls = []
        def fake(url, **kw):
            calls.append(url)
            return responses[url].pop(0)
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), \
                mock.patch.object(safe_fetch.requests, "get", side_effect=fake), \
                mock.patch.object(safe_fetch.time, "sleep") as sleep:
            r = client.post(path, json={"url": self.URL})
        return r, calls, sleep


class FetchLimitTest(FetchCase):
    """Rate-limited stores: Retry-After retry, page cache, robots 429, Shopify JSON fallback (all mocked)."""

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
        self.assertEqual(r.json()["detail"], safe_fetch.STORE_LIMITED_HELP)

    def test_long_retry_after_not_waited(self):
        r, _, sleep = self.run_fetch({
            "https://shop.example.com/robots.txt": [resp(404)],
            "https://shop.example.com/products/heavy-tee.json": [resp(404)],
            self.URL: [resp(429, headers={"retry-after": "120"})]})
        self.assertEqual(r.json()["detail"], safe_fetch.STORE_LIMITED_HELP)
        sleep.assert_not_called()

    def test_robots_429_is_retry_later(self):
        r, calls, _ = self.run_fetch({"https://shop.example.com/robots.txt": [resp(429), resp(429)]})
        self.assertEqual(r.json()["detail"], "store_rate_limited: upstream HTTP 429 (robots.txt)")
        self.assertNotIn(self.URL, calls)

    def test_robots_5xx_disallows_and_is_not_cached(self):
        robots = "https://shop.example.com/robots.txt"
        for code in (500, 502):
            r, calls, _ = self.run_fetch({robots: [resp(code)]})
            self.assertEqual(r.json()["detail"], f"upstream HTTP {code} (robots.txt): store temporarily unavailable")
            self.assertNotIn(self.URL, calls)
        r, calls, _ = self.run_fetch({robots: [resp(404)], self.URL: [resp(200, FIXTURE)]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn(robots, calls)  # the 5xx answers were not cached

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
        self.assertEqual(r.json()["detail"], safe_fetch.STORE_LIMITED_HELP)
        self.assertNotIn("https://shop.example.com/products/heavy-tee.json", calls)


class ArchiveFallbackTest(FetchCase):
    """Blocked/rate-limited store: Common Crawl copy, honestly labelled (Common Crawl and the store are mocked)."""
    ROBOTS = "https://shop.example.com/robots.txt"
    CAPTURE = {"html": FIXTURE, "capture_date": "2026-08-14", "crawl_id": "CC-MAIN-2026-33",
               "warc_url": "https://data.commoncrawl.org/x.warc.gz"}
    @property
    def LIMITED(self):
        return {"https://shop.example.com/products/heavy-tee.json": [resp(429), resp(429)]}

    def test_429_uses_archive_and_says_so(self):
        self.archive.return_value = self.CAPTURE
        r, calls, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED},
                                     "/v1/audit")
        self.assertEqual(r.status_code, 200, r.text)
        a = r.json()
        self.assertEqual(a["archive"], {"source": "common_crawl", "capture_date": "2026-08-14",
                                        "crawl_id": "CC-MAIN-2026-33", "warc_url": self.CAPTURE["warc_url"]})
        self.assertIn("archive copy captured 2026-08-14, not the live page", a["notes"][0])
        self.assertEqual(self.archive.call_args.args[0], self.URL)
        _, calls, _ = self.run_fetch({}, "/v1/audit")  # cached copy stays labelled
        self.assertEqual(calls, [])

    def test_cached_archive_page_keeps_label_until_it_expires(self):
        """The label is part of the cached page: served together, near the TTL, still labelled (never shown as live)."""
        self.archive.return_value = self.CAPTURE
        now = safe_fetch.time.monotonic()
        with mock.patch.object(safe_fetch.time, "monotonic", return_value=now):
            self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        with mock.patch.object(safe_fetch.time, "monotonic", return_value=now + safe_fetch.PAGE_TTL - 1):
            r, calls, _ = self.run_fetch({}, "/v1/audit")
        self.assertEqual((r.status_code, calls), (200, []))
        self.assertEqual(r.json()["archive"]["capture_date"], "2026-08-14")
        self.assertIn("archive copy", r.json()["notes"][0])

    def test_extract_carries_archive_label(self):
        self.archive.return_value = self.CAPTURE
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        self.assertEqual(r.json()["archive"]["crawl_id"], "CC-MAIN-2026-33")

    def test_live_success_after_archive_drops_label(self):
        self.archive.return_value = self.CAPTURE
        self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        safe_fetch.clear_cache()  # the archived copy expired; the store answers again
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(200, FIXTURE)]}, "/v1/audit")
        self.assertNotIn("archive", r.json())
        self.assertFalse(any("archive" in n for n in r.json()["notes"]))

    def test_401_uses_archive(self):
        self.archive.return_value = self.CAPTURE
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(401)],
                                  "https://shop.example.com/products/heavy-tee.json": [resp(401)]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("archive", r.json())

    def test_archive_failure_never_becomes_a_500(self):
        self.archive.side_effect = RuntimeError("boom")
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        self.assertEqual(r.status_code, 502)
        self.assertIn("Paste the page HTML or text as a draft instead.", r.json()["detail"])

    def test_busy_archive_skipped_with_actionable_error(self):
        self.archive.return_value = self.CAPTURE
        slots = [safe_fetch._archive_slots.acquire(blocking=False) for _ in range(4)]
        try:
            r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        finally:
            for ok in slots:
                ok and safe_fetch._archive_slots.release()
        self.assertEqual(r.status_code, 502)
        self.archive.assert_not_called()
        self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})  # slots were released
        self.archive.assert_called_once()

    def test_blocked_403_uses_archive(self):
        self.archive.return_value = self.CAPTURE
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(403), resp(403)],
                                  "https://shop.example.com/products/heavy-tee.json": [resp(403)]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["archive"]["crawl_id"], "CC-MAIN-2026-33")

    def test_429_without_archive_is_actionable(self):
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        self.assertEqual(r.status_code, 502)
        self.assertTrue(r.json()["detail"].startswith("store_rate_limited: upstream HTTP 429"))
        self.assertIn("Paste the page HTML or text as a draft instead.", r.json()["detail"])
        self.archive.assert_called_once()

    def test_blocked_without_archive_is_actionable(self):
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(403), resp(403)],
                                  "https://shop.example.com/products/heavy-tee.json": [resp(403)]})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], safe_fetch.BLOCKED)
        self.assertTrue(safe_fetch.BLOCKED.startswith("blocked_by_store: This store blocks automated reading from our server."))

    def test_archived_bot_check_page_refused(self):
        self.archive.return_value = {**self.CAPTURE, "html": "<html><head><title>Just a moment...</title></head></html>"}
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)], **self.LIMITED})
        self.assertEqual(r.status_code, 502)

    def test_shopify_json_wins_over_archive(self):
        self.archive.return_value = self.CAPTURE
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(429), resp(429)],
                                  "https://shop.example.com/products/heavy-tee.json": [resp(200, SHOPIFY)]}, "/v1/audit")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("archive", r.json())
        self.archive.assert_not_called()

    def test_robots_disallow_never_reaches_archive(self):
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(200, "User-agent: *\nDisallow: /products/")]})
        self.assertEqual(r.status_code, 403)
        self.archive.assert_not_called()

    def test_robots_429_never_reaches_archive(self):
        self.run_fetch({self.ROBOTS: [resp(429), resp(429)]})
        self.archive.assert_not_called()

    def test_amazon_never_reaches_archive(self):
        r = client.post("/v1/audit", json={"url": "https://www.amazon.com/dp/B085WMXFP3"})
        self.assertEqual(r.status_code, 422)
        self.archive.assert_not_called()

    def test_live_success_has_no_archive(self):
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(200, FIXTURE)]}, "/v1/audit")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("archive", r.json())
        self.assertFalse(any("archive" in n for n in r.json()["notes"]))
        self.archive.assert_not_called()

    def test_pasted_html_with_url_is_not_labelled_archived(self):
        safe_fetch.remember(("archive", self.URL), {"source": "common_crawl", "capture_date": "2026-01-01"}, 600)
        r = client.post("/v1/audit", json={"url": self.URL, "html": FIXTURE})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn("archive", r.json())


class RateLimitTest(unittest.TestCase):
    def test_audit_is_rate_limited_per_client(self):
        import profile_api
        profile_api._hits.clear()
        self.addCleanup(profile_api._hits.clear)
        with mock.patch.dict(os.environ, {"AUDIT_RATE_LIMIT": "2"}):
            codes = [client.post("/v1/audit", json={"title": "Blue cotton tee", "text": "Soft cotton t-shirt."}).status_code
                     for _ in range(3)]
        self.assertEqual(codes[2], 429)
        self.assertNotIn(429, codes[:2])


class FetchErrorTest(FetchCase):
    """Honest, coded reasons for pages we can't read (all mocked)."""
    ROBOTS = "https://shop.example.com/robots.txt"

    def detail(self, page, **extra):
        r, calls, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: page, **extra})
        return r.status_code, r.json().get("detail", ""), calls

    def test_amazon_never_fetched(self):
        for url in ("https://www.amazon.com/dp/B085WMXFP3", "https://amazon.co.uk/dp/X", "https://amzn.to/abc"):
            with mock.patch.object(safe_fetch.requests, "get") as get, mock.patch.object(safe_fetch.socket, "getaddrinfo") as dns:
                r = client.post("/v1/audit", json={"url": url})
            self.assertEqual(r.status_code, 422)
            self.assertTrue(r.json()["detail"].startswith("amazon_not_supported"), r.text)
            get.assert_not_called()
            dns.assert_not_called()

    def test_redirect_to_amazon_not_followed(self):
        hop = mock.MagicMock(is_redirect=True, headers={"location": "https://www.amazon.com/dp/B085WMXFP3"})
        hop.__enter__.return_value = hop
        short = "https://bit.ly/abc"
        calls = []
        def fake(url, **kw):
            calls.append(url)
            return {"https://bit.ly/robots.txt": resp(404), short: hop}[url]
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), \
                mock.patch.object(safe_fetch.requests, "get", side_effect=fake):
            r = client.post("/v1/audit", json={"url": short})
        self.assertEqual(r.status_code, 422)
        self.assertTrue(r.json()["detail"].startswith("amazon_not_supported"), r.text)
        self.assertFalse(any("amazon" in u for u in calls), calls)

    def test_dns_failure(self):
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", side_effect=safe_fetch.socket.gaierror):
            r = client.post("/v1/extract", json={"url": self.URL})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()["detail"].startswith("host_not_found"))
        self.assertIn("does not resolve", r.json()["detail"])  # web/src/lib.tsx maps on this

    def test_blocked(self):
        page = "<html><head><title>Just a moment...</title></head><body>Checking your browser</body></html>"
        for resp_ in (resp(403), resp(401), resp(200, page), resp(503, page)):
            status, detail, _ = self.detail([resp_, resp_], **{self.URL + ".json": [resp(404)]})
            self.assertEqual(status, 403)
            self.assertTrue(detail.startswith("blocked_by_store"), detail)

    def test_blocked_shopify_uses_json(self):
        r, calls, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(403)],
                                      self.URL + ".json": [resp(200, SHOPIFY)]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["normalized"]["commerce"]["price"], 35.0)

    def test_shopify_page_without_product_uses_json(self):
        shell = '<html><head><script src="https://cdn.shopify.com/s/app.js"></script></head><body><div id="app"></div></body></html>'
        r, _, _ = self.run_fetch({self.ROBOTS: [resp(404)], self.URL: [resp(200, shell)],
                                  self.URL + ".json": [resp(200, SHOPIFY)]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("Heavyweight", r.json()["normalized"]["identity"]["product_name"])

    def test_not_found(self):
        status, detail, _ = self.detail([resp(404)])
        self.assertEqual(status, 404)
        self.assertTrue(detail.startswith("page_not_found"), detail)

    def test_not_a_web_page(self):
        for page in (resp(200, "\x89PNG....", {"content-type": "image/png"}), resp(200, "%PDF-1.7 ..."),
                     resp(200, "x", {"content-type": "application/pdf"})):
            status, detail, _ = self.detail([page])
            self.assertEqual(status, 415)
            self.assertTrue(detail.startswith("not_a_web_page"), detail)

    def test_redirect_home_is_product_gone(self):
        hop = mock.MagicMock(is_redirect=True, headers={"location": "https://shop.example.com/search?q=heavy-tee"})
        hop.__enter__.return_value = hop
        status, detail, _ = self.detail([hop], **{"https://shop.example.com/search?q=heavy-tee": [resp(200, FIXTURE)]})
        self.assertEqual(status, 404)
        self.assertTrue(detail.startswith("product_gone"), detail)

    def test_charset_from_meta(self):
        body = '<html><head><meta charset="iso-8859-1"><title>Camiseta algodón</title></head></html>'
        r = resp(200)
        r.iter_content.return_value = [body.encode("latin-1")]
        with mock.patch.object(safe_fetch.socket, "getaddrinfo", PUBLIC_DNS), \
                mock.patch.object(safe_fetch.requests, "get", return_value=r):
            self.assertIn("algodón", safe_fetch.get("https://shop.example.com/p")[2])


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


class RateLimitKeyTest(unittest.TestCase):
    """Behind a trusted proxy (Fly) the key is the LAST X-Forwarded-For entry: the address the proxy appended, which a
    client cannot forge (anything it sends stays earlier in the list)."""

    def hit(self, forwarded, host="172.16.0.1"):
        import profile_api
        req = mock.Mock(headers={"x-forwarded-for": forwarded} if forwarded else {}, client=mock.Mock(host=host))
        profile_api.rate_limit(req, "keytest", "KEYTEST_LIMIT", 1)

    def setUp(self):
        import profile_api
        profile_api._hits.clear()
        self.addCleanup(profile_api._hits.clear)
        patcher = mock.patch.dict(os.environ, {"PROFILE_TRUST_PROXY": "1"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_two_visitors_behind_one_proxy_have_separate_buckets(self):
        self.hit("203.0.113.9")
        self.hit("198.51.100.7")  # a different visitor, same proxy address: not limited
        with self.assertRaises(main.HTTPException) as e:
            self.hit("203.0.113.9")
        self.assertEqual(e.exception.status_code, 429)

    def test_spoofed_leading_entry_does_not_change_the_key(self):
        self.hit("spoofed-1, 203.0.113.9")
        with self.assertRaises(main.HTTPException):
            self.hit("spoofed-2, 203.0.113.9")

    def test_without_trust_flag_the_socket_address_is_used(self):
        with mock.patch.dict(os.environ, {"PROFILE_TRUST_PROXY": "0"}):
            self.hit("203.0.113.9")
            with self.assertRaises(main.HTTPException):
                self.hit("198.51.100.7")  # same socket address: forwarded header ignored
