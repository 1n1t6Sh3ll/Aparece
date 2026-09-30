"""Snapshot content from a normalized record, and change events between two snapshots (VISION §24-26)."""
import hashlib

from bs4 import BeautifulSoup

from analysis.gaps import ATTRIBUTES, SCHEMA_FLAGS, attributes_present
from analysis.peers import get


def languages(html):
    """hreflang alternates declared on the page, e.g. ["de", "en", "x-default"]."""
    soup = BeautifulSoup(html, "html.parser")
    return sorted({ln["hreflang"].strip().lower() for ln in soup.find_all("link", hreflang=True) if ln["hreflang"].strip()})


def content(norm, html, visibility=None):
    present = attributes_present(norm)
    desc = get(norm, "content", "full_description") or ""
    return {
        "title": get(norm, "identity", "product_name"),
        "language": get(norm, "source", "language"),
        "price": get(norm, "commerce", "price"),
        "currency": get(norm, "commerce", "currency"),
        "description_sha256": hashlib.sha256(desc.encode()).hexdigest() if desc else None,
        "description_chars": len(desc),
        "attributes": {f"{s}.{k}": get(norm, s, k) for s, k in ATTRIBUTES if present[f"{s}.{k}"]},
        "schema": {f: bool(get(norm, "structured_data", f)) for f in SCHEMA_FLAGS},
        "languages": languages(html),
        "visibility": visibility,
    }


def diff(old, new):
    """old/new: snapshot content dicts. Returns a list of {type, field, before, after}."""
    if old is None:
        return []
    ev = []

    def add(type_, field, before, after):
        ev.append({"type": type_, "field": field, "before": before, "after": after})

    if old["description_sha256"] != new["description_sha256"]:
        add("DESCRIPTION_CHANGED", "content.full_description", old["description_chars"], new["description_chars"])
    if (old["price"], old["currency"]) != (new["price"], new["currency"]):
        add("PRICE_CHANGED", "commerce.price", [old["price"], old["currency"]], [new["price"], new["currency"]])
    oa, na = old["attributes"], new["attributes"]
    for f in sorted(na.keys() - oa.keys()):
        add("ATTRIBUTE_ADDED", f, None, na[f])
    for f in sorted(oa.keys() - na.keys()):
        add("ATTRIBUTE_REMOVED", f, oa[f], None)
    if old["schema"] != new["schema"]:
        add("SCHEMA_CHANGED", "structured_data", old["schema"], new["schema"])
    for lang in sorted(set(new["languages"]) - set(old["languages"])):
        add("LANGUAGE_PAGE_ADDED", "hreflang", None, lang)
    if old.get("visibility") != new.get("visibility") and new.get("visibility") is not None:
        add("VISIBILITY_CHANGED", "visibility", old.get("visibility"), new["visibility"])
    return ev
