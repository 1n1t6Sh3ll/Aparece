"""Polite product-link checker (TEAM-50).

  python -m tools.linkcheck.check INPUT [INPUT ...] [--out dataset/output/link_status.jsonl] [--limit N]

INPUT is a JSONL of records (URL from source.url / source.canonical_url / provenance.url / url) or a text file with
one URL per line. Each URL is classified and appended to --out with checked_at; URLs already in --out are skipped,
so an interrupted run resumes (--recheck re-checks them; the newest line wins when read).

Statuses: live | gone (404/410, or a 200 "not found" page) | redirected_away (redirect ends on a home, search,
collection or category page, not a product) | blocked (401/403/429, bot challenge, robots.txt disallows us or is
unreachable) | error (DNS/TLS/connection/timeout, 5xx, other 4xx, too many redirects).

Politeness: honest ProductLens User-Agent (dataset/collect/fetch.py), robots.txt respected, at most one request per
second per host (robots, HEAD, GET and redirect hops all count), HEAD first with a GET fallback, 8 s timeout, a
bounded thread pool across hosts, no retries of 429. Every URL and redirect hop passes api/safe_fetch.check_url
(http(s) and public IPs only).
"""
import argparse
import json
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "api", ROOT / "dataset" / "collect"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import safe_fetch  # noqa: E402
from fetch import USER_AGENT, robots_allows  # noqa: E402
from tools.linkcheck.status import DEFAULT, record_url, url_key  # noqa: E402

TIMEOUT = 8
MIN_INTERVAL = 1.0
MAX_REDIRECTS = 5
BODY_BYTES = 65536
REDIRECTS = (301, 302, 303, 307, 308)
# Product-looking paths win over "away" markers (Shopify /collections/x/products/y is a product).
PRODUCT_PATH = re.compile(r"/(products?|dp|gp/product|p|item|items|artikel|producto|productos)/[^/]+"
                          r"|-p-?\d+|/\d{5,}|\.html?$", re.I)
AWAY_PATH = re.compile(r"^/?(?:[a-z]{2}(?:[-_][a-z]{2})?/?)?$"
                       r"|/(?:collections?|categor(?:y|ies)|search|catalog(?:ue)?|shop|store|all|c)(?:/|$)", re.I)
AWAY_QUERY = re.compile(r"(?:^|&)(?:q|s|query|search)=", re.I)
CHALLENGE = re.compile(r"<title[^>]*>\s*(?:just a moment|attention required|access denied|robot check|"
                       r"are you a (?:human|robot)|security check|pardon our interruption)"
                       r"|cf-chl-|/_incapsula_resource|px-captcha|captcha-delivery", re.I)
