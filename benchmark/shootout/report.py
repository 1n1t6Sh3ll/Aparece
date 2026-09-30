"""Shoot-out report: per-part audits (title, tags, description), per-part winners, a merged recommendation built
only from guardrail-passing parts, and controlled visibility with bootstrap CIs. JSON + markdown."""
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from benchmark import harness
from benchmark.shootout import score

LABEL = "Controlled evaluation (simulated shopping context); not proof of real-world ranking."
PARTS = ("title", "tags", "description")


def load_rows(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def audit(c, g):
    truth, lang, intents = g["truth"], g["language"], g["intents"]
    t = score.title_audit(c["title"], truth, lang) if c.get("title") else None
    tags = score.tags_audit(c.get("tags"), truth, lang, intents)
    d = score.description_audit(c["text"], truth, lang, intents, c.get("json_ld")) if c.get("text") else None
    flagged = (t["guard"]["flagged_sentences"] if t else 0) + len(tags["false"]) + (d["guard"]["flagged_sentences"] if d else 0)
    claims = (t["guard"]["unsupported_claims"] if t else 0) + (d["guard"]["unsupported_claims"] if d else 0)
    return {"title": t, "tags": tags, "description": d, "flagged": flagged, "unsupported_claims": claims,
            "qualified": bool(t and t["passes"] and d and d["passes"] and not tags["false"])}


MERCHANT_LINE = re.compile(r"^(?:care|cuidado)\s*:", re.I)  # verbatim merchant care text
OMITTED = {"en": ("(merchant description omitted from the committed sample)",
                  " Care: (merchant care text omitted from the sample)."),
           "es": ("(descripción del comercio omitida en la muestra publicada)",
                  " Cuidado: (instrucciones de cuidado del comercio omitidas en la muestra).")}


def scrub(a, gen, truth, lang="en"):
    """Committed samples carry no verbatim merchant text: no original description, no care text, no flagged quotes."""
    care = " ".join(truth.get("care") or []).lower()

    def merchant(sent):
        body = MERCHANT_LINE.sub("", sent).strip().rstrip(".").lower()
        return bool(MERCHANT_LINE.match(sent)) or (len(body) > 3 and body in care)
    desc_note, care_note = OMITTED.get(lang, OMITTED["en"])
    if gen == "original":
        a["raw"]["text"] = desc_note
    elif a["raw"]["text"]:
        sents = score.guard.sentences(a["raw"]["text"])
        kept = [x for x in sents if not merchant(x)]
        a["raw"]["text"] = " ".join(kept) + (care_note if len(kept) < len(sents) else "")
    for part in ("title", "description"):
        if a[part]:
            a[part]["guard"]["flagged"] = []


def _best(items, key):
    items = list(items)
    return max(items, key=key)[0] if items else None


def part_winners(cands):
    """Per-part winner among parts that pass the guardrail. Description uses measured MRR when judged."""
    title = _best(((s, c) for s, c in cands.items() if c["title"] and c["title"]["passes"]),
                  lambda x: (x[1]["title"]["score"], -abs(x[1]["title"]["chars"] - 60)))
    tags = _best(((s, c) for s, c in cands.items() if c["tags"]["passes"] and c["tags"]["n"]),
                 lambda x: x[1]["tags"]["score"])
    desc = _best(((s, c) for s, c in cands.items() if c["description"] and c["description"]["passes"]),
                 lambda x: ((x[1]["visibility"] or {}).get("mrr", {}).get("value", -1),
                            x[1]["description"]["attribute_coverage"] or 0))
    return {"title": title, "tags": tags, "description": desc}


def merged(cands, winners, max_tags=score.MAX_TAGS):
    """Recommended title/tags/description, each taken from a guardrail-passing part (with its source)."""
    out = {"title": None, "tags": None, "description": None}
    if winners["title"]:
        out["title"] = {"text": cands[winners["title"]]["raw"]["title"], "from": winners["title"]}
    order = ([winners["tags"]] if winners["tags"] else []) + [s for s in cands if s != winners["tags"]]
    tags, seen, src = [], set(), []
    for s in order:
        for t in cands[s]["tags"]["passing"]:
            k = " ".join(score.guard._tokens(t))
            if k not in seen and len(tags) < max_tags:
                seen.add(k)
                tags.append(t)
                src.append(s)
    if tags:
        out["tags"] = {"list": tags, "from": sorted(set(src), key=src.index)}
    if winners["description"]:
        out["description"] = {"text": cands[winners["description"]]["raw"]["text"], "from": winners["description"]}
    return out


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 4) if vals else None


