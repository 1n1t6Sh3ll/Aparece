"""Second offline source: Amazon Reviews 2023 (McAuley Lab) item metadata, Clothing_Shoes_and_Jewelry.

  python dataset/collect/amazon_source.py --target 5000 --per-brand 50

Streams the metadata JSONL over HTTP (the ~18 GB file is never stored), keeps T-shirts only, caps records
per store/brand, maps the original fields into the raw schema, normalizes with normalize.build_normalized,
dedupes by parent_asin, validates, and writes dataset/output/amazon/. License is not declared by the dataset:
every record carries provenance {source: "amazon-reviews-2023", license: "undeclared-research-only"}
(outside the schema; validation runs on the record without the `provenance` key).
"""
import argparse
import copy
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract import SCHEMA_VERSION, hash_id  # noqa: E402
from normalize import build_normalized  # noqa: E402
from run import NOT_SHIRT, NOT_TEE, NORM_V, OUT, RAW_V, TEE, evidence_errors, plain  # noqa: E402

META_URL = ("https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/"
            "raw/meta_categories/meta_Clothing_Shoes_and_Jewelry.jsonl")
AMAZON_OUT = OUT / "amazon"
SOURCE, LICENSE = "amazon-reviews-2023", "undeclared-research-only"
TOP_CATEGORIES = ("Shirts", "Tops, Tees & Blouses", "T-Shirts", "Tops & Tees", "Novelty", "Active Shirts & Tees")
FABRIC_KEYS = ("Fabric Type", "Fabric type", "Material", "Material composition", "Material Type")
CARE_KEYS = ("Care instructions", "Care Instructions")


def text(s):
    s = s.strip() if isinstance(s, str) else None
    return s or None


def is_tee(meta):
    """T-shirt by title; categories, when present, must be a tops/shirts/novelty branch."""
    title = meta.get("title") or ""
    if not TEE.search(title) or NOT_TEE.search(title) or NOT_SHIRT.search(title):
        return False
    cats = meta.get("categories") or []
    return not cats or any(c in TOP_CATEGORIES or "Shirt" in c or "Tee" in c for c in cats)


def build_raw_amazon(meta, scraped_at):
    """Raw schema record from one metadata line; values copied as-is, absent fields null."""
    asin, title = meta["parent_asin"], text(meta.get("title"))
    url = f"https://www.amazon.com/dp/{asin}"
    details = {k: v for k, v in (meta.get("details") or {}).items() if text(str(v))}
    desc = [d for d in (text(d) for d in meta.get("description") or []) if d]
    sections = [{"heading": None, "section_type": "overview", "text": d} for d in desc]
    for keys, kind in ((FABRIC_KEYS, "fabric"), (CARE_KEYS, "care")):
        sections += [{"heading": k, "section_type": kind, "text": str(details[k]).strip()} for k in keys if k in details]
    features = [f for f in (text(f) for f in meta.get("features") or []) if f]
    price = meta.get("price")
    price = None if price in (None, "None", "") else str(price)
    images = [i.get("hi_res") or i.get("large") for i in meta.get("images") or []]
    images = [i for i in images if i and i.startswith("http")]
    cats = [c for c in meta.get("categories") or [] if text(c)]

    def detail(keys):
        return next((str(details[k]).strip() for k in keys if k in details), None)

    return {
        "schema_version": SCHEMA_VERSION, "record_type": "raw", "product_id": hash_id("p_", "amazon:" + asin),
        "source_url": url, "final_url": url, "canonical_url": url,
        "merchant_name": "Amazon", "merchant_domain": "amazon.com", "brand": text(meta.get("store")),
        "scraped_at": scraped_at, "page_language": "en",
        "raw_product_name": title, "raw_title": title, "raw_h1": title, "raw_meta_title": None, "raw_meta_description": None,
        "raw_full_description": "\n".join(desc) or None, "raw_short_description": None,
        "raw_description": {"sections": sections or None,
                            "combined_text": "\n\n".join((s["heading"] + "\n" if s["heading"] else "") + s["text"] for s in sections) or None},
        "raw_bullet_points": features or None,
        "raw_specifications": [{"name": k, "value": str(v)} for k, v in details.items()] or None,
        "raw_material_text": detail(FABRIC_KEYS), "raw_fit_text": None, "raw_size_text": None, "raw_color_text": None,
        "raw_care_text": detail(CARE_KEYS), "raw_features_text": "\n".join(features) or None,
        "raw_shipping_text": None, "raw_return_text": None,
        "raw_price_text": price, "raw_sale_price_text": None, "raw_availability_text": None,
        "raw_rating_text": None if meta.get("average_rating") is None else str(meta["average_rating"]),
        "raw_review_count_text": None if meta.get("rating_number") is None else str(meta["rating_number"]),
        "raw_category_text": " > ".join(cats) or None, "raw_breadcrumbs": cats or None,
        "raw_variants": None, "raw_json_ld": None, "raw_product_schema": None, "raw_offer_schema": None,
        "raw_product_group_schema": None, "raw_variant_schema": None,
        "image_urls": images or None, "image_alt_text": [None] * len(images) if images else None,
        "sku": asin, "gtin": None, "mpn": None,
    }


