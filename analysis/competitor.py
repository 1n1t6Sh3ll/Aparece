"""Competitor intelligence table and typed gap list (vision sections 7, 13-16).

Framing: every issue is a measurable difference associated with the observed
visibility gap. Nothing here says a difference causes a ranking or visibility change.
Labels: OBSERVED_FACT / SUPPORTED_HYPOTHESIS / UNKNOWN (vision section 21).

Column definitions (all computed from normalized records, no network):
  attributes_present    count of analysis.gaps.ATTRIBUTES present
  jsonld_fields         distinct property names on Product / ProductGroup JSON-LD nodes
  verified_facts        distinct evidence fields with confidence >= 0.9, excluding
                        fields with an unresolved conflict
  spanish_content       full   = record is Spanish, or a Spanish sibling page (same
                                 merchant + product_group_id, or a shared GTIN) has a description
                        partial = Spanish sibling with title only, or Spanish words in
                                 this page's text
                        none   = neither
                        (peer median uses only peers in the target's page language)
  independent_evidence  distinct evidence source domains other than the merchant's;
                        "not measured" when none are recorded (the collector only
                        reads the merchant page)
  entity_consistency_pct share of passing checks: product name tokens appear in title,
                        h1, meta title and JSON-LD name; brand equals JSON-LD brand and
                        appears in title or meta title (only surfaces that exist)
  contradictions        unresolved conflicts in the record

CLI: python -m analysis.competitor --data records.jsonl --product-id p_123 [--k 5]
"""
import argparse
import json
import sys
from urllib.parse import urlparse

from analysis.gaps import MAJORITY, _issue, _median, attributes_present
from analysis.peers import get, load_records, similar_peers, tokens

FRAMING = "Measurable differences associated with the observed visibility gap; not causes."
VERIFIED_CONFIDENCE = 0.9
NAME_TOKEN_SHARE = 0.8
SPANISH_LEVELS = {"none": 0, "partial": 1, "full": 2}
ES_WORDS = {"el", "la", "los", "las", "del", "y", "con", "para", "una", "que", "por",
            "sus", "camiseta", "algodón", "manga", "tejido", "talla", "hombre", "mujer"}
PRODUCT_TYPES = {"Product", "ProductGroup"}


def _jsonld_nodes(rec):
    out, stack = [], list((rec.get("structured_data") or {}).get("raw_json_ld") or [])
    while stack:
        n = stack.pop()
        if isinstance(n, list):
            stack.extend(n)
        elif isinstance(n, dict):
            t = n.get("@type")
            if set(t if isinstance(t, list) else [t]) & PRODUCT_TYPES:
                out.append(n)
            stack.extend(n.get("@graph") or [])
    return out


def jsonld_fields(rec):
    return sorted({k for n in _jsonld_nodes(rec) for k in n if not k.startswith("@")})


def _conflicting(rec):
    return {c.get("field") for c in rec.get("conflicts") or [] if c.get("status") == "conflicting"}


def verified_facts(rec):
    bad = _conflicting(rec)
    return len({e.get("field") for e in rec.get("evidence") or []
                if (e.get("confidence") or 0) >= VERIFIED_CONFIDENCE and e.get("field") not in bad})


