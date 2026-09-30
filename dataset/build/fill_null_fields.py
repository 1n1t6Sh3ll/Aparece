"""TEAM-37: fill the 7 always-null fields on a small subset with deterministic, evidence-backed rules.

python dataset/build/fill_null_fields.py --final <dir with train.jsonl + test_gold.jsonl> \
    --eval-ids train/runs/team20/eval_subset_ids.txt --out dataset/output/final_v2_2k

Train: stratified sample (language x source, seed 42). Test: the given eval ids (else stratified sample).
Rules (dataset/collect/normalize.extra_fields) search the html-unescaped title, name, description,
bullets and care/size text. Only null gold fields are filled; each fill adds evidence whose
source_text is an exact substring of the (unescaped) raw field named by source_location.
"""
import argparse
import collections
import html
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "dataset" / "collect"))
sys.path.insert(0, str(ROOT / "train"))
from common import FIELDS, messages  # noqa: E402
from normalize import extra_fields  # noqa: E402

NEW_FIELDS = ["materials.fabric_type", "materials.texture", "fit_and_style.shirt_length", "fit_and_style.style",
              "care", "variants.sizes", "fit_and_style.collar_type"]
TEXT_KEYS = ["raw_title", "raw_product_name", "raw_full_description", "raw_short_description",
             "raw_bullet_points", "raw_care_text", "raw_size_text", "raw_features_text"]


def clean_text(t):
    """html-unescape (twice, for double-encoded pages) and collapse whitespace, keeping line breaks."""
    t = html.unescape(html.unescape(t)).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    return re.sub(r" ?\n[\s]*", "\n", t).strip()


def clean_raw(raw):
    """Copy of raw with every prompt/text string cleaned; the stored raw stays untouched."""
    def walk(v):
        if isinstance(v, str):
            return clean_text(v)
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v
    return {k: (walk(v) if k.startswith("raw_") else v) for k, v in raw.items()}


def sources(raw):
    """(source_location, cleaned text) pairs; raw must already be cleaned."""
    out = []
    for key in TEXT_KEYS:
        v = raw.get(key)
        items = [(f"{key}[{i}]", b) for i, b in enumerate(v)] if isinstance(v, list) else [(key, v)]
        out += [(loc, t) for loc, t in items if isinstance(t, str) and t.strip()]
    return out


def apply(rec):
    """Fill null NEW_FIELDS in place; returns the list of filled fields."""
    clean = clean_raw(rec["raw"])
    values, evs = extra_fields(sources(clean))
    url = rec["raw"].get("source_url")
    filled = [f for f in NEW_FIELDS if f in values and rec["gold"].get(f) is None]
    for f, v, text, loc in evs:
        if f in filled:
            rec["evidence"].append({"field": f, "value": v, "source_text": text, "source_location": loc,
                                    "source_url": url, "method": "rule", "confidence": 0.8,
                                    "note": "TEAM-37 rule; source_text is verbatim in the html-unescaped, whitespace-normalized field"})
    for f in filled:
        rec["gold"][f] = values[f]
    # Prompt rebuilt from the cleaned text so the model sees exactly what the evidence quotes.
    rec["messages"] = messages(clean) + [{"role": "assistant", "content": json.dumps(
        {f: rec["gold"][f] for f in FIELDS}, ensure_ascii=False)}]
    return filled


def stratified(rows, n, seed):
    rng = random.Random(seed)
    strata = collections.defaultdict(list)
    for r in rows:
        strata[(r["language"], r["source"])].append(r)
    keys = sorted(strata)
    quota = {k: n * len(strata[k]) / len(rows) for k in keys}
    take = {k: int(quota[k]) for k in keys}
    for k in sorted(keys, key=lambda k: -(quota[k] - take[k]))[:n - sum(take.values())]:
        take[k] += 1
    out = []
    for k in keys:
        out += rng.sample(strata[k], min(take[k], len(strata[k])))
    return out


def coverage(rows, gold_key="gold"):
    return {f: round(sum(r[gold_key][f] is not None for r in rows) / len(rows), 4) for f in FIELDS}


def read(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eval-ids")
    ap.add_argument("--n-train", type=int, default=2000)
    ap.add_argument("--n-test", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train-ids", help="jsonl whose product_ids fix the train subset (e.g. a previous train.jsonl)")
    a = ap.parse_args(argv)
    final, out = Path(a.final), Path(a.out)
    assert final.resolve() != out.resolve(), "refusing to overwrite the input dir"
    train = stratified(read(final / "train.jsonl"), a.n_train, a.seed)
    if a.train_ids:  # reuse an earlier subset's ids, in its order
        ids = [json.loads(line)["product_id"] for line in open(a.train_ids, encoding="utf-8") if line.strip()]
        by_id = {r["product_id"]: r for r in read(final / "train.jsonl")}
        train = [by_id[i] for i in ids]
    test_all = read(final / "test_gold.jsonl")
    if a.eval_ids:
        ids = [x.strip() for x in open(a.eval_ids, encoding="utf-8") if x.strip()]
        by_id = {r["product_id"]: r for r in test_all}
        missing = [i for i in ids if i not in by_id]
        assert not missing, f"{len(missing)} eval ids missing from test_gold"
        test = [by_id[i] for i in ids]
    else:
        test = stratified(test_all, a.n_test, a.seed)
    stats = {"seed": a.seed, "input": str(final), "eval_ids": a.eval_ids, "new_fields": NEW_FIELDS}
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("test_gold", test)):
        before = coverage(rows)
        filled = collections.Counter(f for r in rows for f in apply(r))
        with open(out / f"{name}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        stats[name] = {"count": len(rows),
                       "by_language_source": dict(collections.Counter(f"{r['language']}/{r['source']}" for r in rows)),
                       "coverage_before": before, "coverage_after": coverage(rows), "filled": dict(filled)}
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("train", "test_gold")}, indent=1))


if __name__ == "__main__":
    main()
