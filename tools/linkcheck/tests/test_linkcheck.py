"""Link checker with mocked HTTP (no network), status reader, and the peer filter."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from requests.exceptions import ConnectionError as ReqConnectionError
from requests.structures import CaseInsensitiveDict

from analysis.peers import find_peers, similar_peers
from tools.linkcheck import check, status
from tools.linkcheck.check import Checker, Throttle, classify

ALLOW_ALL = "User-agent: *\nDisallow:\n"


class Resp:
    def __init__(self, code, headers=None, body=""):
        self.status_code, self.headers = code, CaseInsensitiveDict(headers or {})
        self.text, self.encoding = body, "utf-8"

    def iter_content(self, n):
        yield self.text.encode()[:n]

    def close(self):
        pass


class FakeSession:
    """routes: {(method, url): Resp}; robots.txt allows all unless routed. Records every request."""

    def __init__(self, routes):
        self.routes, self.calls, self.headers = routes, [], {}

    def request(self, method, url, **kw):
        self.calls.append((method, url))
        assert kw["allow_redirects"] is False and kw["timeout"] == 8
        key = (method, url) if (method, url) in self.routes else ("HEAD", url)  # GET mirrors HEAD unless routed
        if key in self.routes:
            r = self.routes[key]
            if isinstance(r, Exception):
                raise r
            return r
        if url.endswith("/robots.txt"):
            return Resp(200, body=ALLOW_ALL)
        return Resp(404)


def checker(routes, guard=lambda u: None):
    s = FakeSession(routes)
    return Checker(session=s, throttle=Throttle(sleep=lambda s: None), guard=guard), s


U = "https://shop.example.com/products/tee"


class CheckerTest(unittest.TestCase):
    def test_head_ok_is_live_and_sends_honest_ua(self):
        u2 = U + "-2"
        c, s = checker({("HEAD", U): Resp(200), ("GET", U): Resp(200, body="<title>Tee</title>"), ("HEAD", u2): Resp(200)})
        row = c.check(U, "p1")  # the first 2xx HEAD on a host is confirmed with GET
        self.assertEqual((row["status"], row["method"], row["product_id"]), ("live", "GET", "p1"))
        self.assertEqual((c.check(u2)["method"], c.check(u2)["status"]), ("HEAD", "live"))  # then HEAD is trusted
        self.assertIn("ProductLens", s.headers["User-Agent"])
        self.assertIn("checked_at", row)
        self.assertEqual(s.calls[0], ("GET", "https://shop.example.com/robots.txt"))

    def test_head_rejected_falls_back_to_get(self):
        c, _ = checker({("HEAD", U): Resp(405), ("GET", U): Resp(200, body="<title>Tee</title>")})
        row = c.check(U)
        self.assertEqual((row["status"], row["method"]), ("live", "GET"))

    def test_gone(self):
        for code in (404, 410):
            c, _ = checker({("HEAD", U): Resp(code), ("GET", U): Resp(code)})
            self.assertEqual(c.check(U)["status"], "gone")

    def test_soft_404(self):
        c, _ = checker({("HEAD", U): Resp(405), ("GET", U): Resp(200, body="<title>Page not found</title>")})
        self.assertEqual(c.check(U)["status"], "gone")

    def test_redirect_to_home_or_collection_is_away(self):
        for loc, final in (("https://shop.example.com/", "https://shop.example.com/"),
                           ("/collections/all", "https://shop.example.com/collections/all"),
                           ("/search?q=tee", "https://shop.example.com/search?q=tee")):
            c, _ = checker({("HEAD", U): Resp(301, {"location": loc}), ("HEAD", final): Resp(200)})
            row = c.check(U)
            self.assertEqual((row["status"], row["final_url"]), ("redirected_away", final))

    def test_redirect_to_other_product_is_live(self):
        new = "https://shop.example.com/collections/tops/products/tee-v2"
        c, _ = checker({("HEAD", U): Resp(301, {"location": new}), ("HEAD", new): Resp(200)})
        row = c.check(U)
        self.assertEqual((row["status"], row["final_url"]), ("live", new))

    def test_blocked(self):
        for code in (401, 403, 429):
            c, _ = checker({("HEAD", U): Resp(code), ("GET", U): Resp(code)})
            self.assertEqual(c.check(U)["status"], "blocked")
        c, _ = checker({("HEAD", U): Resp(405), ("GET", U): Resp(200, body="<title>Just a moment...</title>")})
        self.assertEqual(c.check(U)["detail"], "challenge")

    def test_head_200_but_get_captcha_is_blocked_and_host_keeps_using_get(self):
        cap = '<html><title>Amazon.com</title><form action="/errors/validateCaptcha">'
        u, u2 = "https://www.amazon.com/dp/B000000001", "https://www.amazon.com/dp/B000000002"
        c, s = checker({("HEAD", u): Resp(200), ("GET", u): Resp(200, body=cap),
                        ("HEAD", u2): Resp(200), ("GET", u2): Resp(200, body=cap)})
        self.assertEqual(c.check(u)["detail"], "challenge")
        row = c.check(u2)
        self.assertEqual((row["status"], row["method"]), ("blocked", "GET"))

    def test_robots_disallow_means_no_page_request(self):
        c, s = checker({("GET", "https://shop.example.com/robots.txt"):
                        Resp(200, body="User-agent: *\nDisallow: /products/\n")})
        row = c.check(U)
        self.assertEqual((row["status"], row["detail"]), ("blocked", "robots_disallowed"))
        self.assertEqual(len(s.calls), 1)

    def test_errors(self):
        c, _ = checker({("HEAD", U): Resp(503), ("GET", U): Resp(503)})
        self.assertEqual(c.check(U)["status"], "error")
        c, _ = checker({("HEAD", U): ReqConnectionError("dns")})
        self.assertEqual(c.check(U)["status"], "error")

    def test_ssrf_guard_on_url_and_redirect_hops(self):
        def guard(u):
            if "169.254" in u:
                raise check.safe_fetch.FetchError(400, "URL resolves to a non-public address")
        c, s = checker({}, guard)
        self.assertEqual(c.check("http://169.254.169.254/latest")["status"], "error")
        self.assertEqual(s.calls, [])
        c, s = checker({("HEAD", U): Resp(302, {"location": "http://169.254.169.254/x"})}, guard)
        row = c.check(U)
        self.assertEqual((row["status"], row["detail"]), ("error", "URL resolves to a non-public address"))
        self.assertNotIn(("HEAD", "http://169.254.169.254/x"), s.calls)

    def test_throttle_one_request_per_second_per_host(self):
        t, slept = [0.0], []
        th = Throttle(sleep=slept.append, clock=lambda: t[0])
        th.wait("a.com"), th.wait("a.com"), th.wait("b.com"), th.wait("a.com")
        self.assertEqual(slept, [1.0, 2.0])

    def test_classify_table(self):
        self.assertEqual(classify(U, U, 500, {})[0], "error")
        self.assertEqual(classify(U, U, 200, {"cf-mitigated": "challenge"})[0], "blocked")
        self.assertEqual(classify(U, "https://parked.example.net/", 200, {})[0], "redirected_away")

    def test_run_is_resumable(self):
        c, s = checker({("HEAD", U): Resp(200), ("GET", U): Resp(200)})
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "ls.jsonl"
            items = [(U, "p1"), (U + "/", "p1")]  # same page, de-duplicated by url_key upstream
            self.assertEqual(check.run(items[:1], out, checker=c, log=lambda *_: None), {"live": 1})
            self.assertEqual(check.run(items[:1], out, checker=c, log=lambda *_: None), {})
            self.assertEqual(len(out.read_text().splitlines()), 1)

    def test_load_urls_dedups_records_and_text(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.jsonl", Path(d) / "b.txt"
            a.write_text(json.dumps({"product_id": "p1", "source": {"canonical_url": U}}) + "\n")
            b.write_text(U + "/\nhttps://other.example.com/p/2\n")
            self.assertEqual(check.load_urls([a, b]), [(U, "p1"), ("https://other.example.com/p/2", None)])


def rec(pid, url, **kw):
    return {"product_id": pid, "source": {"url": url, "language": "en"},
            "identity": {"product_type": "t_shirt", **kw}, "commerce": {}}


class FilterTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.path = Path(self.d.name) / "link_status.jsonl"
        self.env = mock.patch.dict(os.environ, {"PRODUCTLENS_LINK_STATUS": str(self.path)})
        self.env.start()
        self.recs = [rec(p, f"https://s.example.com/products/{p}") for p in ("t", "live", "gone", "away", "blk", "err")]

    def tearDown(self):
        self.env.stop()
        self.d.cleanup()

    def write(self):
        rows = [{"url": f"https://www.s.example.com/products/{p}/", "status": s, "checked_at": "2026-09-29T00:00:00+00:00"}
                for p, s in (("live", "live"), ("gone", "gone"), ("away", "redirected_away"),
                             ("blk", "blocked"), ("err", "error"))]
        self.path.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def ids(self, pairs):
        return sorted(p["product_id"] for _, p in pairs)

    def test_missing_status_file_changes_nothing(self):
        self.assertEqual(self.ids(find_peers(self.recs[0], self.recs)), ["away", "blk", "err", "gone", "live"])
        self.assertEqual(status.flag(self.recs[2]), {"link_status": None, "link_unverified": False})

    def test_dead_links_excluded_unverified_flagged(self):
        self.write()
        self.assertEqual(self.ids(find_peers(self.recs[0], self.recs)), ["blk", "err", "live"])
        self.assertEqual(sorted(r["product_id"] for r in similar_peers(self.recs[0], self.recs)["peers"]),
                         ["blk", "err", "live"])
        self.assertEqual(status.flag(self.recs[4]), {"link_status": "blocked", "link_unverified": True})
        self.assertEqual(status.flag(self.recs[1])["link_unverified"], False)

    def test_later_line_wins(self):
        self.write()
        with open(self.path, "a") as f:
            f.write(json.dumps({"url": "https://s.example.com/products/gone", "status": "live"}) + "\n")
        os.utime(self.path, (1, 2))  # new mtime -> reload
        self.assertIn("gone", self.ids(find_peers(self.recs[0], self.recs)))


if __name__ == "__main__":
    unittest.main()
