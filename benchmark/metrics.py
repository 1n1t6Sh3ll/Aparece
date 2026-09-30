"""Transparent visibility metrics (vision section 19) and JSON/markdown reports."""
from collections import Counter, defaultdict
from itertools import combinations

from .match import match_response


def model_key(r, ambiguous=()):
    """Report key: the model id (backward compatible), or provider:model when that
    id appears under more than one provider in the same results."""
    return f"{r['provider']}:{r['model']}" if r["model"] in ambiguous else r["model"]


def _entity_rows(matched, entity_of, cited_key, k):
    """Mention rate, top-k, MRR, citation rate for every entity in `entity_of`."""
    n = len(matched)
    rows = {}
    for ent in sorted(set(entity_of.values())):
        ranks, cites = [], 0
        for m in matched:
            pos = next((i + 1 for i, pid in enumerate(m["mentions"]) if entity_of.get(pid) == ent), None)
            ranks.append(pos)
            cites += ent in cited_key(m)
        rows[ent] = {
            "mention_rate": round(sum(r is not None for r in ranks) / n, 4),
            f"top{k}_rate": round(sum(r is not None and r <= k for r in ranks) / n, 4),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 4),
            "citation_rate": round(cites / n, 4),
        }
    return rows


def stability(records, matched):
    """Mean pairwise Jaccard of mentioned-product sets across repeats of one prompt."""
    groups = defaultdict(list)
    for r, m in zip(records, matched):
        groups[(r.get("provider"), r["model"], r["prompt_id"], r["variant"])].append(set(m["mentions"]))
    scores = []
    for sets in groups.values():
        for a, b in combinations(sets, 2):
            scores.append(len(a & b) / len(a | b) if a | b else 1.0)
    return round(sum(scores) / len(scores), 4) if scores else None


def _summary(records, matched, products, k):
    sites = {p["product_id"]: p["site"] for p in products}
    return {
        "responses": len(records),
        "any_catalog_mention_rate": round(sum(bool(m["mentions"]) for m in matched) / len(matched), 4),
        "stability": stability(records, matched),
        "unmatched_mentions": sum(len(m["unmatched"]) for m in matched),
        "sites": _entity_rows(matched, sites, lambda m: m["cited_sites"], k),
    }


def build_report(records, products, k=3):
    matched = [match_response(r.get("response_text", ""), products) for r in records]
    providers = defaultdict(set)
    for r in records:
        providers[r["model"]].add(r.get("provider"))
    ambiguous = {mid for mid, provs in providers.items() if len(provs) > 1}
    by_model = defaultdict(list)
    for r, m in zip(records, matched):
        by_model[model_key(r, ambiguous)].append((r, m))
    models = {}
    for model, pairs in sorted(by_model.items()):
        recs, ms = [p[0] for p in pairs], [p[1] for p in pairs]
        out = _summary(recs, ms, products, k)
        out["products"] = _entity_rows(ms, {p["product_id"]: p["product_id"] for p in products},
                                       lambda m: m["cited_products"], k)
        langs = defaultdict(list)
        for r, m in pairs:
            langs[r["language"]].append((r, m))
        out["languages"] = {lang: _summary([p[0] for p in lp], [p[1] for p in lp], products, k)
                            for lang, lp in sorted(langs.items())}
        models[model] = out
    unmatched = Counter((u["kind"], u["text"]) for m in matched for u in m["unmatched"])
    return {
        "k": k,
        "responses": len(records),
        "models": models,
        "top_unmatched": [{"kind": kd, "text": t, "count": c} for (kd, t), c in unmatched.most_common(20)],
    }


def _by_model(records, products):
    providers = defaultdict(set)
    for r in records:
        providers[r["model"]].add(r.get("provider"))
    ambiguous = {mid for mid, provs in providers.items() if len(provs) > 1}
    out = defaultdict(list)
    for r in records:
        out[model_key(r, ambiguous)].append((r, match_response(r.get("response_text", ""), products)))
    return out


