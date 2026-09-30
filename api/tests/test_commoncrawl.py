"""Common Crawl archive fallback (api/commoncrawl.py) with the network mocked.

Fixtures are recorded from the live service on 2026-09-29: cc_collinfo.json (first 3 crawls of collinfo.json),
cc_cdx.jsonl (one CDX index row) and cc_record.warc.gz (a real WARC response record's headers, with the HTML body
cut down to a small product page so the fixture stays small; digests/lengths in it are the originals)."""
import gzip
import json
import sys
import unittest
import zlib
from pathlib import Path
from unittest import mock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import commoncrawl as cc  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
COLLINFO = json.loads((FIX / "cc_collinfo.json").read_text(encoding="utf-8"))
CDX = (FIX / "cc_cdx.jsonl").read_text(encoding="utf-8")
RECORD = (FIX / "cc_record.warc.gz").read_bytes()
ROW = json.loads(CDX)
URL = "https://www.allbirds.com/products/mens-strider-medium-grey?variant=123#reviews"
NEWEST, SECOND = COLLINFO[0]["id"], COLLINFO[1]["id"]


class Resp:
    def __init__(self, status=200, text="", content=b"", data=None):
        self.status_code = status
        self.content = json.dumps(data).encode() if data is not None else (text.encode() or content)
        self.closed = False

    def iter_content(self, size):
        for i in range(0, len(self.content), size):
            yield self.content[i:i + size]

    def close(self):
        self.closed = True


def network(index):
    """Fake requests.get: collinfo, CDX answers from index[(crawl, url)] (default 404), WARC range reads."""
    calls = []

    def get(url, headers=None, timeout=None, allow_redirects=True, params=None, stream=False):
        assert stream, "every body must be streamed"
        calls.append((url, params, headers, allow_redirects))
        if url == cc.COLLINFO:
            return Resp(data=COLLINFO)
        if url.startswith("https://index.commoncrawl.org/"):
            crawl = url.rsplit("/", 1)[1][:-len("-index")]
            ans = index.get((crawl, params["url"]))
            if isinstance(ans, int):
                return Resp(ans, "<html>gateway</html>")
            return Resp(200, ans) if ans else Resp(404, '{"message": "No Captures found"}')
        if url == cc.DATA + ROW["filename"]:
            return Resp(206, content=index.get("record", RECORD))
        return Resp(404)
    return get, calls