NOT_FOUND = re.compile(r"<title[^>]*>[^<]*(?:\b404\b|not found|no longer available|no encontrad|"
                       r"no existe|nicht gefunden|introuvable)[^<]*</title>", re.I)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def host_of(url):
    h = (urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def redirected_away(original, final):
    """True when a redirect ended on a non-product page (home, search, collection, category) or another site."""
    if url_key(final) == url_key(original):
        return False
    p = urlsplit(final)
    if PRODUCT_PATH.search(p.path) and host_of(final) == host_of(original):
        return False
    return bool(AWAY_PATH.search(p.path) or AWAY_QUERY.search(p.query) or host_of(final) != host_of(original))


def classify(original, final, code, headers, body=""):
    """(status, detail) from the final response of a HEAD or GET chain."""
    if code in (404, 410):
        return "gone", f"http_{code}"
    if code in (401, 403, 429):
        return "blocked", f"http_{code}"
    if (headers.get("cf-mitigated") or "").lower() == "challenge" or (body and CHALLENGE.search(body)):
        return "blocked", "challenge"
    if code in REDIRECTS:
        return "error", "too_many_redirects"
    if code >= 500:
        return "error", f"http_{code}"
    if not 200 <= code < 300:
        return "error", f"http_{code}"
    if redirected_away(original, final):
        return "redirected_away", "redirect_to_non_product"
    if body and NOT_FOUND.search(body):
        return "gone", "soft_404"
    return "live", f"http_{code}"


class Throttle:
    """At most one request per `interval` seconds per host, shared by all threads."""

    def __init__(self, interval=MIN_INTERVAL, sleep=time.sleep, clock=time.monotonic):
        self.interval, self.sleep, self.clock = interval, sleep, clock
        self.next, self.lock = {}, threading.Lock()

    def wait(self, host):
        with self.lock:
            t = self.clock()
            slot = max(t, self.next.get(host, 0.0))
            self.next[host] = slot + self.interval
        if slot > t:
            self.sleep(slot - t)


class Checker:
    def __init__(self, session=None, throttle=None, timeout=TIMEOUT, guard=safe_fetch.check_url):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
        self.throttle, self.timeout, self.guard = throttle or Throttle(), timeout, guard
        self.robots, self.lock = {}, threading.Lock()

    def _request(self, method, url):
        self.guard(url)  # SSRF: http(s) + public IPs, re-checked on every redirect hop
        self.throttle.wait(host_of(url))
        return self.session.request(method, url, allow_redirects=False, timeout=self.timeout,
                                    stream=method == "GET")

    def _follow(self, method, url):
        for _ in range(MAX_REDIRECTS + 1):
            r = self._request(method, url)
            loc = r.headers.get("location")
            if r.status_code not in REDIRECTS or not loc:
                return r, url
            r.close()
            url = urljoin(url, loc)
        return r, url

    def _robots(self, url):
        """robots.txt text ('' = allow all when it is missing), or None when unreachable (RFC 9309: disallow)."""
        p = urlsplit(url)
        key = f"{p.scheme}://{p.netloc}"
        with self.lock:
            if key in self.robots:
                return self.robots[key]
        try:
            r, _ = self._follow("GET", key + "/robots.txt")
            txt = r.text[:500_000] if 200 <= r.status_code < 300 else ("" if 400 <= r.status_code < 500 else None)
            r.close()
        except (requests.RequestException, safe_fetch.FetchError):
            txt = None
        with self.lock:
            self.robots[key] = txt
        return txt

    def check(self, url, product_id=None):
        row = {"url": url, "product_id": product_id, "status": None, "http_status": None, "final_url": None,
               "detail": None, "method": None}
        try:
            self.guard(url)  # a bad or unresolvable URL is an error, not a robots problem
            robots = self._robots(url)
            p = urlsplit(url)
            if robots is None:
                return self._done(row, "blocked", "robots_unreachable")
            if not robots_allows(robots, (p.path or "/") + (f"?{p.query}" if p.query else "")):
                return self._done(row, "blocked", "robots_disallowed")
            r, final = self._follow("HEAD", url)
            row["method"], body = "HEAD", ""
            if not 200 <= r.status_code < 300:  # many stores reject or mis-answer HEAD: confirm with GET
                r.close()
                r, final = self._follow("GET", url)
                row["method"] = "GET"
                if r.status_code < 300:
                    raw = next(r.iter_content(BODY_BYTES), b"")
                    body = raw.decode(r.encoding or "utf-8", errors="replace")
            r.close()
            row.update(http_status=r.status_code, final_url=final)
            return self._done(row, *classify(url, final, r.status_code, r.headers, body))
        except safe_fetch.FetchError as e:
            return self._done(row, "error", e.detail)
        except requests.exceptions.SSLError:
            return self._done(row, "error", "tls")
        except requests.exceptions.Timeout:
            return self._done(row, "error", "timeout")
        except requests.RequestException as e:
            return self._done(row, "error", f"connection: {type(e).__name__}")

    @staticmethod
    def _done(row, status, detail):
        row.update(status=status, detail=detail, checked_at=now())
        return row


def load_urls(paths):
    """[(url, product_id)] from JSONL records or plain URL lists, in order, de-duplicated by url_key."""
    out, seen = [], set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("{"):
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    url, pid = record_url(rec), rec.get("product_id")
                else:
                    url, pid = line, None
                k = url_key(url)
                if k and k not in seen:
                    seen.add(k)
                    out.append((url, pid))
    return out


def checked(path):
    try:
        with open(path, encoding="utf-8") as f:
            return {url_key(json.loads(l).get("url")) for l in f if l.strip().startswith("{")}
    except OSError:
        return set()


def run(items, out, workers=8, checker=None, recheck=False, log=print):
    """Check [(url, product_id)], appending rows to `out`. One thread per host at a time (hosts in parallel)."""
    done = set() if recheck else checked(out)
    todo = [(u, pid) for u, pid in items if url_key(u) not in done]
    by_host = defaultdict(list)
    for u, pid in todo:
        by_host[host_of(u)].append((u, pid))
    checker = checker or Checker()
    counts, lock = Counter(), threading.Lock()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    log(f"{len(items)} URLs, {len(items) - len(todo)} already checked, {len(todo)} to check on {len(by_host)} hosts")
    with open(out, "a", encoding="utf-8") as f:
        def host_job(rows):
            for u, pid in rows:
                row = checker.check(u, pid)
                with lock:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    counts[row["status"]] += 1
                    if sum(counts.values()) % 100 == 0:
                        log(f"  {sum(counts.values())}/{len(todo)} {dict(counts)}")
        # longest hosts first so a big host does not start last
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            list(pool.map(host_job, sorted(by_host.values(), key=len, reverse=True)))
    log(f"done: {dict(counts)}")
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools.linkcheck.check", description=__doc__.split("\n\n")[0])
    ap.add_argument("inputs", nargs="+", help="JSONL records or text files of URLs")
    ap.add_argument("--out", default=str(DEFAULT))
    ap.add_argument("--workers", type=int, default=8, help="hosts checked in parallel")
    ap.add_argument("--limit", type=int, help="check at most N URLs (after de-duplication)")
    ap.add_argument("--recheck", action="store_true", help="re-check URLs already in --out")
    a = ap.parse_args(argv)
    items = load_urls(a.inputs)[: a.limit]
    return run(items, a.out, a.workers, recheck=a.recheck)


if __name__ == "__main__":
    main()
