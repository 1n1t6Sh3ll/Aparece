"""Archived copy of a product page from the public Common Crawl archive, for stores whose robots.txt or bot checks
stop a live fetch. We never fetch the store itself here: only index.commoncrawl.org (CDX index) and
data.commoncrawl.org (WARC files), both fixed public hosts, with redirects off and an honest User-Agent.

fetch_archived(url, timeout_total=10) -> {"html", "capture_date", "crawl_id", "warc_url"} or None.
None means no usable copy (no capture, network error, deadline passed, not HTML)."""
import json
import re
import threading
import time
import zlib
from urllib.parse import urlsplit, urlunsplit

import requests

COLLINFO = "https://index.commoncrawl.org/collinfo.json"
DATA = "https://data.commoncrawl.org/"
USER_AGENT = "ProductLens/1.0 (archived-page lookup; +https://github.com/1n1t6Sh3ll/powerlens)"
MAX_CRAWLS = 6
MAX_RECORD = 5_000_000  # compressed WARC record bytes (Range length cap)
MAX_INDEX = 2_000_000  # collinfo.json / CDX answer bytes
MAX_INFLATED = 5_000_000  # decompressed record / page bytes; larger is dropped (gzip-bomb guard)
CHUNK = 65536
COLLINFO_TTL = 6 * 3600
AMAZON = re.compile(r"(?:^|\.)amazon\.[a-z.]+$", re.I)
ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/asin)/([A-Z0-9]{10})(?:[/?#]|$)", re.I)
_crawls = {"at": 0.0, "ids": []}
_lock = threading.Lock()


class TooLarge(ValueError):
    pass


def left(deadline):
    t = deadline - time.monotonic()
    if t <= 0:
        raise TimeoutError("deadline")
    return t


def _get(url, deadline, cap, headers=None, params=None):
    """Streamed GET -> (status, body bytes). Raises TooLarge past cap bytes and TimeoutError past the deadline,
    which is checked between chunks as well as per socket read."""
    r = requests.get(url, headers={"User-Agent": USER_AGENT, **(headers or {})}, params=params,
                     timeout=left(deadline), allow_redirects=False, stream=True)
    try:
        body = bytearray()
        for chunk in r.iter_content(CHUNK):
            body += chunk
            if len(body) > cap:
                raise TooLarge(url)
            left(deadline)
        return r.status_code, bytes(body)
    finally:
        r.close()


def inflate(data, wbits, cap=MAX_INFLATED):
    """Streaming zlib/gzip decompress that stops at cap bytes: raises TooLarge instead of inflating a bomb."""
    d = zlib.decompressobj(wbits)
    out = d.decompress(data, cap + 1)
    if len(out) > cap or d.unconsumed_tail:
        raise TooLarge("inflated")
    return out


def crawls(deadline):
    """Crawl ids (e.g. CC-MAIN-2025-30), newest first, cached in memory."""
    with _lock:
        if _crawls["ids"] and time.monotonic() - _crawls["at"] < COLLINFO_TTL:
            return _crawls["ids"]
    status, body = _get(COLLINFO, deadline, MAX_INDEX)
    if status != 200:
        raise requests.HTTPError(f"collinfo {status}")
    ids = [c["id"] for c in json.loads(body) if c.get("id")]
    with _lock:
        _crawls.update(at=time.monotonic(), ids=ids)
    return ids


def clear_cache():
    with _lock:
        _crawls.update(at=0.0, ids=[])


def variants(url):
    """The URL as given, then without query/fragment, with and without www., and for Amazon /dp/<ASIN> forms."""
    p = urlsplit(url.strip())
    host = (p.hostname or "").lower()
    bare = host[4:] if host.startswith("www.") else host
    path = p.path or "/"
    out = [url.strip()]
    for h in (host, bare, "www." + bare):
        out.append(urlunsplit(("https", h, path, "", "")))
    if AMAZON.search(host):
        m = ASIN.search(path)
        if m:
            asin = m.group(1).upper()
            out.append(urlunsplit(("https", host, path[:m.end(1)], "", "")))  # /<title-slug>/dp/<ASIN>
            for h in ("www." + bare, bare):
                out += [f"https://{h}/dp/{asin}", f"https://{h}/dp/{asin}/", f"https://{h}/gp/product/{asin}"]
    # The CDX index keys captures by SURT, which ignores the scheme and a leading "www.", so variants that differ only
    # there are the same lookup: keep one of each to spend the time budget on distinct queries.
    seen, uniq = set(), []
    for u in out:
        q = urlsplit(u)
        key = (re.sub(r"^www\d*\.", "", (q.hostname or "").lower()), q.path or "/", q.query)
        if key not in seen:
            seen.add(key)
            uniq.append(u)
    return uniq


def page_key(u):
    """(host without www., path without trailing slash, query) or None: scheme and host case are ignored."""
    q = urlsplit(str(u or ""))
    return ((q.hostname or "").lower().removeprefix("www."), q.path.rstrip("/"), q.query) if q.hostname else None


def same_page(a, b):
    return page_key(a) is not None and page_key(a) == page_key(b)


def lookup(crawl_id, url, deadline):
    """Newest HTML 200 capture of url in one crawl's CDX index, or None."""
    status, body = _get(f"https://index.commoncrawl.org/{crawl_id}-index", deadline, MAX_INDEX,
                        params={"url": url, "output": "json", "filter": "status:200"})
    if status == 404:  # "No Captures found"
        return None
    if status != 200:
        raise requests.HTTPError(f"index {status}")
    rows = []
    for line in body.decode("utf-8", "replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or same_page(row.get("url"), url) is False:  # never another page's capture
            continue
        if "html" in row.get("mime", "") + row.get("mime-detected", "") and row.get("filename"):
            rows.append(row)
    return max(rows, key=lambda x: x.get("timestamp", "")) if rows else None


def split_block(data):
    """(header dict with lower-case names, rest) for a CRLF header block."""
    head, _, rest = data.partition(b"\r\n\r\n")
    headers = {}
    for line in head.split(b"\r\n")[1:]:
        k, sep, v = line.partition(b":")
        if sep:
            headers[k.strip().decode("latin-1").lower()] = v.strip().decode("latin-1")
    return head.split(b"\r\n", 1)[0], headers, rest


def dechunk(body):
    out, i = [], 0
    while True:
        j = body.find(b"\r\n", i)
        if j < 0:
            break
        size = int(body[i:j].split(b";")[0] or b"0", 16)
        if size == 0:
            break
        out.append(body[j + 2:j + 2 + size])
        i = j + 2 + size + 2
    return b"".join(out)


def parse_record(raw):
    """gzip WARC response record -> decoded HTML text, or None if it is not an HTTP 200 HTML response."""
    data = inflate(raw, 31)  # one gzip member per record
    first, warc, rest = split_block(data)
    if not first.startswith(b"WARC/") or warc.get("warc-type") != "response":
        return None
    if warc.get("content-length", "").isdigit():
        rest = rest[:int(warc["content-length"])]  # drop the record's trailing CRLFs
    status_line, http, body = split_block(rest)
    parts = status_line.split()
    if len(parts) < 2 or parts[1] != b"200":
        return None
    ctype = http.get("content-type", "")
    if ctype and "html" not in ctype.lower():
        return None
    if "chunked" in http.get("transfer-encoding", "").lower():
        body = dechunk(body)
    enc = http.get("content-encoding", "").lower()
    if enc in ("gzip", "x-gzip", "deflate"):
        body = inflate(body, 47 if "gzip" in enc else 15)  # 47 = auto gzip/zlib header
    elif enc and enc != "identity":
        return None  # e.g. br: not decoded here
    m = re.search(r"charset=([\w-]+)", ctype, re.I) or re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", body[:4096], re.I)
    charset = m.group(1) if m else "utf-8"
    charset = charset.decode("ascii", "ignore") if isinstance(charset, bytes) else charset
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_record(row, deadline):
    offset, length = int(row["offset"]), int(row["length"])
    if length <= 0 or length > MAX_RECORD:
        return None
    status, raw = _get(DATA + row["filename"], deadline, length,
                       headers={"Range": f"bytes={offset}-{offset + length - 1}"})
    return parse_record(raw) if status == 206 else None


def fetch_archived(url, timeout_total=10):
    """Newest archived HTML copy of url from the latest MAX_CRAWLS Common Crawl crawls, or None."""
    if urlsplit(url or "").scheme not in ("http", "https") or not urlsplit(url).hostname:
        return None
    if re.search(r"[*\s]", url):  # CDX treats * as a prefix/wildcard match: could return another product's capture
        return None
    deadline = time.monotonic() + timeout_total
    try:
        for crawl_id in crawls(deadline)[:MAX_CRAWLS]:
            for u in variants(url):
                try:
                    try:
                        row = lookup(crawl_id, u, deadline)
                    except requests.HTTPError:  # the index often answers 502/504 once: try the same lookup again
                        row = lookup(crawl_id, u, deadline)
                except (requests.HTTPError, TooLarge):  # index still overloaded (5xx) or oversized answer: next crawl
                    break
                if not row:
                    continue
                try:
                    html = fetch_record(row, deadline)
                except TooLarge:  # oversized or bomb record: try the next crawl's copy
                    break
                if html:
                    ts = row["timestamp"]
                    return {"html": html, "capture_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                            "crawl_id": crawl_id, "warc_url": DATA + row["filename"]}
    except (requests.RequestException, TimeoutError, OSError, ValueError, KeyError, EOFError, zlib.error):
        return None
    return None
