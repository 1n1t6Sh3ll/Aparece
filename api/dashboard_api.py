"""Read-only dashboard routes (TEAM-26) over a local normalized-records JSONL.

PRODUCTLENS_DATA: dataset path (default dataset/output/final/train.jsonl).
PRODUCTLENS_EVAL: eval JSON from train/eval.py (default train/runs/eval.json).
A missing file gives empty results, never a 500. Peer/gap logic lives in analysis/.
"""
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.gaps import analyze  # noqa: E402
from analysis.peers import find_peers, get, load_records, price  # noqa: E402

router = APIRouter(prefix="/v1")
_cache = {}


def _path(env, default):
    """Env value is used as given (relative to the working directory); the default is repo-relative."""
    return Path(os.environ[env]) if os.environ.get(env) else ROOT / default


def records():
    p = _path("PRODUCTLENS_DATA", "dataset/output/final/train.jsonl")
    try:
        key = (str(p), p.stat().st_mtime)
    except OSError:
        return []
    if key not in _cache:
        _cache.clear()
        _cache[key] = load_records(p)
    return _cache[key]


def summary(r):
    return {"product_id": r.get("product_id"),
            "title": get(r, "content", "title") or get(r, "identity", "product_name"),
            "brand": get(r, "identity", "brand"), "product_type": get(r, "identity", "product_type"),
            "language": get(r, "source", "language"), "merchant": get(r, "source", "merchant_domain"),
            "price": get(r, "commerce", "price"), "currency": get(r, "commerce", "currency"),
            "quality_status": r.get("quality_status")}


def find(pid):
    rec = next((r for r in records() if r.get("product_id") == pid), None)
    if rec is None:
        raise HTTPException(404, "product not found")
    return rec


@router.get("/products")
def products(q: str = Query("", max_length=200), limit: int = Query(20, ge=1, le=100)):
    terms = q.lower().split()
    out = []
    for r in records():
        s = summary(r)
        hay = " ".join(str(v) for v in s.values() if v).lower()
        if all(t in hay for t in terms):
            out.append(s)
            if len(out) >= limit:
                break
    return {"results": out}


@router.get("/products/{pid}")
def product(pid: str):
    rec = find(pid)
    keep = ("source", "identity", "materials", "fit_and_style", "variants", "commerce", "evidence",
            "conflicts", "quality_status", "quality_flags")
    return {"summary": summary(rec), **{k: rec.get(k) for k in keep}}


@router.get("/products/{pid}/gaps")
def gaps(pid: str, k: int = Query(10, ge=1, le=50)):
    rec = find(pid)
    peers = find_peers(rec, records(), k)
    out = analyze(rec, peers)
    prices = [price(p) for _, p in peers if price(p) and get(p, "commerce", "currency") == get(rec, "commerce", "currency")]
    out["price"] = {"target": price(rec), "currency": get(rec, "commerce", "currency"), "peer_count": len(prices),
                    "peer_min": min(prices, default=None), "peer_max": max(prices, default=None),
                    "peer_median": statistics.median(prices) if prices else None}
    return out


@router.get("/stats")
def stats():
    recs = records()

    def count(fn):
        return dict(Counter(fn(r) or "unknown" for r in recs).most_common())

    return {"total": len(recs),
            "by_source": count(lambda r: get(r, "source", "merchant_domain")),
            "by_language": count(lambda r: get(r, "source", "language")),
            "by_product_type": count(lambda r: get(r, "identity", "product_type")),
            "by_material": count(lambda r: get(r, "materials", "primary_material")),
            "by_quality": count(lambda r: r.get("quality_status"))}


@router.get("/eval")
def evaluation():
    p = _path("PRODUCTLENS_EVAL", "train/runs/eval.json")
    try:
        return {"available": True, "results": json.loads(p.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"available": False, "results": {}}
