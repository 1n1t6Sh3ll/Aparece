"""Deterministic matching of AI-response mentions to catalog products.

A product matches when its exact URL appears, an alias appears, or its
normalized brand AND name appear on the same line. Sites are keyed by exact
host (minus "www."), so northwindtees.com and northwindtees.es are distinct.
"""
import json
import re
import unicodedata
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s)\]>\"'<]+")
HOST_RE = re.compile(r"(?<![\w.-])((?:[a-z0-9-]+\.)+[a-z]{2,})(?![\w-])", re.I)
LIST_ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(.+)")


def norm(text):
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", text).split()) + " "


def host(url):
    h = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def url_key(url):
    p = urlparse(url)
    return host(url) + p.path.rstrip("/").lower()


def load_catalog(path):
    """Load normalized records (JSONL or JSON list) into flat product dicts."""
    with open(path, encoding="utf-8") as f:
        text = f.read().strip()
    rows = json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    products = []
    for r in rows:
        src, ident = r.get("source", {}), r.get("identity", {})
        url = src.get("canonical_url") or src.get("url") or ""
        products.append({
            "product_id": r["product_id"],
            "brand": ident.get("brand") or "",
            "name": ident.get("product_name") or "",
            "url": url,
            "site": host(src.get("merchant_domain") or url),
            "aliases": r.get("aliases") or [],
        })
    return products


def match_response(text, products):
    """Return ordered product mentions, citations, and unmatched mentions."""
    by_url = {url_key(p["url"]): p for p in products if p["url"]}
    sites = {p["site"] for p in products}
    hits = {}  # product_id -> first character offset
    cited_products, cited_sites, unmatched = set(), set(), []

    def hit(pid, pos):
        if pid not in hits or pos < hits[pid]:
            hits[pid] = pos

    for m in URL_RE.finditer(text or ""):
        url = m.group(0).rstrip(".,;:!?")
        h = host(url)
        p = by_url.get(url_key(url))
        if p:
            hit(p["product_id"], m.start())
            cited_products.add(p["product_id"])
        if h in sites:
            cited_sites.add(h)
        else:
            unmatched.append({"kind": "url", "text": url})

    offset = 0
    for line in (text or "").splitlines(keepends=True):
        nl = norm(line)
        line_hosts = {host(h) for h in HOST_RE.findall(line)}
        found = [p for p in products
                 if any(norm(a) in nl for a in p["aliases"] if a.strip())
                 or (p["name"] and norm(p["name"]) in nl and norm(p["brand"]) in nl)]
        # Same brand+name on several country sites: disambiguate by domain in line.
        groups = {}
        for p in found:
            groups.setdefault((norm(p["brand"]), norm(p["name"])), []).append(p)
        for group in groups.values():
            if len(group) > 1:
                group = [p for p in group if p["site"] in line_hosts] or group
            if len(group) == 1:
                hit(group[0]["product_id"], offset)
            else:
                unmatched.append({"kind": "ambiguous", "text": line.strip()[:120]})
        item = LIST_ITEM_RE.match(line)
        if item and not found and not URL_RE.search(line):
            unmatched.append({"kind": "item", "text": item.group(1).strip()[:120]})
        offset += len(line)

    ordered = sorted(hits, key=lambda pid: hits[pid])
    return {
        "mentions": ordered,  # position = index + 1
        "cited_products": sorted(cited_products),
        "cited_sites": sorted(cited_sites),
        "unmatched": unmatched,
    }