def build(args, groups, gens, judges, log=print):
    out = Path(args.out_dir)
    raw = {(r["group"], r["generator"]): r for r in load_rows(out / "candidates.jsonl")}
    obs = load_rows(out / "judge_calls.jsonl")
    judge_ids = [f"{p}:{m}" for p, m in judges]
    holdout = args.holdout_judge if args.holdout_judge in judge_ids else None
    primary = [o for o in obs if o["judge"] != holdout]
    B = args.bootstrap
    sel = lambda rows, **kw: [o for o in rows if all(o[k] == v for k, v in kw.items())]  # noqa: E731
    ci = lambda rows: score.with_ci(rows, B) if rows else None  # noqa: E731

    products, audits = [], {s: [] for s in gens}
    for g in groups:
        cands = {}
        for s in gens:
            c = raw.get((g["group"], s))
            if not c:
                continue
            a = audit(c, g)
            a.update(raw={k: c.get(k) for k in ("title", "tags", "text", "error")},
                     visibility=ci(sel(primary, group=g["group"], generator=s)), cost_usd=round(c.get("cost_usd") or 0, 6))
            if getattr(args, "sample", False):
                scrub(a, s, g["truth"], g["language"])
            cands[s] = a
            audits[s].append(a)
        winners = part_winners(cands)
        ranked = {s: c for s, c in cands.items() if c["qualified"] and c["visibility"]}
        products.append({"group": g["group"], "product_id": g["target"]["product_id"], "language": g["language"],
                         "brand": g["target"]["identity"]["brand"], "name": g["target"]["identity"]["product_name"],
                         "url": g["target"]["source"]["canonical_url"], "verified_facts": g["facts"],
                         "prompts": [p["id"] for p in g["prompts"]], "candidates": cands, "part_winners": winners,
                         "visibility_winner": _best(ranked.items(), lambda x: (x[1]["visibility"]["mrr"]["value"],
                                                                              x[1]["visibility"]["mention_rate"]["value"])),
                         "recommended": merged(cands, winners)})

    generators = {}
    for s, al in audits.items():
        titles, descs = [a["title"] for a in al if a["title"]], [a["description"] for a in al if a["description"]]
        generators[s] = {
            "candidates": len(al), "qualified_products": sum(a["qualified"] for a in al),
            "qualified": bool(al) and all(a["qualified"] for a in al),
            "flagged": sum(a["flagged"] for a in al), "unsupported_claims": sum(a["unsupported_claims"] for a in al),
            "title": {"score": _mean(t["score"] for t in titles), "chars": _mean(t["chars"] for t in titles),
                      "passes": sum(t["passes"] for t in titles)},
            "tags": {"score": _mean(a["tags"]["score"] for a in al), "n": _mean(a["tags"]["n"] for a in al),
                     "false": sum(len(a["tags"]["false"]) for a in al), "duplicates": sum(a["tags"]["duplicates"] for a in al),
                     "language_match": _mean(a["tags"]["language_match"] for a in al)},
            "description": {k: _mean(d[k] for d in descs) for k in ("attribute_coverage", "intent_coverage", "readability",
                                                                     "words", "jsonld_completeness")}
            | {"passes": sum(d["passes"] for d in descs)},
            "visibility": ci(sel(primary, generator=s)),
            "by_language": {lang: ci(sel(primary, generator=s, language=lang)) for lang in ("en", "es")},
            "by_judge": {j: ci(sel(obs, generator=s, judge=j)) for j in judge_ids}}

    def ranking(scope):
        r = [s for s, v in generators.items() if v["qualified"] and scope(v)]
        return sorted(r, key=lambda s: (-scope(generators[s])["mrr"]["value"], -scope(generators[s])["mention_rate"]["value"]))

    order = ranking(lambda v: v["visibility"])
    overall = {"ranking": order, "winner": order[0] if order else None}
    if len(order) > 1:
        d = score.paired_diff(sel(primary, generator=order[0]), sel(primary, generator=order[1]), b=B)
        overall.update(runner_up=order[1], diff_vs_runner_up=d, decisive=bool(d and d["lo"] > 0))
    if holdout:
        h = ranking(lambda v: v["by_judge"].get(holdout))
        overall["holdout_judge"] = {"judge": holdout, "winner": h[0] if h else None,
                                    "agrees": bool(h) and bool(order) and h[0] == order[0]}
    overall["by_language"] = {lang: (ranking(lambda v: v["by_language"].get(lang)) or [None])[0] for lang in ("en", "es")}
    parts = {}
    for part in PARTS:
        wins = Counter(p["part_winners"][part] for p in products if p["part_winners"][part])
        parts[part] = {"wins": dict(wins), "winner": max(wins, key=lambda s: (wins[s], -gens.index(s))) if wins else None}
    overall["parts"] = parts

    rep = {"label": LABEL, "sample": bool(getattr(args, "sample", False)),
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "setup": {"products": len(groups), "languages": sorted({g["language"] for g in groups}), "generators": gens,
                     "judges": judge_ids, "holdout_judge": holdout, "prompts_per_product": args.prompts_per_product,
                     "repeats": args.repeats, "splits": ["dev", "val"], "competitors_per_context": 4,
                     "primary_metric": "mrr", "bootstrap": B, "judge_temperature": args.judge_temperature,
                     "gen_temperature": args.gen_temperature, "free_providers": sorted(harness.FREE),
                     "instructions": "optimizer/fix.py SYSTEM + _prompt (LLMs also asked for tags)"},
           "overall": overall, "generators": generators, "products": products,
           "cost": {"judge_calls": len(obs), "judge_usd": round(sum(o["cost_usd"] for o in obs), 4),
                    "generation_usd": round(sum(c.get("cost_usd") or 0 for c in raw.values()), 4)},
           "caveats": [
               "Simulated context: 5 product pages chosen by us, not a real search index or live assistant.",
               f"Small n: {len(groups)} products x {args.prompts_per_product} prompts x {args.repeats} repeats; "
               "CIs are cluster bootstrap over (product, prompt).",
               ("SAMPLE: the judges were MOCK models (deterministic fakes), not OpenAI or Anthropic; the visibility "
                "numbers are placeholders and mean nothing. Only the audits are real." if getattr(args, "sample", False) else
                "Judges are from the same model families as the AI generators (OpenAI, Anthropic); self-preference is possible."),
               f"Winner chosen on judges other than the held-out one ({holdout}); nothing was tuned on these results.",
               "Guardrail is a strict allowlist: harmless paraphrases can be flagged, which disqualifies that part.",
               "Title and tag winners are deterministic audit scores, not measured visibility.",
               "The merchant original is judged against the same Product Truth; the dataset has no merchant tags."]}
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    log(f"wrote {out / 'report.json'} and {out / 'report.md'}")
    return rep


