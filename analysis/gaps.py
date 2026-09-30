"""Compare a target product with comparable peers and list measurable gaps.

Every issue is typed OBSERVED_FACT / SUPPORTED_HYPOTHESIS / UNKNOWN (VISION §21).
No composite score is produced (VISION §20). Nothing here claims an effect on ranking.

CLI: python -m analysis.gaps --data records.jsonl --product-id p_123 [--k 10]
"""
import argparse
import json
import re
import statistics
import sys

from analysis.peers import find_peers, get, load_records, price_comparable

# (section, key) attributes counted for completeness. A value is "present" if not
# None and not an empty string/list/dict.
ATTRIBUTES = [
    ("identity", "brand"), ("identity", "audience"), ("identity", "subcategory"),
    ("content", "full_description"),
    ("materials", "primary_material"), ("materials", "material_percentages"),
    ("materials", "fabric_type"), ("materials", "fabric_weight_gsm"),
    ("materials", "stretch"), ("materials", "texture"),
    ("fit_and_style", "fit"), ("fit_and_style", "neckline"),
    ("fit_and_style", "collar_type"), ("fit_and_style", "sleeve_length"),
    ("fit_and_style", "shirt_length"), ("fit_and_style", "pattern"),
    ("fit_and_style", "style"),
    ("variants", "colors"), ("variants", "sizes"),
    ("commerce", "price"), ("commerce", "currency"), ("commerce", "availability"),
    ("commerce", "gtin"),
]
SCHEMA_FLAGS = ["product_schema_present", "offer_schema_present", "product_group_present"]
MAJORITY = 0.5  # flag a missing attribute when more than half of peers have it


def _present(v):
    return v not in (None, "", [], {})


def attributes_present(rec):
    return {f"{s}.{k}": _present(get(rec, s, k)) for s, k in ATTRIBUTES}


def completeness(rec):
    p = attributes_present(rec)
    return round(100 * sum(p.values()) / len(p), 1)


def description_chars(rec):
    c = rec.get("content") or {}
    parts = [c.get("full_description") or "", c.get("short_description") or ""]
    parts += [b for b in (c.get("bullet_points") or []) if isinstance(b, str)]
    return sum(len(p) for p in parts)


def description_text(rec):
    c = rec.get("content") or {}
    parts = [c.get("full_description") or "", c.get("short_description") or ""]
    parts += [b for b in (c.get("bullet_points") or []) if isinstance(b, str)]
    return "\n".join(p for p in parts if p)


# Shopper questions a shirt description can answer (EN/ES). Each counts once however often it is mentioned,
# so repeating keywords adds nothing.
INTENTS = {
    "material": r"\b(?:cotton|polyester|linen|wool|merino|viscose|modal|lyocell|tencel|elastane|spandex|nylon|hemp|"
                r"bamboo|algod[oó]n|poli[eé]ster|lino|lana)\b",
    "composition": r"\b\d{1,3}\s?%",
    "fabric": r"\b(?:jersey|piqu[eé]|pique|oxford|poplin|popelina|twill|flannel|franela|rib|interlock|slub|knit|"
              r"punto|gsm|oz|g/m)\b",
    "fit": r"\b(?:slim|regular|relaxed|oversized?|boxy|classic|athletic|loose|tailored|holgad[oa]|ajustad[oa])\b"
           r"|\bfit\b|\bcorte\b",
    "neck_or_collar": r"\b(?:crew|v-neck|neck|neckline|collar|henley|cuello|mock)\b",
    "sleeve": r"\bsleeves?\b|\bmangas?\b|\bsleeveless\b",
    "size_guide": r"\b(?:model|wearing|size guide|sizing|true to size|measurements|chest|lleva|talla|gu[ií]a de tallas|"
                  r"medidas)\b",
    "care": r"\b(?:wash|washing|machine|tumble|dry|iron|bleach|lavar|lavado|secadora|planchar)\b",
    "origin_or_certification": r"\b(?:made in|hecho en|fabricado en|organic|org[aá]nico|gots|oeko|fair ?trade|"
                               r"recycled|reciclad[oa]|certified|certificad[oa])\b",
    "feel_or_feature": r"\b(?:soft|breathable|stretch|durable|lightweight|heavyweight|pre-?shrunk|moisture|"
                       r"suave|transpirable|el[aá]stic[oa]|ligera|resistente)\b",
}
REPEAT_FREE = 0.15  # share of repeated word 3-grams tolerated before the description score is reduced


def repetition(text):
    """Share of word 3-grams that repeat an earlier 3-gram (0 = no repetition, near 1 = the same text over again)."""
    words = re.findall(r"\w+", (text or "").lower())
    grams = list(zip(words, words[1:], words[2:]))
    return round(1 - len(set(grams)) / len(grams), 3) if len(grams) >= 6 else 0.0


def description_coverage(rec):
    """Distinct shopper intents the description covers (each once, so stuffing adds nothing) times a repetition
    factor: full credit up to REPEAT_FREE repeated 3-grams, falling linearly to 0 at twice that plus 0.5."""
    text = description_text(rec)
    hits = sorted(k for k, rx in INTENTS.items() if re.search(rx, text, re.I))
    rep = repetition(text)
    factor = 1.0 if rep <= REPEAT_FREE else max(0.0, 1 - (rep - REPEAT_FREE) / 0.5)
    return {"intents": hits, "covered": len(hits), "of": len(INTENTS), "repetition": rep,
            "repetition_factor": round(factor, 3), "value": round(len(hits) / len(INTENTS) * factor, 4)}


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def _issue(type_, field, statement, evidence, action):
    return {"type": type_, "field": field, "statement": statement,
            "evidence": evidence, "suggested_action": action}


