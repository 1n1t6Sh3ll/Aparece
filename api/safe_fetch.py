"""Fetch one product page for the API: http(s) only, public IPs only (SSRF guard), robots.txt, timeout, size cap.
Rate limits: one retry honouring Retry-After (<= 10 s) inside the total deadline; successful pages are cached for
10 minutes and robots.txt for 1 hour per host. If a Shopify product page stays rate-limited, the store's public
/products/<handle>.json (robots permitting) is read instead and wrapped as schema.org JSON-LD. The User-Agent is
never changed."""
import html as htmllib
import ipaddress
import json
import re
import socket
import threading
import time
from urllib.parse import urljoin, urlsplit

import requests

from fetch import USER_AGENT, robots_allows

TIMEOUT = 10  # total seconds for robots.txt + page + redirects
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3
MAX_RETRY_AFTER = 10  # seconds; a longer Retry-After is not waited for
PAGE_TTL, ROBOTS_TTL = 600, 3600
LIMITED = (429, 503)
SHOPIFY_PRODUCT = re.compile(r"^(/(?:[a-z]{2}(?:-[a-z]{2})?/)?)(?:collections/[^/]+/)?products/([^/?#.]+)/?$", re.I)
_cache, _lock = {}, threading.Lock()


def cached(key):
    with _lock:
        hit = _cache.get(key)
        return hit[1] if hit and hit[0] > time.monotonic() else None


def remember(key, value, ttl):
    with _lock:
        if len(_cache) > 1000:
            _cache.clear()
        _cache[key] = (time.monotonic() + ttl, value)
    return value


def clear_cache():
    with _lock:
        _cache.clear()


def retry_after(headers):
    """Seconds to wait before the one retry: Retry-After in seconds (<= MAX_RETRY_AFTER), 1 s if absent or a date,
    None (no retry) if the store asks for longer."""
    v = (headers.get("retry-after") or "").strip()
    if not v.isdigit():
        return 1.0
    return float(v) if int(v) <= MAX_RETRY_AFTER else None


class FetchError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def check_url(url):
    """Reject non-http(s) URLs and hosts that resolve to private, loopback, link-local or reserved IPs."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError(400, "only http(s) URLs are allowed")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise FetchError(400, "host does not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError(400, "URL resolves to a non-public address")
    return p


def remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise FetchError(504, "fetch deadline exceeded")
    return left


def get(url, deadline=None):
    """GET with manual redirects (each hop re-checked) under one total deadline. Returns (final_url, status, text).
    A 429/503 is retried once after Retry-After when that wait fits in the deadline."""
    deadline = deadline or time.monotonic() + TIMEOUT
    final, status, text, wait = get_once(url, deadline)
    if status in LIMITED and wait is not None and wait < remaining(deadline):
        time.sleep(wait)
        final, status, text, _ = get_once(url, deadline)
    return final, status, text


def get_once(url, deadline):
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=remaining(deadline), stream=True,
                             allow_redirects=False)
        except requests.RequestException as e:
            raise FetchError(502, f"fetch failed: {type(e).__name__}")
        with r:
            if r.is_redirect:
                if not r.headers.get("location"):
                    raise FetchError(400, "redirect without Location header")
                url = urljoin(url, r.headers["location"])
                continue
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                remaining(deadline)
                if len(body) > MAX_BYTES:
                    raise FetchError(413, "page larger than size limit")
            wait = retry_after(r.headers) if r.status_code in LIMITED else None
            return url, r.status_code, body.decode(r.encoding or "utf-8", errors="replace"), wait
    raise FetchError(502, "too many redirects")


def robots(p, deadline):
    """robots.txt text for the host ("" if none), cached 1 h. Raises 'upstream HTTP 429' if it stays rate-limited:
    permission is unknown, so nothing else is fetched."""
    key = ("robots", p.scheme, p.netloc)
    hit = cached(key)
    if hit is not None:
        return hit
    _, status, text = get(f"{p.scheme}://{p.netloc}/robots.txt", deadline)
    if status == 429:
        raise FetchError(502, "upstream HTTP 429 (robots.txt)")
    if status >= 500:  # RFC 9309: server error = disallow for now; not cached
        raise FetchError(502, f"upstream HTTP {status} (robots.txt): store temporarily unavailable")
    return remember(key, text if status == 200 else "", ROBOTS_TTL)


def allowed(p, robots_txt, path):
    if robots_txt and not robots_allows(robots_txt, path):
        raise FetchError(403, "robots.txt disallows this URL")


def shopify_page(p, robots_txt, deadline):
    """A Shopify product's public JSON as a minimal page with schema.org Product JSON-LD, or None."""
    m = SHOPIFY_PRODUCT.match(p.path)
    if not m:
        return None
    path = f"{m.group(1)}products/{m.group(2)}.json"
    if robots_txt and not robots_allows(robots_txt, path):
        return None
    _, status, text = get(f"{p.scheme}://{p.netloc}{path}", deadline)
    if status != 200:
        return None
    try:
        prod = json.loads(text)["product"]
    except (ValueError, KeyError, TypeError):
        return None
    return shopify_html(prod, (m.group(1).strip("/") or None))