def competitor_win_rate(records, products, a, b):
    """Pairwise competitor win rate CWR(A,B) per model and overall (vision section 19).

    Per response: A wins when A is mentioned and B is not, or both are and A comes first;
    B wins symmetrically; neither mentioned is no contest. CWR = A wins / contests
    (None when there are no contests). CWR(B,A) = 1 - CWR(A,B)."""
    def rate(pairs):
        aw = bw = 0
        for _, m in pairs:
            ra = m["mentions"].index(a) if a in m["mentions"] else None
            rb = m["mentions"].index(b) if b in m["mentions"] else None
            if ra is not None and (rb is None or ra < rb):
                aw += 1
            elif rb is not None:
                bw += 1
        n = aw + bw
        return {"a_wins": aw, "b_wins": bw, "contests": n, "responses": len(pairs),
                "cwr": round(aw / n, 4) if n else None}
    groups = _by_model(records, products)
    return {"a": a, "b": b, "overall": rate([p for ps in groups.values() for p in ps]),
            "models": {mk: rate(ps) for mk, ps in sorted(groups.items())}}


def language_visibility_gap(records, products, metric="mention_rate", en="en", es="es"):
    """LVG = V_EN - V_ES per model and product, where V is `metric` (mention_rate,
    mrr, citation_rate or top{k}_rate from _entity_rows with k=3). None when either
    language has no responses for that model. Positive means more visible in English."""
    ids = {p["product_id"]: p["product_id"] for p in products}
    out = {}
    for mk, pairs in sorted(_by_model(records, products).items()):
        rows = {}
        for lang in (en, es):
            ms = [m for r, m in pairs if r.get("language") == lang]
            rows[lang] = _entity_rows(ms, ids, lambda m: m["cited_products"], 3) if ms else None
        out[mk] = {}
        for pid in sorted(ids):
            ve = rows[en][pid][metric] if rows[en] else None
            vs = rows[es][pid][metric] if rows[es] else None
            out[mk][pid] = {"v_en": ve, "v_es": vs,
                            "lvg": round(ve - vs, 4) if ve is not None and vs is not None else None}
    return {"metric": metric, "models": out}


def claim_accuracy_passthrough(claims_rep):
    """Claim accuracy per model and language copied from claims.claims_report output
    (no recomputation), for side-by-side use with CWR and LVG."""
    return {"overall": (claims_rep.get("overall") or {}).get("claim_accuracy"),
            "models": {mk: {"claim_accuracy": m.get("claim_accuracy"),
                            "languages": {l: v.get("claim_accuracy")
                                          for l, v in (m.get("languages") or {}).items()}}
                       for mk, m in (claims_rep.get("models") or {}).items()}}


def to_markdown(report):
    k = report["k"]
    lines = [f"# AI visibility report ({report['responses']} responses)", "",
             "Observed outputs of black-box systems; not claims about their internals.", ""]
    names = list(report["models"])
    sites = sorted({s for m in report["models"].values() for s in m["sites"]})
    lines += ["## Model comparison (mention rate / MRR, all languages)", "",
              "| site | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for site in sites:
        cells = []
        for n in names:
            row = report["models"][n]["sites"].get(site)
            cells.append(f"{row['mention_rate']:.2f} / {row['mrr']:.2f}" if row else "-")
        lines.append(f"| {site} | " + " | ".join(cells) + " |")
    lines += ["", "## Detail", "",
             f"| model | language | site | mention | top{k} | MRR | citation |",
             "|---|---|---|---|---|---|---|"]
    for model, m in report["models"].items():
        scopes = [("all", m)] + list(m["languages"].items())
        for lang, s in scopes:
            for site, row in s["sites"].items():
                lines.append(f"| {model} | {lang} | {site} | {row['mention_rate']:.2f} | "
                             f"{row[f'top{k}_rate']:.2f} | {row['mrr']:.2f} | {row['citation_rate']:.2f} |")
    lines += ["", "| model | language | responses | any mention | stability | unmatched |", "|---|---|---|---|---|---|"]
    for model, m in report["models"].items():
        for lang, s in [("all", m)] + list(m["languages"].items()):
            stab = "n/a" if s["stability"] is None else f"{s['stability']:.2f}"
            lines.append(f"| {model} | {lang} | {s['responses']} | {s['any_catalog_mention_rate']:.2f} | "
                         f"{stab} | {s['unmatched_mentions']} |")
    if report["top_unmatched"]:
        lines += ["", "Top unmatched mentions:"]
        lines += [f"- {u['count']}x {u['kind']}: {u['text']}" for u in report["top_unmatched"][:10]]
    return "\n".join(lines) + "\n"
