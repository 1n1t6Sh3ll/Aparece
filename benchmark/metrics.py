"""Transparent visibility metrics (vision section 19) and JSON/markdown reports."""
from collections import Counter, defaultdict
from itertools import combinations

from .match import match_response


def model_key(r):
    """provider:model, so the same model id under two providers stays distinct."""
    return f"{r['provider']}:{r['model']}" if r.get("provider") else r["model"]


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
        groups[(model_key(r), r["prompt_id"], r["variant"])].append(set(m["mentions"]))
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
    by_model = defaultdict(list)
    for r, m in zip(records, matched):
        by_model[model_key(r)].append((r, m))
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
