"""Read link-check results (dataset/output/link_status.jsonl, or PRODUCTLENS_LINK_STATUS) for peer filtering.

gone / redirected_away: the product page no longer exists, so it is not a peer, competitor or catalog product.
blocked / error: the page could not be verified; it stays, flagged "link unverified".
A missing file (or a URL never checked) changes nothing: behaviour is as before link checking existed.
"""
import json
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "dataset" / "output" / "link_status.jsonl"
STATUSES = ("live", "gone", "redirected_away", "blocked", "error")
EXCLUDE = {"gone", "redirected_away"}
UNVERIFIED = {"blocked", "error"}
_cache = {}


def url_key(url):
    """host (no www.) + path (no trailing slash) + query; scheme and fragment ignored."""
    return _key(url.strip()) if isinstance(url, str) else ""


@lru_cache(maxsize=65536)
def _key(url):
    p = urlsplit(url)
    h = (p.hostname or "").lower()
    h = h[4:] if h.startswith("www.") else h
    return h + p.path.rstrip("/") + (f"?{p.query}" if p.query else "") if h else ""


def path():
    return Path(os.environ["PRODUCTLENS_LINK_STATUS"]) if os.environ.get("PRODUCTLENS_LINK_STATUS") else DEFAULT


def load(p=None):
    """{url_key: row}; a later line for the same URL wins. Cached per (path, mtime); missing file -> {}."""
    p = Path(p) if p else path()
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if _cache.get("key") != key:
        rows = {}
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line) if line.strip() else None
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("status") in STATUSES and url_key(r.get("url")):
                    rows[url_key(r["url"])] = r
        _cache.update(key=key, rows=rows)
    return _cache["rows"]


def record_url(rec):
    rec = rec if isinstance(rec, dict) else {}
    src = rec.get("source") if isinstance(rec.get("source"), dict) else {}
    prov = rec.get("provenance") if isinstance(rec.get("provenance"), dict) else {}
    return src.get("url") or src.get("canonical_url") or prov.get("url") or rec.get("url")


def status(url):
    row = load().get(url_key(url)) if url else None
    return row["status"] if row else None


def is_dead(rec):
    """True when the record's product URL was checked and is gone or redirected away."""
    return status(record_url(rec)) in EXCLUDE


def keep(records):
    """Records whose link is not known to be dead (all of them when no link status exists)."""
    rows = load()
    if not rows:
        return list(records)
    return [r for r in records if (rows.get(url_key(record_url(r))) or {}).get("status") not in EXCLUDE]


def flag(rec_or_url):
    """Fields for UI/API rows: link_status (None if never checked) and link_unverified (blocked/error)."""
    s = status(rec_or_url if isinstance(rec_or_url, str) else record_url(rec_or_url))
    return {"link_status": s, "link_unverified": s in UNVERIFIED}
