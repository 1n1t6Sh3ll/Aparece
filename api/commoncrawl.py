"""Archived copy of a product page from the public Common Crawl archive, for stores whose robots.txt or bot checks
stop a live fetch. We never fetch the store itself here: only index.commoncrawl.org (CDX index) and
data.commoncrawl.org (WARC files), both fixed public hosts, with redirects off and an honest User-Agent.

fetch_archived(url, timeout_total=10) -> {"html", "capture_date", "crawl_id", "warc_url"} or None.
None means no usable copy (no capture, network error, deadline passed, not HTML)."""
import gzip
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
MAX_RECORD = 5_000_000  # compressed WARC record bytes
COLLINFO_TTL = 6 * 3600
AMAZON = re.compile(r"(?:^|\.)amazon\.[a-z.]+$", re.I)
ASIN = re.compile(r"/(?:dp|gp/product|gp/aw/d|exec/obidos/asin)/([A-Z0-9]{10})(?:[/?#]|$)", re.I)
_crawls = {"at": 0.0, "ids": []}
_lock = threading.Lock()


def _get(url, deadline, **kw):
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError("deadline")
    headers = {"User-Agent": USER_AGENT, **kw.pop("headers", {})}
    return requests.get(url, headers=headers, timeout=left, allow_redirects=False, **kw)


def crawls(deadline):
    """Crawl ids (e.g. CC-MAIN-2025-30), newest first, cached in memory."""
    with _lock:
        if _crawls["ids"] and time.monotonic() - _crawls["at"] < COLLINFO_TTL:
            return _crawls["ids"]
    r = _get(COLLINFO, deadline)
    r.raise_for_status()
    ids = [c["id"] for c in r.json() if c.get("id")]
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


def lookup(crawl_id, url, deadline):
    """Newest HTML 200 capture of url in one crawl's CDX index, or None."""
    r = _get(f"https://index.commoncrawl.org/{crawl_id}-index", deadline,
             params={"url": url, "output": "json", "filter": "status:200"})
    if r.status_code == 404:  # "No Captures found"
        return None
    r.raise_for_status()
    rows = []
    for line in r.text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
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
    data = gzip.decompress(raw)
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
        body = zlib.decompress(body, 47 if "gzip" in enc else 15)  # 47 = auto gzip/zlib header
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
    if length > MAX_RECORD:
        return None
    r = _get(DATA + row["filename"], deadline, headers={"Range": f"bytes={offset}-{offset + length - 1}"})
    if r.status_code != 206:
        return None
    return parse_record(r.content)


def fetch_archived(url, timeout_total=10):
    """Newest archived HTML copy of url from the latest MAX_CRAWLS Common Crawl crawls, or None."""
    if urlsplit(url or "").scheme not in ("http", "https") or not urlsplit(url).hostname:
        return None
    deadline = time.monotonic() + timeout_total
    try:
        for crawl_id in crawls(deadline)[:MAX_CRAWLS]:
            for u in variants(url):
                try:
                    row = lookup(crawl_id, u, deadline)
                except requests.HTTPError:  # index overloaded (503) for this crawl: try the next one
                    break
                if not row:
                    continue
                html = fetch_record(row, deadline)
                if html:
                    ts = row["timestamp"]
                    return {"html": html, "capture_date": f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}",
                            "crawl_id": crawl_id, "warc_url": DATA + row["filename"]}
    except (requests.RequestException, TimeoutError, OSError, ValueError, KeyError, EOFError, zlib.error):
        return None
    return None
