"""Fetch one product page for the API: http(s) only, public IPs only (SSRF guard), robots.txt, timeout, size cap."""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests

from fetch import USER_AGENT, robots_allows

TIMEOUT = 10  # seconds per request
MAX_BYTES = 3_000_000
MAX_REDIRECTS = 3


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


def get(url):
    """GET with manual redirects (each hop re-checked). Returns (final_url, status, text)."""
    for _ in range(MAX_REDIRECTS + 1):
        check_url(url)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True, allow_redirects=False)
        except requests.RequestException as e:
            raise FetchError(502, f"fetch failed: {type(e).__name__}")
        with r:
            if r.is_redirect:
                url = urljoin(url, r.headers["location"])
                continue
            body = b""
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > MAX_BYTES:
                    raise FetchError(413, "page larger than size limit")
            return url, r.status_code, body.decode(r.encoding or "utf-8", errors="replace")
    raise FetchError(502, "too many redirects")


def fetch_page(url):
    """robots.txt check, then the page. Returns (final_url, html)."""
    p = check_url(url)
    _, status, robots = get(f"{p.scheme}://{p.netloc}/robots.txt")
    if status == 200 and not robots_allows(robots, p.path + (f"?{p.query}" if p.query else "")):
        raise FetchError(403, "robots.txt disallows this URL")
    final, status, html = get(url)
    if status != 200:
        raise FetchError(502, f"upstream HTTP {status}")
    return final, html