def _ci(v, m="mrr"):
    return f"{v[m]['value']:.3f} [{v[m]['lo']:.3f}, {v[m]['hi']:.3f}]" if v else "n/a"


def to_markdown(rep):
    o, s, L = rep["overall"], rep["setup"], []
    L += [f"# AI comparison: title, tags, description\n\n**{rep['label']}**" + (" **SAMPLE (mock judges).**" if rep["sample"] else ""),
          "", f"{s['products']} products ({', '.join(s['languages'])}); judges {', '.join(s['judges'])} "
          f"(held out: {s['holdout_judge']}); {s['prompts_per_product']} dev/val prompts x {s['repeats']} repeats.", ""]
    for part in PARTS:
        p = o["parts"][part]
        L.append(f"- Best {part}: **{p['winner'] or 'none passed the guardrail'}** (product wins: {p['wins']})")
    if o.get("winner"):
        d = o.get("diff_vs_runner_up")
        L.append(f"- Highest measured visibility (whole candidate, MRR, primary judges): **{o['winner']}**"
                 + (f"; vs {o['runner_up']} {d['value']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}] "
                    f"({'separated' if o['decisive'] else 'not separated; treat as a tie'})" if d else ""))
        if o.get("holdout_judge"):
            h = o["holdout_judge"]
            L.append(f"- Held-out judge {h['judge']}: {h['winner']} ({'agrees' if h['agrees'] else 'disagrees'})")
    else:
        L.append("- No generator passed the guardrail on every product, or nothing was judged.")
    L += ["", "| Generator | Qualified | Flagged | Unsupp. claims | Title score | Tags score | Attr. cov. | "
          "Intent cov. | MRR [95% CI] | Mention [95% CI] |", "|" + "---|" * 10]
    for g, v in rep["generators"].items():
        L.append(f"| {g} | {v['qualified_products']}/{v['candidates']} | {v['flagged']} | {v['unsupported_claims']} | "
                 f"{v['title']['score']} | {v['tags']['score']} | {v['description']['attribute_coverage']} | "
                 f"{v['description']['intent_coverage']} | {_ci(v['visibility'])} | {_ci(v['visibility'], 'mention_rate')} |")
    L += ["", "## Recommended per product (guardrail-passing parts only)", ""]
    for p in rep["products"]:
        r = p["recommended"]
        L.append(f"### {p['brand']} {p['name']} ({p['language']})")
        L.append(f"- Title ({r['title']['from'] if r['title'] else '-'}): {r['title']['text'] if r['title'] else 'none passed'}")
        L.append(f"- Tags ({', '.join(r['tags']['from']) if r['tags'] else '-'}): "
                 f"{', '.join(r['tags']['list']) if r['tags'] else 'none passed'}")
        L.append(f"- Description ({r['description']['from'] if r['description'] else '-'}): "
                 f"{r['description']['text'] if r['description'] else 'none passed'}")
        L.append("")
    L += ["## Caveats", ""] + [f"- {c}" for c in rep["caveats"]]
    L.append(f"\nCost: ${rep['cost']['generation_usd'] + rep['cost']['judge_usd']:.4f} ({rep['cost']['judge_calls']} judge calls).")
    return "\n".join(L) + "\n"
