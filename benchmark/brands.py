"""Which brands do model answers name? Heuristic on the bold item at the start of each recommended line
(**Brand - Product** or **Brand Product**), counted once per answer. Observed outputs, not model internals.

    python -m benchmark.brands --results runs.jsonl --out brands.json
"""
import argparse
import json
import re
from collections import Counter

ITEM = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*\*\*(.+?)\*\*", re.M)
MULTI = ("Under Armour", "The North Face", "Fruit of the Loom", "Marks & Spencer", "New Balance", "Tommy Hilfiger",
         "Calvin Klein", "Ralph Lauren", "Champion Reverse", "American Apparel", "Bella + Canvas", "Bella+Canvas",
         "Los Angeles Apparel", "Next Level", "Comfort Colors", "Lululemon", "Todd Snyder", "Abercrombie & Fitch")
SEP = re.compile(r"\s+[-–—:]\s+|:\s*")


def brand_of(bold):
    bold = bold.strip().strip("*").strip()
    for m in MULTI:
        if bold.lower().startswith(m.lower()):
            return m
    head = SEP.split(bold, 1)[0].strip()
    if head != bold:
        return head
    return bold.split()[0].strip(",.:;") if bold.split() else ""


def named_brands(text):
    return {b for b in (brand_of(x) for x in ITEM.findall(text or "")) if b and not b.isdigit()}


def build(records, top=30):
    count, by_lang, answers = Counter(), {}, Counter()
    for r in records:
        lang = r.get("language") or "?"
        answers[lang] += 1
        for b in named_brands(r.get("response_text")):
            count[b] += 1
            by_lang.setdefault(lang, Counter())[b] += 1
    fmt = lambda c, n: [{"name": k, "answers": v} for k, v in c.most_common(n)]  # noqa: E731
    return {"method": "Brand names in bold at the start of each recommended item (**Brand - Product**), counted "
                      "once per answer. Heuristic; observed outputs, not claims about model internals.",
            "answers": sum(answers.values()), "by_language": dict(answers), "top_named": fmt(count, top),
            "top_named_by_language": {k: fmt(v, 5) for k, v in by_lang.items()}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    with open(a.results, encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(build(recs), f, indent=1, ensure_ascii=False)
