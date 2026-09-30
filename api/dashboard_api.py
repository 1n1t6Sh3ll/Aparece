"""Read-only dashboard routes (TEAM-26) over a local normalized-records JSONL.

PRODUCTLENS_DATA: dataset path (default dataset/output/final/train.jsonl).
PRODUCTLENS_EVAL: eval JSON from train/eval.py (default train/runs/eval.json).
PRODUCTLENS_SIGNALS: signals/build.py output (default dataset/output/signals/signals.jsonl).
PRODUCTLENS_VISIBILITY: benchmark report.json (default benchmark/reports/report.json).
A missing file gives empty results, never a 500. Peer/gap logic lives in analysis/.
"""
import html
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dataset" / "collect"))

from analysis.gaps import analyze, completeness  # noqa: E402
from analysis.peers import find_peers, get, load_records, price  # noqa: E402
from normalize import lang_code  # noqa: E402
from tools.linkcheck import status as link  # noqa: E402

router = APIRouter(prefix="/v1")
_cache = {}


def _path(env, default):
    """Env value is used as given (relative to the working directory); the default is repo-relative."""
    return Path(os.environ[env]) if os.environ.get(env) else ROOT / default


def _cached(env, default, loader, empty):
    """Load a file once per (path, mtime); a missing or unreadable file gives `empty`."""
    p = _path(env, default)
    try:
        key = (str(p), p.stat().st_mtime)
        if _cache.get(env, (None,))[0] != key:
            _cache[env] = (key, loader(p))
        return _cache[env][1]
    except (OSError, ValueError):
        return empty


SECTIONS = ("source", "identity", "content", "materials", "fit_and_style", "variants", "commerce",
            "structured_data")


def adapt(row):
    """Normalized record (*_clean.jsonl) as-is, or a ground-truth row (dataset/output/final) mapped to the
    same shape: `gold` dotted keys become sections. Non-dict sections become {} so analysis/ never sees them."""
    if not isinstance(row, dict):
        return None
    if isinstance(row.get("gold"), dict):
        raw = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        prov = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
        txt = lambda v: html.unescape(v) if isinstance(v, str) else None  # noqa: E731
        name = txt(raw.get("raw_title")) or txt(raw.get("raw_product_name"))
        rec = {"product_id": row.get("product_id"), "dataset_source": row.get("source"),
               "source": {"merchant_domain": row.get("domain") or raw.get("merchant_domain"),
                          "language": lang_code(row.get("language")), "url": prov.get("url") or raw.get("source_url"),
                          "scraped_at": prov.get("scraped_at")},
               "identity": {"brand": txt(raw.get("brand")), "product_name": name},
               "content": {"title": name, "full_description": txt(raw.get("raw_full_description")),
                           "bullet_points": [txt(b) for b in raw.get("raw_bullet_points") or [] if isinstance(b, str)]},
               "commerce": {"sku": raw.get("sku"), "gtin": raw.get("gtin"), "mpn": raw.get("mpn")},
               "evidence": row.get("evidence") if isinstance(row.get("evidence"), list) else [],
               "quality_status": prov.get("quality_status")}
        for key, v in row["gold"].items():
            sec, _, field = key.partition(".")
            if field and sec in SECTIONS:
                rec.setdefault(sec, {})[field] = v
        return rec
    rec = dict(row)
    for sec in SECTIONS:
        if not isinstance(rec.get(sec), dict):
            rec[sec] = {}
    if rec["source"].get("language"):  # 'en-US' / 'EN' -> 'en', so peers match on language (#71)
        rec["source"] = {**rec["source"], "language": lang_code(rec["source"]["language"])}
    return rec


def _load_adapted(p):
    """Stream and adapt line by line (ground-truth files are large); undecodable lines are skipped."""
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            try:
                rec = adapt(json.loads(line)) if line.strip() else None
            except ValueError:
                continue
            if rec and rec.get("product_id"):
                out.append(rec)
    return out


def records():
    return _cached("PRODUCTLENS_DATA", "dataset/output/final/train.jsonl", _load_adapted, [])


def signals():
    return _cached("PRODUCTLENS_SIGNALS", "dataset/output/signals/signals.jsonl",
                   lambda p: {s["product_id"]: s for s in load_records(p) if s.get("product_id")}, {})


def visibility():
    return _cached("PRODUCTLENS_VISIBILITY", "benchmark/reports/report.json",
                   lambda p: json.loads(p.read_text(encoding="utf-8")), {})


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


@router.get("/products/{pid}/signals")
def product_signals(pid: str):
    find(pid)
    sig = signals().get(pid)
    if sig is None:
        return {"available": False, "signal": None}
    # currency_source "assumed:..." means the currency was not on the page; the UI must label it.
    return {"available": True, "signal": sig,
            "currency_assumed": str(sig.get("currency_source") or "").startswith("assumed")}


@router.get("/products/{pid}/competitors")
def competitors(pid: str, k: int = Query(10, ge=1, le=50)):
    """Comparable products (analysis.peers) with completeness and price relative to the target."""
    rec, sig = find(pid), signals()

    def price_cur(r):
        """Record price; else the signals price when its currency was observed, not assumed."""
        if price(r):
            return price(r), get(r, "commerce", "currency")
        s = sig.get(r.get("product_id")) or {}
        ok = s.get("currency_source") == "record" and isinstance(s.get("price"), (int, float)) and s["price"] > 0
        return (s["price"], s.get("currency")) if ok else (None, None)

    tp, cur = price_cur(rec)
    rows = []
    for sc, p in find_peers(rec, records(), k):
        pp, pcur = price_cur(p)
        same = bool(tp and pp and cur and pcur == cur)
        rows.append({**summary(p), **link.flag(p), "price": pp, "currency": pcur, "match_score": sc,
                     "completeness_pct": completeness(p),
                     "price_diff_pct": round(100 * (pp - tp) / tp, 1) if same else None,
                     "peer_percentile": ((sig.get(p["product_id"]) or {}).get("peer") or {}).get("percentile")})
    return {"target": {**summary(rec), "price": tp, "currency": cur, "completeness_pct": completeness(rec),
                       "peer_percentile": ((sig.get(pid) or {}).get("peer") or {}).get("percentile")},
            "peers": rows}


@router.get("/visibility")
def visibility_report():
    rep = visibility()
    ok = isinstance(rep, dict) and isinstance(rep.get("models"), dict) and bool(rep["models"])
    return {"available": ok, "report": rep if ok else {}}


@router.get("/languages")
def languages():
    """Attribute coverage per page language, next to visibility per language from the benchmark report."""
    by = {}
    for r in records():
        by.setdefault(get(r, "source", "language") or "unknown", []).append(completeness(r))
    rep = visibility()
    vis = {}
    for model, m in (rep.get("models") or {}).items() if isinstance(rep, dict) else []:
        for lang, s in (m.get("languages") or {}).items():
            vis.setdefault(lang, {})[model] = {"responses": s.get("responses"),
                                               "any_catalog_mention_rate": s.get("any_catalog_mention_rate"),
                                               "stability": s.get("stability")}
    out = {}
    for lang in sorted(set(by) | set(vis)):
        c = by.get(lang, [])
        out[lang] = {"products": len(c),
                     "completeness_median": round(statistics.median(c), 1) if c else None,
                     "completeness_mean": round(statistics.mean(c), 1) if c else None,
                     "visibility": vis.get(lang, {})}
    return {"languages": out, "visibility_available": bool(vis)}