def normalize_amazon(raw):
    """build_normalized plus parent_asin as the variant group (variants are linked under it on Amazon)."""
    n = build_normalized(raw)
    n["variants"]["product_group_id"] = raw["sku"]
    n["evidence"].append({"field": "variants.product_group_id", "value": raw["sku"], "source_text": raw["sku"],
                          "source_location": "sku", "source_url": raw["final_url"], "method": "direct",
                          "confidence": 1.0, "note": "Amazon parent_asin groups size/colour variants."})
    return n


def errors(raw, norm):
    return [e.message[:120] for e in RAW_V.iter_errors(raw)] + [e.message[:120] for e in NORM_V.iter_errors(norm)] \
        + evidence_errors(raw, norm)


def stream(url):
    import requests
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                yield json.loads(line)


def collect(lines, target, per_brand, scraped_at):
    """(raw, normalized, original) triples; stops at `target` non-reject records."""
    seen, brands, out, kept, scanned = set(), Counter(), [], 0, 0
    for meta in lines:
        scanned += 1
        asin = meta.get("parent_asin")
        if not asin or asin in seen or not is_tee(meta):
            continue
        brand = (text(meta.get("store")) or "").lower()
        if brands[brand] >= per_brand:
            continue
        seen.add(asin)
        raw = build_raw_amazon(meta, scraped_at)
        norm = normalize_amazon(raw)
        if errors(raw, norm):
            continue
        brands[brand] += 1
        out.append((raw, norm, meta))
        kept += norm["quality_status"] != "reject"
        if kept >= target:
            break
    return out, scanned


def clean(norms):
    """Drop rejects, dedupe by parent_asin and brand+name, strip HTML from content."""
    out, seen = [], set()
    for n in map(copy.deepcopy, norms):
        keys = {("asin", n["commerce"]["sku"]),
                ("name", (n["identity"]["brand"] or "").lower(), (n["identity"]["product_name"] or "").lower())}
        if n["quality_status"] == "reject" or keys & seen:
            continue
        seen |= keys
        c = n["content"]
        for k in ("title", "full_description", "short_description", "meta_title", "meta_description", "h1"):
            c[k] = plain(c[k])
        c["bullet_points"] = [b for b in (plain(b) for b in c["bullet_points"]) if b]
        out.append(n)
    return out


def stats(norms, clean_recs, scanned):
    def filled(get):
        return round(sum(1 for n in clean_recs if get(n) not in (None, [], {})) / len(clean_recs), 3) if clean_recs else 0
    return {
        "source": SOURCE, "license": LICENSE, "meta_lines_scanned": scanned,
        "records": len(norms), "clean_records": len(clean_recs),
        "quality": dict(Counter(n["quality_status"] for n in norms)),
        "clean_quality": dict(Counter(n["quality_status"] for n in clean_recs)),
        "brands": len({(n["identity"]["brand"] or "").lower() for n in clean_recs}),
        "top_brands": dict(Counter(n["identity"]["brand"] for n in clean_recs).most_common(10)),
        "fill_rate_clean": {
            "material_percentages": filled(lambda n: n["materials"]["material_percentages"]),
            "primary_material": filled(lambda n: n["materials"]["primary_material"]),
            "fabric_weight_gsm": filled(lambda n: n["materials"]["fabric_weight_gsm"]),
            "fit": filled(lambda n: n["fit_and_style"]["fit"]),
            "sleeve_length": filled(lambda n: n["fit_and_style"]["sleeve_length"]),
            "neckline": filled(lambda n: n["fit_and_style"]["neckline"]),
            "audience": filled(lambda n: n["identity"]["audience"]),
            "product_type": filled(lambda n: n["identity"]["product_type"]),
            "price": filled(lambda n: n["commerce"]["price"]),
            "care": filled(lambda n: n["care"]),
        },
        "primary_material": dict(Counter(n["materials"]["primary_material"] for n in clean_recs).most_common()),
        "quality_flags": dict(Counter(f for n in norms for f in n["quality_flags"]).most_common()),
    }


def write_jsonl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", type=int, default=5000, help="stop after this many non-reject records")
    ap.add_argument("--per-brand", type=int, default=50, help="max records per store/brand")
    ap.add_argument("--url", default=META_URL)
    args = ap.parse_args()
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows, scanned = collect(stream(args.url), args.target, args.per_brand, scraped_at)
    prov = {"source": SOURCE, "license": LICENSE, "dataset_url": META_URL}
    raws = [{**r, "provenance": {**prov, "original": m}} for r, _, m in rows]
    norms = [n for _, n, _ in rows]
    clean_recs = clean(norms)
    AMAZON_OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(AMAZON_OUT / "shirts_raw.jsonl", raws)
    write_jsonl(AMAZON_OUT / "shirts_normalized.jsonl", [{**n, "provenance": prov} for n in norms])
    write_jsonl(AMAZON_OUT / "shirts_clean.jsonl", [{**n, "provenance": prov} for n in clean_recs])
    s = stats(norms, clean_recs, scanned)
    (AMAZON_OUT / "dataset_stats.json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    print(json.dumps({k: s[k] for k in ("meta_lines_scanned", "records", "clean_records", "quality", "brands")}))


if __name__ == "__main__":
    main()
