"""Live AI comparison for one audited product (POST /v1/shootout/live).

Same generators, guardrail and deterministic audit as benchmark/shootout/run.py + report.py, for a single product,
on request. What it does not do: the simulated AI-shopping test (judges ranking pages), which needs competitor pages
and many judge calls; that stays in the committed benchmark run. Paid generators run only when their API key is
set, under a per-request cap (SHOOTOUT_LIVE_MAX_USD, default $0.05) and a per-process daily cap
(SHOOTOUT_LIVE_DAILY_USD, default $1).
"""
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from benchmark.shootout import score
from benchmark.shootout.report import audit, merged, part_winners
from benchmark.shootout.run import Budget, BudgetExceeded, generate, make_adapter
from optimizer import fix
from optimizer.truth import fact_sentences, product_truth

HERE = Path(__file__).resolve().parent
PAID = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
KEYWORDS = "productlens+keywords"  # free: the productlens title/description plus grounded shopper keywords (boost.py)
GENERATORS = ("original", "productlens", KEYWORDS, "productlens@openai:gpt-4o-mini", "openai:gpt-4o-mini",
              "anthropic:claude-haiku-4-5-20251001")
_day = {"date": None, "spent": 0.0}


def _available(spec):
    """Paid generators need their API key; the others always run."""
    if ":" not in spec:
        return True
    prov = spec.split("@", 1)[-1].split(":", 1)[0]
    return prov not in PAID or bool(os.environ.get(PAID[prov]))


def _intents(lang):
    path = HERE.parent / "prompts" / "tshirts.jsonl"
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f if l.strip()]
    return [p for p in rows if p.get("language") == lang and p.get("split") in ("dev", "val")]


def _summary(a):
    t, d, tg = a["title"], a["description"], a["tags"]
    return {"candidates": 1, "qualified_products": int(a["qualified"]), "qualified": a["qualified"],
            "flagged": a["flagged"], "unsupported_claims": a["unsupported_claims"],
            "title": {"score": t["score"] if t else None},
            "tags": {"score": tg["score"], "false": len(tg["false"]), "duplicates": tg["duplicates"]},
            "description": {k: (d or {}).get(k) for k in ("attribute_coverage", "intent_coverage", "readability", "words")},
            "visibility": None}


def _keywords(g, base):
    """The productlens row with grounded keywords added to its title and description (no model, no spend)."""
    from benchmark.shootout.boost import boost  # lazy: boost imports this module
    title, text = boost(g["truth"], g["language"], g["intents"], base["title"], base["text"])
    return {**base, "generator": KEYWORDS, "title": title, "text": text, "cost_usd": 0.0, "calls": 0}


def compare(rec, lang, factory=make_adapter, gens=GENERATORS):
    """Report-shaped result for one product: products=[entry], generators, overall.parts (no visibility test)."""
    lang = lang if lang in ("en", "es") else "en"
    rec = json.loads(json.dumps(rec))  # never mutate the caller's record
    c = rec.setdefault("content", {})
    c["full_description"] = html.unescape(c.get("full_description") or " ".join(c.get("bullet_points") or []) or "").strip()
    truth = product_truth(rec)
    n = len(fact_sentences(truth, lang))
    if n < fix.MIN_FACTS:
        return {"available": False, "reason": "not_enough_facts", "verified_facts": n}
    ident = rec.get("identity") or {}
    pid = rec.get("product_id") or "live"
    g = {"group": "live", "language": lang, "record": rec, "truth": truth, "intents": _intents(lang),
         "target": {"product_id": pid, "identity": {"brand": ident.get("brand"),
                                                     "product_name": ident.get("product_name") or c.get("title")}}}
    today = datetime.now(timezone.utc).date().isoformat()
    if _day["date"] != today:
        _day.update(date=today, spent=0.0)
    daily = float(os.environ.get("SHOOTOUT_LIVE_DAILY_USD") or 1.0)
    cap = min(float(os.environ.get("SHOOTOUT_LIVE_MAX_USD") or 0.05), max(0.0, daily - _day["spent"]))
    budget = Budget(cap, json.loads((HERE.parent / "prices.json").read_text(encoding="utf-8"))["models"])
    args = SimpleNamespace(gen_temperature=0.0, gen_max_tokens=600)
    cands, skipped, rows = {}, [], {}
    for spec in gens:
        if not _available(spec):
            skipped.append(spec)
            continue
        try:
            if spec == KEYWORDS:
                row = _keywords(g, rows.get("productlens") or generate(g, "productlens", args, budget, factory))
            else:
                row = generate(g, spec, args, budget, factory)
            rows[spec] = row
        except BudgetExceeded:
            skipped.append(spec)
            continue
        except Exception as e:  # one provider failing must not sink the comparison
            row = {"title": None, "tags": [], "text": None, "json_ld": None, "error": f"{type(e).__name__}: {e}"[:200],
                   "cost_usd": 0.0}
        a = audit(row, g)
        a.update(raw={k: row.get(k) for k in ("title", "tags", "text", "error")}, visibility=None,
                 cost_usd=round(row.get("cost_usd") or 0, 6))
        cands[spec] = a
    _day["spent"] += budget.spent
    winners = part_winners(cands)
    wins = {p: {"winner": winners[p], "wins": {winners[p]: 1} if winners[p] else {}} for p in ("title", "tags", "description")}
    return {"available": True, "sample": False, "live": True,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "cost": {"judge_calls": 0, "judge_usd": 0.0, "generation_usd": round(budget.spent, 6)},
            "caveats": ["Live comparison: every part is checked for unsupported claims and audited; the simulated "
                        "AI-shopping test runs only in the benchmark, so visibility is not measured here."]
                       + ([f"Skipped (no API key or spend cap reached): {', '.join(skipped)}."] if skipped else []),
            "overall": {"winner": None, "parts": wins},
            "generators": {s: _summary(a) for s, a in cands.items()},
            "products": [{"group": "live", "product_id": pid, "language": lang, "brand": ident.get("brand") or "",
                          "name": g["target"]["identity"]["product_name"] or "", "url": (rec.get("source") or {}).get("url") or "",
                          "verified_facts": n, "candidates": cands, "part_winners": winners,
                          "recommended": merged(cands, winners)}]}