class CommonCrawlTest(unittest.TestCase):
    def setUp(self):
        cc.clear_cache()

    def run_with(self, index, url=URL, **kw):
        get, calls = network(index)
        with mock.patch.object(cc.requests, "get", side_effect=get):
            return cc.fetch_archived(url, **kw), calls

    def test_found_via_normalized_variant(self):
        res, calls = self.run_with({(NEWEST, "https://www.allbirds.com/products/mens-strider-medium-grey"): CDX})
        self.assertEqual(set(res), {"html", "capture_date", "crawl_id", "warc_url"})
        self.assertEqual(res["capture_date"], "2026-07-14")
        self.assertEqual(res["crawl_id"], NEWEST)
        self.assertEqual(res["warc_url"], cc.DATA + ROW["filename"])
        self.assertIn('"@type":"Product"', res["html"])
        self.assertIn("Men’s Strider", res["html"])
        self.assertTrue(res["html"].endswith("</html>"))
        # query first as given (with status filter), then without query/fragment
        self.assertEqual(calls[1][1], {"url": URL, "output": "json", "filter": "status:200"})
        # the WARC read is a byte range for exactly the record, honest UA, never a redirect follow
        off, length = int(ROW["offset"]), int(ROW["length"])
        self.assertEqual(calls[-1][2]["Range"], f"bytes={off}-{off + length - 1}")
        for url, _, headers, redirects in calls:
            self.assertIn("ProductLens", headers["User-Agent"])
            self.assertFalse(redirects)
            self.assertTrue(url.startswith(("https://index.commoncrawl.org/", "https://data.commoncrawl.org/")))

    def test_transient_index_error_retried_once(self):
        get, _ = network({})
        with mock.patch.object(cc.requests, "get", side_effect=get), \
                mock.patch.object(cc, "lookup", side_effect=[requests.HTTPError("index 504"), ROW]) as look:
            res = cc.fetch_archived(URL)
        self.assertEqual((res["crawl_id"], look.call_count), (NEWEST, 2))

    def test_wildcard_url_never_queried(self):
        res, calls = self.run_with({}, url="https://www.allbirds.com/products/*")
        self.assertIsNone(res)
        self.assertEqual(calls, [])

    def test_capture_of_another_url_is_ignored(self):
        other = CDX.replace("mens-strider-medium-grey", "another-product")
        res, _ = self.run_with({(NEWEST, "https://www.allbirds.com/products/mens-strider-medium-grey"): other})
        self.assertIsNone(res)

    def test_older_crawl_and_overloaded_index(self):
        bare = "https://www.allbirds.com/products/mens-strider-medium-grey"
        res, _ = self.run_with({(NEWEST, URL): 504, (SECOND, bare): CDX})
        self.assertEqual(res["crawl_id"], SECOND)

    def test_not_found_returns_none(self):
        res, calls = self.run_with({})
        self.assertIsNone(res)
        self.assertEqual(sum("-index" in c[0] for c in calls), len(COLLINFO) * len(cc.variants(URL)))

    def test_collinfo_cached(self):
        _, first = self.run_with({})
        _, second = self.run_with({})
        self.assertEqual(sum(c[0] == cc.COLLINFO for c in first + second), 1)

    def test_bad_input_and_network_error(self):
        self.assertIsNone(cc.fetch_archived("ftp://x.example/a"))
        self.assertIsNone(cc.fetch_archived("not a url"))
        with mock.patch.object(cc.requests, "get", side_effect=requests.ConnectionError("down")):
            self.assertIsNone(cc.fetch_archived(URL))

    def test_deadline(self):
        res, calls = self.run_with({}, timeout_total=0)
        self.assertIsNone(res)
        self.assertEqual(calls, [])

    def test_amazon_variants(self):
        v = cc.variants("https://www.amazon.com/Hanes-Mens-Tee/dp/B07ZPKBL9V/ref=sr_1_1?keywords=tee")
        self.assertEqual(v, ["https://www.amazon.com/Hanes-Mens-Tee/dp/B07ZPKBL9V/ref=sr_1_1?keywords=tee",
                             "https://www.amazon.com/Hanes-Mens-Tee/dp/B07ZPKBL9V/ref=sr_1_1",
                             "https://www.amazon.com/Hanes-Mens-Tee/dp/B07ZPKBL9V",
                             "https://www.amazon.com/dp/B07ZPKBL9V",
                             "https://www.amazon.com/dp/B07ZPKBL9V/",
                             "https://www.amazon.com/gp/product/B07ZPKBL9V"])
        self.assertEqual(cc.variants("https://amazon.co.uk/gp/product/B000000001"),
                         ["https://amazon.co.uk/gp/product/B000000001", "https://www.amazon.co.uk/dp/B000000001",
                          "https://www.amazon.co.uk/dp/B000000001/"])

    def test_www_and_scheme_variants_collapse(self):
        # the CDX index ignores scheme and "www." (SURT keys), so these are one lookup
        self.assertEqual(cc.variants("http://shop.example.com/products/tee"), ["http://shop.example.com/products/tee"])

    def test_parse_record_edge_cases(self):
        raw = gzip.decompress(RECORD)
        self.assertIsNone(cc.parse_record(gzip.compress(raw.replace(b"HTTP/1.1 200 ", b"HTTP/1.1 301 "))))
        self.assertIsNone(cc.parse_record(gzip.compress(raw.replace(b"WARC-Type: response", b"WARC-Type: request"))))
        body = b"<html><body>caf\xc3\xa9</body></html>"
        z = zlib.compressobj(wbits=31)
        gz = z.compress(body) + z.flush()
        chunked = b"%x\r\n" % len(gz) + gz + b"\r\n0\r\n\r\n"
        http = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Encoding: gzip\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n" + chunked)
        rec = b"WARC/1.0\r\nWARC-Type: response\r\nContent-Length: %d\r\n\r\n" % len(http) + http + b"\r\n\r\n"
        self.assertEqual(cc.parse_record(gzip.compress(rec)), body.decode())

    def test_gzip_bomb_record_dropped(self):
        bomb = gzip.compress(b"WARC/1.0\r\nWARC-Type: response\r\n\r\n" + b"\0" * (cc.MAX_INFLATED + 10))
        self.assertLess(len(bomb), 20_000)
        with self.assertRaises(cc.TooLarge):
            cc.parse_record(bomb)
        bare = "https://www.allbirds.com/products/mens-strider-medium-grey"
        res, _ = self.run_with({(NEWEST, bare): CDX, "record": bomb})
        self.assertIsNone(res)
        # a gzip Content-Encoding bomb inside a small record is capped too
        inner = zlib.compressobj(wbits=31)
        payload = inner.compress(b"a" * (cc.MAX_INFLATED + 10)) + inner.flush()
        http = b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Encoding: gzip\r\n\r\n" + payload
        rec = b"WARC/1.0\r\nWARC-Type: response\r\nContent-Length: %d\r\n\r\n" % len(http) + http
        with self.assertRaises(cc.TooLarge):
            cc.parse_record(gzip.compress(rec))

    def test_body_caps(self):
        big = Resp(200, content=b"x" * (cc.MAX_INDEX + 1))
        with mock.patch.object(cc.requests, "get", return_value=big):
            with self.assertRaises(cc.TooLarge):
                cc._get(cc.COLLINFO, cc.time.monotonic() + 5, cc.MAX_INDEX)
        self.assertTrue(big.closed)
        # the WARC Range read never asks for, or accepts, more than the CDX length (and never over MAX_RECORD)
        self.assertIsNone(cc.fetch_record({**ROW, "length": str(cc.MAX_RECORD + 1)}, cc.time.monotonic() + 5))
        with mock.patch.object(cc.requests, "get", return_value=Resp(206, content=RECORD + b"extra")):
            with self.assertRaises(cc.TooLarge):
                cc.fetch_record({**ROW, "length": str(len(RECORD))}, cc.time.monotonic() + 5)

    def test_deadline_between_chunks(self):
        clock = iter([0.0, 1.0, 11.0, 12.0])
        slow = Resp(200, content=b"x" * (cc.CHUNK * 3))
        with mock.patch.object(cc.requests, "get", return_value=slow),                 mock.patch.object(cc.time, "monotonic", side_effect=lambda: next(clock)):
            with self.assertRaises(TimeoutError):
                cc._get(cc.COLLINFO, 10.0, cc.MAX_INDEX)
        self.assertTrue(slow.closed)


if __name__ == "__main__":
    unittest.main()