ES_WORDS = {"de", "con", "para", "y", "el", "la", "los", "las", "en", "algodón", "camiseta", "manga", "hombre", "mujer"}
EN_WORDS = {"the", "with", "for", "and", "of", "in", "cotton", "shirt", "sleeve", "men", "women", "our"}


def guess_language(text):
    """'es' or 'en' from common words when the JSON has no locale, else None (no guess)."""
    words = re.findall(r"[a-záéíóúñ]+", (text or "").lower())
    es, en = sum(w in ES_WORDS for w in words), sum(w in EN_WORDS for w in words)
    return "es" if es >= 3 and es > 2 * en else "en" if en >= 3 and en > 2 * es else None


def shopify_html(prod, lang=None):
    """Shopify product JSON as a minimal page: schema.org Product (name, description, brand, category, images,
    one Offer per priced variant) and <html lang> from the URL locale or, failing that, the text."""
    variants = [v for v in prod.get("variants") or [] if isinstance(v, dict)]
    desc = htmllib.unescape(re.sub(r"<[^>]+>", " ", prod.get("body_html") or ""))
    node = {"@context": "https://schema.org", "@type": "Product", "name": prod.get("title") or "",
            "description": re.sub(r"\s+", " ", desc).strip(), "brand": {"@type": "Brand", "name": prod.get("vendor") or ""},
            "category": prod.get("product_type") or "",
            "image": [i.get("src") for i in prod.get("images") or [] if isinstance(i, dict) and i.get("src")][:5],
            "offers": [{"@type": "Offer", "price": v.get("price"), "priceCurrency": v.get("price_currency"),
                        "sku": v.get("sku"), "gtin": v.get("barcode"), "name": v.get("title")}
                       for v in variants if v.get("price")]}
    for o in node["offers"]:
        for k in [k for k, v in o.items() if not v]:
            del o[k]
    ld = json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
    t = htmllib.escape(node["name"])
    lang = lang or guess_language(f"{node['name']} {node['description']}")
    attr = f' lang="{htmllib.escape(lang)}"' if lang else ""
    return (f'<html{attr}><head><title>{t}</title><script type="application/ld+json">{ld}</script></head>'
            f'<body><h1>{t}</h1>{prod.get("body_html") or ""}</body></html>')


def fetch_page(url):
    """robots.txt check, then the page (cached 10 min). Returns (final_url, html)."""
    hit = cached(("page", url))
    if hit:
        return hit
    p = check_url(url)
    deadline = time.monotonic() + TIMEOUT
    robots_txt = robots(p, deadline)
    allowed(p, robots_txt, p.path + (f"?{p.query}" if p.query else ""))
    final, status, html = get(url, deadline)
    if status in LIMITED:
        page = shopify_page(p, robots_txt, deadline)
        if page:
            return remember(("page", url), (url, page), PAGE_TTL)
    if status != 200:
        raise FetchError(502, f"upstream HTTP {status}")
    return remember(("page", url), (final, html), PAGE_TTL)
