"""Keyword boost: add shared/trending shopper keywords to a title and description, but only the ones the guardrail
accepts as grounded in this product's verified facts. Nothing is invented: every added phrase is checked with
optimizer.guard, and the boosted title/description are re-checked as a whole (a phrase that fails is dropped).

This measures a lexical keyword proxy (score.intent_coverage), not visibility in real AI answers.

CLI (free: POST /v1/audits is a local audit, no model calls):
  python -m benchmark.shootout.boost --report report.json --api http://127.0.0.1:8000 --out boost.json
"""
import argparse
import html
import json
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "api"), str(ROOT / "dataset" / "collect")]

from benchmark.shootout import score  # noqa: E402
from benchmark.shootout.live import _intents  # noqa: E402
from optimizer import fix, guard  # noqa: E402
from optimizer.truth import PHRASES, fact_sentences, product_truth

# Shared keywords (generators, AI answers, 2026 web sources), in priority order: (en, es).
SHARED = [("t-shirt", "camiseta"), ("oversized", "oversize"), ("organic cotton", "algodón orgánico"),
          ("cotton", "algodón"), ("unisex", "unisex"), ("crew neck", "cuello redondo"),
          ("short sleeve", "manga corta"), ("gsm", "g/m²"), ("printed", "estampado")]


def _stems(text):
    return {w[:5] for t in guard._tokens(text) for w in (t, *t.split("-"))}


def _has(text, phrase):
    """True when every word of the phrase is already in the text (5-letter stems, accent-folded)."""
    have = _stems(text)
    return all(w[:5] in have for t in guard._tokens(phrase) if not t[0].isdigit() for w in t.split("-"))


def _grounded(text, truth, title=False):
    check = guard.check_title if title else guard.check_text
    return not any(r["problems"] for r in check(text, truth))


def candidates(truth, lang, prompts):
    """Ordered keyword phrases that are grounded on their own: shared list first, then shoppers' intent words
    that appear in this product's localized fact sentences."""
    rec, vocab = guard.check_record(truth), guard.vocabulary(truth)
    gsm = truth["facts"].get("materials.fabric_weight_gsm")
    out = []
    for en, es in SHARED:
        p = (en, es)[lang == "es"]
        if p in ("gsm", "g/m²"):
            if not isinstance(gsm, (int, float)):
                continue
            p = f"{gsm:g} {p}"
        out.append(p)
    counts = Counter(s for pr in prompts for s in score.intent_keywords(pr["text"]))
    care = PHRASES[lang]["care"].split("{")[0].strip().lower()  # care instructions carry no product keywords
    facts_words = {w for s in fact_sentences(truth, lang) if not s.lower().startswith(care) for w in guard._tokens(s)
                   if not w[0].isdigit() and w not in guard.NEUTRAL and w not in score.INTENT_STOP and len(w) >= 4}
    out += sorted((w for w in facts_words if w[:5] in counts), key=lambda w: (-counts[w[:5]], w))
    ok = []
    for p in dict.fromkeys(out):
        _, problems = guard.check_sentence(p, truth, rec, vocab)
        if not problems:
            ok.append(p)
    return ok


def _sentence(lead, kind, phrases):
    return f"{lead[0]} {kind}" + (f" {lead[1]} {', '.join(phrases)}" if phrases else "") + "."


def boost(truth, lang, prompts, title, description):
    """(title, description) with grounded keywords added. Never returns text that fails the guard."""
    cands = candidates(truth, lang, prompts)
    title, desc = (title or "").strip(), (description or "").strip()
    new, added = title, []
    for p in cands:
        if _has(new, p):
            continue
        trial = f"{title} {'-' if ' - ' not in title else ','} {', '.join(added + [p])}".replace(" ,", ",")
        if len(trial) <= score.TITLE_RANGE[1] and _grounded(trial, truth, title=True):
            new, added = trial, added + [p]
    lead = {"en": ("This is a", "with"), "es": ("Esta es una", "con")}[lang]
    kind = SHARED[0][lang == "es"]  # "t-shirt" opens the sentence: "This is a t-shirt with crew neck, cotton."
    added = []
    for p in (p for p in cands if not _has(desc, p) and p != kind):
        if _grounded(_sentence(lead, kind, added + [p]), truth):
            added.append(p)
    if added or not _has(desc, kind):  # only when it adds a keyword
        trial = f"{desc} {_sentence(lead, kind, added)}".strip()
        desc = trial if _grounded(trial, truth) else desc
    return new, desc


# ---------- measurement ----------
def measure(title, desc, truth, lang, prompts):
    t, d = score.title_audit(title, truth, lang), score.description_audit(desc, truth, lang, prompts)
    return {"guard_pass": bool(t["passes"] and d["passes"]), "title_score": t["score"], "title_chars": t["chars"],
            "attribute_coverage": d["attribute_coverage"], "intent_coverage": d["intent_coverage"],
            "words": d["words"], "intent_coverage_title_plus_desc": score.intent_coverage(f"{title}. {desc}", prompts)}


def _post(api, url, lang):
    req = urllib.request.Request(api.rstrip("/") + "/v1/audits", json.dumps({"url": url, "language": lang}).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["record"]


def compare_record(rec, lang):
    rec = json.loads(json.dumps(rec))
    c = rec.setdefault("content", {})
    c["full_description"] = html.unescape(c.get("full_description") or " ".join(c.get("bullet_points") or []) or "").strip()
    truth, prompts = product_truth(rec), _intents(lang)
    out = fix.generate(rec, lang, None, backend="stub")
    bt, bd = boost(truth, lang, prompts, out["title"], out["description"])
    return {"before": {"title": out["title"], "description": out["description"],
                       **measure(out["title"], out["description"], truth, lang, prompts)},
            "after": {"title": bt, "description": bd, **measure(bt, bd, truth, lang, prompts)}}


METRICS = ("guard_pass", "title_score", "attribute_coverage", "intent_coverage", "intent_coverage_title_plus_desc", "words")


def run(report_path, api, sleep=1.5, log=print):
    with open(report_path, encoding="utf-8") as f:
        items = [i for i in json.load(f)["items"] if not i.get("error") and i.get("url")]
    rows = []
    for i in items:
        try:
            rows.append({"url": i["url"], "language": i["language"], **compare_record(_post(api, i["url"], i["language"]), i["language"])})
        except Exception as e:  # skip failures, keep going
            log(f"skip {i['url']}: {type(e).__name__}: {str(e)[:100]}")
        time.sleep(sleep)
    mean = lambda side, m: round(sum(float(r[side][m] or 0) for r in rows) / len(rows), 4) if rows else None  # noqa: E731
    return {"n": len(rows), "skipped": len(items) - len(rows), "rows": rows,
            "average": {side: {m: mean(side, m) for m in METRICS} for side in ("before", "after")}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    res = run(a.report, a.api)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"products: {res['n']} (skipped {res['skipped']})")
    print(f"{'metric':34}{'before':>9}{'after':>9}")
    for m in METRICS:
        print(f"{m:34}{res['average']['before'][m]:>9}{res['average']['after'][m]:>9}")


if __name__ == "__main__":
    main()