def _domain(url):
    h = (urlparse(url or "").hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def independent_evidence(rec):
    own = (get(rec, "source", "merchant_domain") or "").lower()
    doms = {_domain(e.get("source_url")) for e in rec.get("evidence") or []}
    doms = {d for d in doms if d and d != own and not d.endswith("." + own)}
    return len(doms) if doms else "not measured"


def _has_spanish_text(rec):
    c = rec.get("content") or {}
    toks = tokens(" ".join(str(x) for x in (c.get("title"), c.get("full_description"),
                                            c.get("meta_description")) if x))
    hits = sum(t in ES_WORDS for t in toks)
    return hits >= 3 and hits / max(len(toks), 1) >= 0.05


def _siblings(rec, records):
    dom, grp = get(rec, "source", "merchant_domain"), get(rec, "variants", "product_group_id")
    gt = {i.get("gtin") for i in get(rec, "variants", "items") or [] if i.get("gtin")}
    for r in records:
        if r.get("product_id") == rec.get("product_id"):
            continue
        same_grp = grp and grp == get(r, "variants", "product_group_id") and dom == get(r, "source", "merchant_domain")
        rgt = {i.get("gtin") for i in get(r, "variants", "items") or [] if i.get("gtin")}
        if same_grp or gt & rgt:
            yield r


def spanish_content(rec, records=()):
    if get(rec, "source", "language") == "es":
        return "full"
    es = [r for r in _siblings(rec, records) if get(r, "source", "language") == "es"]
    if any(get(r, "content", "full_description") for r in es):
        return "full"
    if es or _has_spanish_text(rec):
        return "partial"
    return "none"


def _covers(name, surface):
    nt, st = set(tokens(name)), set(tokens(surface))
    return bool(nt) and len(nt & st) / len(nt) >= NAME_TOKEN_SHARE


def entity_checks(rec):
    c = rec.get("content") or {}
    name, brand = get(rec, "identity", "product_name"), get(rec, "identity", "brand")
    nodes = _jsonld_nodes(rec)
    ld_name = next((n.get("name") for n in nodes if n.get("name")), None)
    ld_brand = next((b.get("name") if isinstance(b, dict) else b
                     for b in (n.get("brand") for n in nodes) if b), None)
    checks = {}
    if name:
        for surf in ("title", "h1", "meta_title"):
            if c.get(surf):
                checks[f"name_in_{surf}"] = _covers(name, c[surf])
        if ld_name:
            checks["name_in_jsonld"] = _covers(name, ld_name)
    if brand:
        if ld_brand:
            checks["brand_eq_jsonld"] = tokens(brand) == tokens(ld_brand)
        heads = " ".join(c.get(s) or "" for s in ("title", "meta_title"))
        if heads.strip():
            checks["brand_in_title"] = _covers(brand, heads)
    return checks


def entity_consistency(rec):
    ch = entity_checks(rec)
    return round(100 * sum(ch.values()) / len(ch), 1) if ch else None


def profile(rec, records=()):
    return {"product_id": rec.get("product_id"),
            "merchant_domain": get(rec, "source", "merchant_domain"),
            "attributes_present": sum(attributes_present(rec).values()),
            "jsonld_fields": len(jsonld_fields(rec)),
            "verified_facts": verified_facts(rec),
            "spanish_content": spanish_content(rec, records),
            "independent_evidence": independent_evidence(rec),
            "entity_consistency_pct": entity_consistency(rec),
            "contradictions": len(_conflicting(rec))}


NUMERIC = ["attributes_present", "jsonld_fields", "verified_facts",
           "independent_evidence", "entity_consistency_pct", "contradictions"]


def competitor_table(target, peers, records=(), top=3):
    """peers: records, (score, record) pairs, or similar_peers() rows."""
    peers = [p[1] if isinstance(p, tuple) else p.get("record", p) for p in peers]
    tp, pp = profile(target, records), [profile(p, records) for p in peers]
    med = {}
    for col in NUMERIC:
        xs = [p[col] for p in pp if isinstance(p[col], (int, float))]
        med[col] = _median(xs) if xs else "not measured"
    # Spanish coverage is compared only with peers in the target's own page language:
    # a Spanish-language peer is trivially "full" and says nothing about whether an
    # English page has a Spanish counterpart.
    lang = get(target, "source", "language")
    same = [p for p, r in zip(pp, peers) if get(r, "source", "language") == lang]
    levels = [SPANISH_LEVELS[p["spanish_content"]] for p in same]
    med["spanish_content"] = (["none", "partial", "full"][round(_median(levels))] if levels else None)
    return {"framing": FRAMING, "target": tp, "peer_median": med, "top_peers": pp[:top],
            "peer_count": len(pp), "spanish_peer_ids": [p["product_id"] for p in same]}


def gap_issues(target, peers, records=(), lvg=None):
    """Typed issues grouped by kind: missing_attributes, entity_inconsistency,
    incomplete_structured_data, weak_language_coverage, factual_contradictions.
    lvg: the target's measured V_EN - V_ES (benchmark.metrics.language_visibility_gap),
    or None. The Spanish SUPPORTED_HYPOTHESIS is emitted only when lvg > 0."""
    peers = [p[1] if isinstance(p, tuple) else p.get("record", p) for p in peers]
    table = competitor_table(target, peers, records)
    t, med, n = table["target"], table["peer_median"], len(peers)
    ids = [p.get("product_id") for p in peers]
    issues = []

    def add(kind, label, field, statement, evidence, action):
        issues.append(dict(_issue(label, field, statement, evidence, action), kind=kind))

    tp, pp = attributes_present(target), [attributes_present(p) for p in peers]
    missing = [a for a, v in tp.items() if not v and n and sum(x[a] for x in pp) / n > MAJORITY]
    if missing:
        add("missing_attributes", "OBSERVED_FACT", "attributes",
            f"{len(missing)} attributes missing that most of {n} peers state",
            {"attributes": missing, "peer_ids": ids}, "Add verified values only; do not invent them.")

    ec, pec = t["entity_consistency_pct"], med["entity_consistency_pct"]
    if ec is not None and ec < 100:
        failed = [k for k, v in entity_checks(target).items() if not v]
        add("entity_inconsistency", "OBSERVED_FACT", "entity_consistency",
            f"Entity consistency {ec}% (peer median {pec}); failing checks: {', '.join(failed)}",
            {"failed_checks": failed}, "Use the same product name and brand in title, h1, meta and JSON-LD.")

    pj = med["jsonld_fields"]
    if isinstance(pj, (int, float)) and t["jsonld_fields"] < pj:
        peer_fields = {f for p in peers for f in jsonld_fields(p)}
        add("incomplete_structured_data", "OBSERVED_FACT", "jsonld_fields",
            f"{t['jsonld_fields']} JSON-LD product fields vs peer median {pj}",
            {"missing_vs_peers": sorted(peer_fields - set(jsonld_fields(target)))},
            "Add JSON-LD fields that match the visible page.")

    ts, ps = t["spanish_content"], med["spanish_content"]
    if ps is not None and SPANISH_LEVELS[ts] < SPANISH_LEVELS[ps]:
        add("weak_language_coverage", "OBSERVED_FACT", "spanish_content",
            f"Spanish content is {ts}; median of same-language peers is {ps}",
            {"peers_compared": table["spanish_peer_ids"]},
            "Publish a reviewed Spanish page; re-measure Spanish visibility (LVG).")
        if isinstance(lvg, (int, float)) and lvg > 0:
            add("weak_language_coverage", "SUPPORTED_HYPOTHESIS", "spanish_content",
                f"Spanish page coverage is a measurable difference associated with the observed "
                f"Spanish visibility gap (LVG = {lvg}); testing it is reasonable",
                {"lvg": lvg}, "Change one thing at a time and compare V_ES before and after.")
        else:
            add("weak_language_coverage", "UNKNOWN", "lvg",
                "No Spanish visibility gap is established: LVG " +
                ("was not provided" if lvg is None else f"= {lvg} shows no gap"),
                {"lvg": lvg}, "Run the benchmark in EN and ES to measure LVG = V_EN - V_ES.")

    conf = [c for c in target.get("conflicts") or [] if c.get("status") == "conflicting"]
    if conf:
        add("factual_contradictions", "OBSERVED_FACT", "conflicts",
            f"{len(conf)} unresolved conflicting facts on the page",
            {"fields": [c.get("field") for c in conf]}, "Resolve which value is true and fix the page.")

    if t["independent_evidence"] == "not measured":
        add("independent_evidence", "UNKNOWN", "independent_evidence",
            "Independent (non-merchant) evidence is not measured by the current collector",
            {}, "Collect third-party sources before comparing on this column.")
    add("visibility_effect", "UNKNOWN", "visibility_effect",
        "Whether closing these differences changes AI visibility is unmeasured",
        {}, "Run the AI-visibility benchmark before and after any change.")
    return {"framing": FRAMING, "table": table, "issues": issues}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Competitor intelligence table and gap list")
    ap.add_argument("--data", required=True, help="normalized records JSONL")
    ap.add_argument("--product-id", required=True)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--lvg", type=float, help="measured V_EN - V_ES for this product")
    a = ap.parse_args(argv)
    records = load_records(a.data)
    target = next((r for r in records if r.get("product_id") == a.product_id), None)
    if target is None:
        print(f"product_id not found: {a.product_id}", file=sys.stderr)
        return 2
    sim = similar_peers(target, records, a.k)
    out = gap_issues(target, sim["peers"], records, a.lvg)
    out["similarity"] = {"text_method": sim["text_method"], "weights": sim["weights"],
                         "peers": [{k: v for k, v in r.items() if k != "record"} for r in sim["peers"]]}
    json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
