"""Merge WDC/Amazon/Shopify clean records into evidence-backed ground truth splits.

python dataset/build/make_ground_truth.py \
    --input wdc=dataset/output --input amazon=dataset/output/amazon --input shopify=dataset/output/shopify

Each input dir holds shirts_clean.jsonl + shirts_raw.jsonl. Outputs go to dataset/output/final/.
"""
import argparse
import collections
import csv
import json
import random
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "train"))
from common import FIELDS, get, messages, target  # noqa: E402

SPLITS = ("train", "val", "test")
FRACS = {"train": 0.8, "val": 0.1, "test": 0.1}
QUALITY_RANK = {"high": 3, "medium": 2, "low": 1}
RAW_KEEP = ["product_id", "source_url", "canonical_url", "merchant_domain", "brand", "sku", "gtin", "mpn",
            "raw_title", "raw_product_name", "raw_category_text", "raw_full_description",
            "raw_short_description", "raw_bullet_points", "raw_specifications", "raw_material_text",
            "raw_fit_text", "raw_color_text", "raw_size_text", "raw_care_text", "raw_features_text",
            "provenance"]


# Final guard against obvious non-shirts that slipped through ("Tee" = tea in German/Finnish, etc.).
STRONG_SHIRT = re.compile(r"(?<!sweat)shirt|\bpolo\b|henley|blouse|camiseta", re.I)
HARD_REJECT = re.compile(r"\b\d+([.,]\d+)?\s?(g|kg|ml|l|gram|grams)\b(?!/)|\bsweatshirts?\b|\bhoodies?\b", re.I)
NON_APPAREL = re.compile(
    r"\b(candles?|mugs?|teas?|matcha|chai|mate|coffee|lunch ?box(es)?|bottles?|tumblers?|posters?|stickers?|"
    r"magnets?|keychains?|pillows?|blankets?|tote|backpacks?|puzzles?|ornaments?|jackets?|coats?|socks|shorts|"
    r"pants|trousers|jeans|leggings|dress(es)?|skirts?|caps?|hats?|beanies?|shoes|sneakers)\b", re.I)
APPAREL_CUE = re.compile(r"sleeve|\bfit(ted)?\b|relaxed|oversized?|youth|boyfriend|unisex|\bmen'?s\b|women'?s|"
                         r"ladies|\bkids\b|\btalla\b|\bsize\b|\btee\s*$|\btee\s+[-(]", re.I)


def non_apparel(raw):
    """True if the title names a non-shirt item (tea, candle, trousers...). Hard shirt words override."""
    title = " ".join(filter(None, [raw.get("raw_title"), raw.get("raw_product_name")]))
    if STRONG_SHIRT.search(title):
        return False
    if HARD_REJECT.search(title):
        return True
    return bool(NON_APPAREL.search(title)) and not APPAREL_CUE.search(title)


EN_WORDS = {"the", "and", "with", "for", "of", "this", "is", "our", "made", "cotton", "shirt", "fit", "wash"}
ES_WORDS = {"el", "la", "los", "las", "de", "del", "con", "para", "y", "es", "una", "algodón", "camiseta", "talla"}


def language_of(norm, raw):
    """en / es / other: the declared page language if set, else a stopword vote over the raw text."""
    lang = (norm["source"].get("language") or raw.get("page_language") or "").lower()
    if not lang:
        words = re.findall(r"\w+", " ".join(str(raw.get(k) or "") for k in (
            "raw_title", "raw_product_name", "raw_full_description", "raw_bullet_points")).lower())
        en, es = sum(w in EN_WORDS for w in words), sum(w in ES_WORDS for w in words)
        lang = "es" if es > en and es >= 2 else "en" if en >= 2 else "other"
    return lang[:2] if lang[:2] in ("en", "es") else "other"


def read_jsonl(path, bad):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:  # e.g. a half-written last line
                    bad[str(path)] += 1
    return rows


def resolve(raw, loc):
    """Follow a path like raw_description.sections[1].text into the raw record."""
    cur = raw
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", loc):
        if tok.startswith("["):
            i = int(tok[1:-1])
            cur = cur[i] if isinstance(cur, list) and i < len(cur) else None
        else:
            cur = cur.get(tok) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _norm(s):
    return " ".join(str(s).split()).casefold()


