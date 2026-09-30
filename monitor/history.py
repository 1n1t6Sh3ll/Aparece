"""Per-snapshot metrics, snapshot diffs and trends for "My products".

Metrics re-run analysis/gaps on the normalized record stored with each snapshot (peers from the local dataset,
as in crawl.gaps_for) and are cached per snapshot in snapshot_metrics. Snapshots taken before records were stored
fall back to the snapshot content (completeness from its attribute list; no peer rank). No composite score.
"""
import difflib
import re

from analysis.gaps import ATTRIBUTES, analyze, completeness
from analysis.peers import get
from monitor import crawl, store

METRICS = ["completeness_rank", "attribute_completeness_pct", "peer_median_completeness_pct", "description_chars",
           "price", "currency", "structured_data_present", "language", "visibility"]


def compute(snap):
    data = snap["data"]
    c, rec = data["content"], data.get("record")
    m = {"completeness_rank": None, "peer_median_completeness_pct": None,
         "attribute_completeness_pct": round(100 * len(c["attributes"]) / len(ATTRIBUTES), 1),
         "description_chars": c["description_chars"], "price": c["price"], "currency": c["currency"],
         "structured_data_present": any(c["schema"].values()), "language": c["language"],
         "visibility": c.get("visibility")}
    if rec is not None:
        peers = crawl.peers_for(rec)
        gm = analyze(rec, peers)["metrics"]
        tc = gm["attribute_completeness_pct"]["target"]
        m["attribute_completeness_pct"] = tc
        m["peer_median_completeness_pct"] = gm["attribute_completeness_pct"]["peer_median"]
        m["completeness_rank"] = audit_rank(rec) or {"position": 1 + sum(completeness(p) > tc for p in peers),
                                                      "of": len(peers) + 1, "by": "attribute_completeness_pct"}
    return m


def audit_rank(rec):
    """The same listing-quality rank the audit shows (api/audit_api: same peers, widening and formula), so Monitor
    and the audit never disagree (#116). None when the audit module is not importable (monitor used outside the API)."""
    try:
        import audit_api
        import dashboard_api
    except ImportError:
        return None
    target = dashboard_api.adapt(rec)
    if not target:
        return None
    recs = audit_api.not_self(target)
    key, _ = audit_api.peer_key(target, recs)
    rk, _ = audit_api.rank(target, recs, match=key)
    return {"position": rk["position"], "position_from": rk.get("position_from"), "position_to": rk.get("position_to"),
            "of": rk["total"], "score": rk["score"], "by": "listing_quality"}


def metrics(snap):
    m = store.cached_metrics(snap["id"])
    if m is None:
        m = compute(snap)
        store.cache_metrics(snap["id"], m)
    return m


def snapshots(pid):
    return [{"id": s["id"], "crawled_at": s["taken_at"], "content_hash": s["content_hash"], "metrics": metrics(s)}
            for s in store.history(pid)["snapshots"]]


def trends(pid):
    return {"metrics": METRICS,
            "points": [{"at": s["crawled_at"], "snapshot_id": s["id"], **s["metrics"]} for s in snapshots(pid)]}


def _evidence(rec, field):
    return [{k: e.get(k) for k in ("value", "source_text", "source_location")}
            for e in (rec or {}).get("evidence") or [] if e.get("field") == field]


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def diff(a, b):
    """Field-level diff from snapshot a to snapshot b (full snapshot rows)."""
    ca, cb = a["data"]["content"], b["data"]["content"]
    ra, rb = a["data"].get("record"), b["data"].get("record")
    oa, na = ca["attributes"], cb["attributes"]
    attrs = {
        "added": [{"field": f, "new": na[f], "evidence": _evidence(rb, f)} for f in sorted(na.keys() - oa.keys())],
        "removed": [{"field": f, "old": oa[f], "evidence": _evidence(ra, f)} for f in sorted(oa.keys() - na.keys())],
        "changed": [{"field": f, "old": oa[f], "new": na[f],
                     "evidence": {"old": _evidence(ra, f), "new": _evidence(rb, f)}}
                    for f in sorted(oa.keys() & na.keys()) if oa[f] != na[f]],
    }
    desc = {"changed": ca["description_sha256"] != cb["description_sha256"],
            "old_chars": ca["description_chars"], "new_chars": cb["description_chars"], "text_diff": None}
    if desc["changed"] and ra is not None and rb is not None:  # text only kept for snapshots with a stored record
        desc["text_diff"] = list(difflib.unified_diff(_sentences(get(ra, "content", "full_description")),
                                                      _sentences(get(rb, "content", "full_description")),
                                                      "before", "after", lineterm="", n=1))
    return {
        "from": {"id": a["id"], "crawled_at": a["taken_at"]}, "to": {"id": b["id"], "crawled_at": b["taken_at"]},
        "attributes": attrs,
        "description": desc,
        "price": {"changed": (ca["price"], ca["currency"]) != (cb["price"], cb["currency"]),
                  "old": {"price": ca["price"], "currency": ca["currency"]},
                  "new": {"price": cb["price"], "currency": cb["currency"]}},
        "structured_data": {"changed": ca["schema"] != cb["schema"], "old": ca["schema"], "new": cb["schema"]},
        "languages": {"added": sorted(set(cb["languages"]) - set(ca["languages"])),
                      "removed": sorted(set(ca["languages"]) - set(cb["languages"]))},
        "visibility": {"changed": ca.get("visibility") != cb.get("visibility"),
                       "old": ca.get("visibility"), "new": cb.get("visibility")},
    }