def analyze(target, peers):
    """peers: list of records (or (score, record) pairs from find_peers)."""
    peers = [p[1] if isinstance(p, tuple) else p for p in peers]
    n = len(peers)
    ids = [p.get("product_id") for p in peers]
    tp = attributes_present(target)
    pp = [attributes_present(p) for p in peers]
    coverage = {a: {"present": sum(x[a] for x in pp), "of": n} for a in tp}
    peer_compl = [completeness(p) for p in peers]
    peer_desc = [description_chars(p) for p in peers]
    tsd = target.get("structured_data") or {}
    sd = {f: {"target": bool(tsd.get(f)),
              "peers_present": sum(bool((p.get("structured_data") or {}).get(f)) for p in peers),
              "of": n} for f in SCHEMA_FLAGS}
    metrics = {
        "product_id": target.get("product_id"),
        "language": get(target, "source", "language"),
        "peer_count": n,
        "peer_ids": ids,
        "attribute_completeness_pct": {"target": completeness(target),
                                       "peer_median": _median(peer_compl),
                                       "attributes_checked": len(tp)},
        "attribute_peer_coverage": coverage,
        "description_chars": {"target": description_chars(target),
                              "peer_median": _median(peer_desc)},
        "structured_data": sd,
    }

    issues = []
    missing_majority = []
    for a, present in tp.items():
        have = [i for i, x in zip(ids, pp) if x[a]]
        if not present and n and len(have) / n > MAJORITY:
            missing_majority.append(a)
            issues.append(_issue(
                "OBSERVED_FACT", a,
                f"{a.split('.')[1]} missing; present in {len(have)}/{n} comparable products",
                {"peers_with_attribute": have, "count": len(have), "of": n},
                f"Add verified {a.split('.')[1].replace('_', ' ')} if known; do not invent it."))

    med = metrics["attribute_completeness_pct"]["peer_median"]
    tc = metrics["attribute_completeness_pct"]["target"]
    if med is not None and tc < med:
        issues.append(_issue(
            "OBSERVED_FACT", "attribute_completeness",
            f"Attribute completeness {tc}% vs peer median {med}% ({len(tp)} attributes checked)",
            {"peer_ids": ids, "peer_values": peer_compl},
            "Fill missing attributes with verified product facts only."))

    dmed = metrics["description_chars"]["peer_median"]
    dt = metrics["description_chars"]["target"]
    if dmed and dt < 0.5 * dmed:
        issues.append(_issue(
            "OBSERVED_FACT", "description_chars",
            f"Description text is {dt} chars vs peer median {dmed}",
            {"peer_ids": ids, "peer_values": peer_desc},
            "Consider adding verified product details; length alone is not a goal."))

    for f, v in sd.items():
        if not v["target"] and n and v["peers_present"] / n > MAJORITY:
            issues.append(_issue(
                "OBSERVED_FACT", f"structured_data.{f}",
                f"{f} is false for target; true for {v['peers_present']}/{n} comparable products",
                {"peers_with_flag": [i for i, p in zip(ids, peers)
                                     if (p.get("structured_data") or {}).get(f)]},
                "Add valid structured data that matches the visible page, if you control the page."))

    if missing_majority:
        issues.append(_issue(
            "SUPPORTED_HYPOTHESIS", "attributes",
            "Adding the verified attributes most peers expose is a reasonable intervention to test",
            {"attributes": missing_majority},
            "Change one thing at a time and re-measure with the benchmark."))

    unpriced = [i for i, p in zip(ids, peers) if not price_comparable(target, p)]
    if unpriced:
        issues.append(_issue(
            "UNKNOWN", "price_band",
            f"Price band not applied to {len(unpriced)}/{n} peers "
            "(price or currency unknown, or currencies differ)",
            {"peer_ids": unpriced}, "Record price and currency to tighten the comparison."))

    if n < 3:
        issues.append(_issue(
            "UNKNOWN", "peers",
            f"Only {n} comparable products found; comparisons are weak",
            {"peer_count": n}, "Collect more comparable products before acting."))

    issues.append(_issue(
        "UNKNOWN", "ranking_effect",
        "Effect of these gaps on AI/search ranking is unmeasured until the AI-visibility benchmark runs",
        {}, "Run the AI-visibility benchmark before and after any change."))
    return {"metrics": metrics, "issues": issues}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic product gap analysis")
    ap.add_argument("--data", required=True, help="normalized records JSONL")
    ap.add_argument("--product-id", required=True)
    ap.add_argument("--k", type=int, default=10)
    a = ap.parse_args(argv)
    records = load_records(a.data)
    target = next((r for r in records if r.get("product_id") == a.product_id), None)
    if target is None:
        print(f"product_id not found: {a.product_id}", file=sys.stderr)
        return 2
    json.dump(analyze(target, find_peers(target, records, a.k)), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