def _text(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def evidence_ok(raw, ev):
    """source_text must occur in the raw field it names (or anywhere in raw if the path is unresolvable)."""
    needle = _norm(ev.get("source_text") or "")
    if not needle:
        return False
    hay = resolve(raw, ev.get("source_location") or "")
    if hay is None:
        hay = raw
    return needle in _norm(_text(hay))


def base_field(path):
    return re.sub(r"\[\d+\]$", "", path)


def verify(norm, raw, drops):
    """Keep only target fields whose every evidence item verifies against raw; return filtered copy."""
    by_field = collections.defaultdict(list)
    for ev in norm.get("evidence", []):
        by_field[base_field(ev["field"])].append(ev)
    kept = []
    for f, evs in by_field.items():
        if f in FIELDS and not all(evidence_ok(raw, e) for e in evs):
            if get(norm, f) not in (None, [], {}):
                drops[f] += 1
            continue
        kept.extend(evs)
    return dict(norm, evidence=kept)


def canon_url(u):
    if not u:
        return None
    p = urlsplit(u.strip().lower())
    return (p.netloc.removeprefix("www.") + p.path.rstrip("/")) or None


def norm_words(s):
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def dedupe_keys(n):
    c, ident = n.get("commerce") or {}, n["identity"]
    brand = norm_words(ident.get("brand"))
    keys = [("url", canon_url(n["source"].get("canonical_url") or n["source"]["url"]))]
    if c.get("gtin"):
        keys.append(("gtin", re.sub(r"\D", "", str(c["gtin"])).lstrip("0") or None))
    if c.get("sku") and len(str(c["sku"])) >= 5:  # short SKUs collide across stores; scope by brand
        keys.append(("sku", f"{brand}|{str(c['sku']).strip().lower()}"))
    name = norm_words(ident.get("product_name"))
    if brand and name:
        keys.append(("brand_name", f"{brand}|{name}"))
    return [(k, v) for k, v in keys if v]


def dedupe(items):
    """Union-find over shared keys; keep the best record per cluster."""
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    seen, why = {}, {}
    for i, it in enumerate(items):
        for key in dedupe_keys(it["norm"]):
            if key in seen:
                a, b = find(i), find(seen[key])
                if a != b:
                    parent[a] = b
                    why.setdefault(i, key[0])
            else:
                seen[key] = i
    clusters = collections.defaultdict(list)
    for i in range(len(items)):
        clusters[find(i)].append(i)
    kept, removed = [], collections.Counter()
    for members in clusters.values():
        best = max(members, key=lambda i: (QUALITY_RANK.get(items[i]["norm"]["quality_status"], 0),
                                           sum(v is not None for v in items[i]["gold"].values()),
                                           items[i]["norm"]["product_id"]))
        kept.append(items[best])
        for i in members:
            if i != best:
                removed[f"{items[i]['source']}:{why.get(i, 'cluster')}"] += 1
    kept.sort(key=lambda it: it["norm"]["product_id"])
    return kept, removed


def group_of(source, norm):
    if source == "amazon":
        return "brand:" + (norm_words(norm["identity"].get("brand")) or "unknown")
    return "domain:" + norm["source"]["merchant_domain"]


def assign_splits(items, seed):
    """Group-level split, stratified by (source, dominant product type, dominant language of the group)."""
    groups = collections.defaultdict(list)
    for it in items:
        groups[it["group"]].append(it)
    strata = collections.defaultdict(list)
    for g, its in groups.items():
        ptype = collections.Counter(str(it["gold"]["identity.product_type"]) for it in its).most_common(1)[0][0]
        lang = collections.Counter(it["language"] for it in its).most_common(1)[0][0]
        strata[(its[0]["source"], ptype, lang)].append(g)
    rng = random.Random(seed)
    split_of = {}
    for key in sorted(strata):
        gs = sorted(strata[key])
        rng.shuffle(gs)
        total = sum(len(groups[g]) for g in gs)
        have = dict.fromkeys(SPLITS, 0)
        for g in gs:  # greedy: give the group to the split furthest below its target
            s = max(SPLITS, key=lambda s: (FRACS[s] * total - have[s]) / FRACS[s])
            split_of[g] = s
            have[s] += len(groups[g])
    for it in items:
        it["split"] = split_of[it["group"]]
    return split_of


def pick_review(test, n, seed):
    """Round-robin over (source, product type, language) strata, preferring records with more gold fields."""
    rng = random.Random(seed)
    strata = collections.defaultdict(list)
    for it in test:
        strata[(it["source"], str(it["gold"]["identity.product_type"]), it["language"])].append(it)
    for k in strata:
        rng.shuffle(strata[k])
        strata[k].sort(key=lambda it: -sum(v is not None for v in it["gold"].values()))
    out, keys = [], sorted(strata)
    while len(out) < n and any(strata.values()):
        for k in keys:
            if strata[k] and len(out) < n:
                out.append(strata[k].pop(0))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", action="append", metavar="SOURCE=DIR",
                    help="repeatable; default wdc=dataset/output amazon=dataset/output/amazon "
                         "shopify=dataset/output/shopify")
    ap.add_argument("--out", default=str(ROOT / "dataset" / "output" / "final"))
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--review", type=int, default=200)
    args = ap.parse_args(argv)
    inputs = dict(x.split("=", 1) for x in (args.input or [
        "wdc=dataset/output", "amazon=dataset/output/amazon", "shopify=dataset/output/shopify"]))

    schema = json.loads((ROOT / "dataset" / "schema" / "normalized_record.schema.json").read_text("utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    st = {"input": {}, "dropped": collections.Counter(), "bad_lines": collections.Counter()}
    ev_drops = collections.Counter()
    items, seen_ids = [], set()
    for source, d in sorted(inputs.items()):
        d = Path(d) if Path(d).is_absolute() else ROOT / d
        norms = read_jsonl(d / "shirts_clean.jsonl", st["bad_lines"])
        raws = read_jsonl(d / "shirts_raw.jsonl", st["bad_lines"])
        raw_by_id = {r["product_id"]: r for r in raws}
        st["input"][source] = {"dir": str(d), "clean": len(norms), "raw_unique": len(raw_by_id)}
        for n in norms:
            pid = n.get("product_id")
            if pid in seen_ids:
                st["dropped"][f"{source}:duplicate_product_id"] += 1
                continue
            extra_prov = n.pop("provenance", None)  # amazon adds this; not in the schema, kept in our row
            if n.get("quality_status") == "reject":
                st["dropped"][f"{source}:reject"] += 1
                continue
            if next(validator.iter_errors(n), None) is not None:
                st["dropped"][f"{source}:schema_invalid"] += 1
                continue
            raw = raw_by_id.get(pid)
            if raw is None:
                st["dropped"][f"{source}:no_raw"] += 1
                continue
            if non_apparel(raw):
                st["dropped"][f"{source}:non_apparel_title"] += 1
                continue
            seen_ids.add(pid)
            vn = verify(n, raw, ev_drops)
            items.append({"source": source, "norm": vn, "raw": raw, "gold": target(vn),
                          "language": language_of(n, raw), "extra_provenance": extra_prov})

    items, removed = dedupe(items)
    for it in items:
        it["group"] = group_of(it["source"], it["norm"])
    assign_splits(items, args.seed)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    names = {"train": "train.jsonl", "val": "val.jsonl", "test": "test_gold.jsonl"}
    by_split = {s: [it for it in items if it["split"] == s] for s in SPLITS}
    for s, its in by_split.items():
        with open(out / names[s], "w", encoding="utf-8") as f:
            for it in its:
                n, raw = it["norm"], it["raw"]
                row = {"product_id": n["product_id"], "source": it["source"], "group": it["group"],
                       "split": s, "language": it["language"], "domain": n["source"]["merchant_domain"],
                       "provenance": {"url": n["source"]["url"], "scraped_at": n["source"]["scraped_at"],
                                      "quality_status": n["quality_status"], "raw": raw.get("provenance"),
                                      "normalized": it["extra_provenance"]},
                       "gold": it["gold"],
                       "evidence": [e for e in n["evidence"] if base_field(e["field"]) in FIELDS],
                       "raw": {k: raw.get(k) for k in RAW_KEEP},
                       "messages": messages(raw, n)}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    review = pick_review(by_split["test"], args.review, args.seed)
    with open(out / "human_review.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "source", "language", "domain", "url", "raw_title", "raw_description"]
                   + [c for fld in FIELDS for c in (f"gold:{fld}", f"correct:{fld}")] + ["reviewer_notes"])
        for it in review:
            raw, g = it["raw"], it["gold"]
            desc = raw.get("raw_full_description") or (raw.get("raw_description") or {}).get("combined_text") \
                or "\n".join(raw.get("raw_bullet_points") or [])
            w.writerow([it["norm"]["product_id"], it["source"], it["language"], it["norm"]["source"]["merchant_domain"],
                        it["norm"]["source"]["url"], raw.get("raw_title") or raw.get("raw_product_name"),
                        (desc or "")[:2000]]
                       + [c for fld in FIELDS for c in ("" if g[fld] is None else _text(g[fld]), "")] + [""])

    def summary(its):
        c = len(its) or 1
        return {"records": len(its), "groups": len({it["group"] for it in its}),
                "by_source": dict(collections.Counter(it["source"] for it in its)),
                "by_language": dict(collections.Counter(it["language"] for it in its)),
                "by_product_type": dict(collections.Counter(str(it["gold"]["identity.product_type"]) for it in its)),
                "material_coverage": round(sum(it["gold"]["materials.primary_material"] is not None
                                               for it in its) / c, 4),
                "field_coverage": {f: round(sum(it["gold"][f] is not None for it in its) / c, 4) for f in FIELDS}}

    stats = {"seed": args.seed, "input": st["input"], "bad_lines": dict(st["bad_lines"]),
             "dropped": dict(st["dropped"]), "dupes_removed": dict(removed),
             "dupes_removed_total": sum(removed.values()),
             "evidence_check_drops": dict(ev_drops), "evidence_check_drops_total": sum(ev_drops.values()),
             "total": summary(items), "splits": {s: summary(by_split[s]) for s in SPLITS},
             "by_source_split": {src: {s: sum(it["source"] == src for it in by_split[s]) for s in SPLITS}
                                 for src in sorted(inputs)},
             "human_review_rows": len(review),
             "human_review_by_source": dict(collections.Counter(it["source"] for it in review))}
    (out / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({"splits": {s: len(v) for s, v in by_split.items()}, "dupes_removed": sum(removed.values()),
                      "evidence_check_drops": sum(ev_drops.values()), "dropped": dict(st["dropped"])}))
    return stats


if __name__ == "__main__":
    main()
