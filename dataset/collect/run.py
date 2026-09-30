"""Shirt collector CLI.

  python dataset/collect/run.py collect --max-products 20 --per-store 4    # resumable; appends
  python dataset/collect/run.py clean                                      # -> shirts_clean.jsonl
  python dataset/collect/run.py report                                     # validation CSV + stats

`collect` also runs `report` and `clean` at the end. Records already in shirts_raw.jsonl are skipped,
so rerunning continues where it stopped. Use --fresh to start over.
"""
import argparse
import csv
import json
import re
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bs4 import BeautifulSoup  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402

from extract import build_raw, canonical_key, hash_id  # noqa: E402
from fetch import Blocked, Fetcher  # noqa: E402
from normalize import build_normalized, decoded_text  # noqa: E402

DATASET = HERE.parent
OUT = DATASET / "output"
RAW_FILE, NORM_FILE = OUT / "shirts_raw.jsonl", OUT / "shirts_normalized.jsonl"
SHIRT = re.compile(r"\b(shirts?|t-?shirts?|tees?|polos?|henleys?|camisas?|camisetas?|sobrecamisas?|guayaberas?|overshirts?)\b", re.I)
NOT_SHIRT = re.compile(r"\b(sweat ?shirts?|jackets?|chaquetas?|hoodies?|sudaderas?|packs?|\d-pack|dress(es)?|vestidos?|gift|"
                       r"cardigans?|trunks|boxers?|briefs|pants|pantalones|shorts|bras?|jerseys?|socks|calcetines|bundle|"
                       r"blouses?|blusas?|bodys?|babygrow|onesie|pullovers?|sweaters?|jumpers?)\b", re.I)
TEE = re.compile(r"\b(t-?shirts?|tees?|camisetas?)\b", re.I)
NOT_TEE = re.compile(r"\b(polos?|camisas?|button[- ]?(down|up)|henleys?)\b", re.I)


def validator(name):
    schema = json.loads((DATASET / "schema" / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


RAW_V, NORM_V = validator("raw_record.schema.json"), validator("normalized_record.schema.json")


def is_shirt(p, tees_only=False):
    """Shirt filter on product_type + title; tags only when both are empty of a signal."""
    text = f"{p.get('title', '')} | {p.get('product_type', '')}"
    if NOT_SHIRT.search(text):
        return False
    if tees_only:
        return bool(TEE.search(text)) and not NOT_TEE.search(p.get("title", ""))
    if SHIRT.search(text):
        return True
    tags = p.get("tags") or []
    tags = tags if isinstance(tags, list) else str(tags).split(",")
    return bool(SHIRT.search(" ".join(tags))) and not NOT_SHIRT.search(" ".join(tags))


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").split("\n") if ln.strip()]  # not splitlines(): U+2028 etc. occur inside values


def load_stores(domains=None):
    with open(HERE / "stores.csv", newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["use"].strip().lower() == "yes"]
    return [r for r in rows if not domains or r["domain"] in domains]


def shirt_candidates(fetcher, store, want, tees_only):
    """Page through /products.json (250 per page) until `want` shirt candidates are found."""
    found, page = [], 1
    while len(found) < want:
        _, text = fetcher.get(f"https://{store['domain']}/products.json?limit=250&page={page}")
        products = json.loads(text).get("products", [])
        if not products:
            break
        found += [p for p in products if is_shirt(p, tees_only)]
        page += 1
    return found


def collect(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        for f in (RAW_FILE, NORM_FILE):
            f.unlink(missing_ok=True)
    existing = read_jsonl(RAW_FILE)
    seen_ids = {r["product_id"] for r in existing}
    seen_urls = {r["source_url"] for r in existing}
    seen_skus = {(r["merchant_domain"], v["sku"]) for r in existing for v in r["raw_variants"] or [] if v["sku"]}
    state = {"total": len(existing), "per_store": Counter(r["merchant_domain"] for r in existing)}
    lock = threading.Lock()

    def full():
        return state["total"] >= args.max_products

    def collect_store(store, fr, fn):
        """One thread per store; each host still gets at most 1 request/second."""
        dom, fetcher = store["domain"], Fetcher(use_cache=not args.no_cache)
        try:
            candidates = shirt_candidates(fetcher, store, args.per_store * 2 + state["per_store"][dom], args.types == "tees")
        except (Blocked, ValueError, OSError) as e:
            print(f"[skip store] {dom}: {e}", flush=True)
            return
        for p in candidates:
            if state["per_store"][dom] >= args.per_store or full():
                break
            url = f"https://{dom}/products/{p['handle']}"
            skus = {(dom, v["sku"]) for v in p.get("variants", []) if v.get("sku")}
            if url in seen_urls or skus & seen_skus:
                continue
            try:
                final_url, html = fetcher.get(url)
                scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                raw = build_raw(p, html, url, final_url, store, scraped_at)
                norm = build_normalized(raw)
            except Exception as e:  # one bad page must not stop a long run
                print(f"[skip] {url}: {type(e).__name__}: {e}", flush=True)
                continue
            with lock:
                if raw["product_id"] in seen_ids or full():  # same canonical URL
                    continue
                fr.write(json.dumps(raw, ensure_ascii=False) + "\n")
                fn.write(json.dumps(norm, ensure_ascii=False) + "\n")
                fr.flush(), fn.flush()
                seen_ids.add(raw["product_id"]), seen_urls.add(url)
                seen_skus.update(skus)
                state["per_store"][dom] += 1
                state["total"] += 1
                print(f"[ok] {state['total']} {norm['quality_status']:6} {url}", flush=True)

    with open(RAW_FILE, "a", encoding="utf-8") as fr, open(NORM_FILE, "a", encoding="utf-8") as fn:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for f in [pool.submit(collect_store, s, fr, fn) for s in load_stores(args.stores)]:
                f.result()
    report(args)
    clean(args)


def resolve(record, path):
    node = record
    for key, index in re.findall(r"([^.\[\]]+)|\[(\d+)\]", path):
        node = node[key] if key else node[int(index)]
    return node


def evidence_errors(raw, norm):
    text = decoded_text(raw)  # evidence quotes entity-decoded text
    bad = []
    for e in norm["evidence"]:
        try:
            target = resolve(text, e["source_location"])
        except (KeyError, IndexError, TypeError):
            bad.append(f"{e['field']}: bad location {e['source_location']}")
            continue
        hay = target if isinstance(target, str) else json.dumps(target, ensure_ascii=False)
        if e["source_text"] not in hay:
            bad.append(f"{e['field']}: text not found at {e['source_location']}")
    return bad


def report(args):
    raws = {r["product_id"]: r for r in read_jsonl(RAW_FILE)}
    norms = read_jsonl(NORM_FILE)
    rows = []
    for n in norms:
        r = raws.get(n["product_id"])
        raw_err = [e.message[:120] for e in RAW_V.iter_errors(r)] if r else ["raw record missing"]
        norm_err = [e.message[:120] for e in NORM_V.iter_errors(n)]
        ev_err = evidence_errors(r, n) if r else []
        rows.append({"product_id": n["product_id"], "merchant_domain": n["source"]["merchant_domain"], "url": n["source"]["url"],
                     "raw_valid": not raw_err, "normalized_valid": not norm_err, "evidence_valid": not ev_err,
                     "quality_status": n["quality_status"], "quality_flags": ";".join(n["quality_flags"]),
                     "errors": " | ".join(raw_err + norm_err + ev_err)})
    with open(OUT / "shirts_validation_report.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["product_id"])
        w.writeheader()
        w.writerows(rows)

    def filled(get):
        return round(sum(1 for n in norms if get(n) not in (None, [], {})) / len(norms), 3) if norms else 0

    stats = {
        "records": len(norms),
        "domains": len({n["source"]["merchant_domain"] for n in norms}),
        "by_store": dict(Counter(n["source"]["merchant_domain"] for n in norms).most_common()),
        "by_tld": dict(Counter(n["source"]["merchant_domain"].rsplit(".", 1)[-1] for n in norms).most_common()),
        "by_language": dict(Counter(str(n["source"]["language"]) for n in norms).most_common()),
        "by_product_type": dict(Counter(str(n["identity"]["product_type"]) for n in norms).most_common()),
        "by_primary_material": dict(Counter(str(n["materials"]["primary_material"]) for n in norms).most_common()),
        "by_fit": dict(Counter(str(n["fit_and_style"]["fit"]) for n in norms).most_common()),
        "quality": dict(Counter(n["quality_status"] for n in norms)),
        "rejects": sum(n["quality_status"] == "reject" for n in norms),
        "all_valid": all(r["raw_valid"] and r["normalized_valid"] and r["evidence_valid"] for r in rows),
        "invalid_records": sum(1 for r in rows if not (r["raw_valid"] and r["normalized_valid"] and r["evidence_valid"])),
        "records_with_conflicts": sum(1 for n in norms if n["conflicts"]),
        "fill_rate": {
            "product_type": filled(lambda n: n["identity"]["product_type"]),
            "audience": filled(lambda n: n["identity"]["audience"]),
            "material_percentages": filled(lambda n: n["materials"]["material_percentages"]),
            "fabric_weight_gsm": filled(lambda n: n["materials"]["fabric_weight_gsm"]),
            "fit": filled(lambda n: n["fit_and_style"]["fit"]),
            "sleeve_length": filled(lambda n: n["fit_and_style"]["sleeve_length"]),
            "neckline": filled(lambda n: n["fit_and_style"]["neckline"]),
            "colors": filled(lambda n: n["variants"]["colors"]),
            "sizes": filled(lambda n: n["variants"]["sizes"]),
            "price": filled(lambda n: n["commerce"]["price"]),
            "currency": filled(lambda n: n["commerce"]["currency"]),
            "care": filled(lambda n: n["care"]),
        },
        "quality_flags": dict(Counter(f for n in norms for f in n["quality_flags"]).most_common()),
    }
    stats["missing_rate"] = {k: round(1 - v, 3) for k, v in stats["fill_rate"].items()}
    (OUT / "dataset_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("records", "by_store", "quality", "all_valid", "invalid_records")}))


def plain(text):
    """Strip any HTML left in a text value (normalized content only; raw is never touched)."""
    if not isinstance(text, str) or "<" not in text:
        return text
    return re.sub(r"[ \t]+", " ", BeautifulSoup(text, "html.parser").get_text("\n")).strip() or None


def clean(args):
    """Drop reject records, dedupe (product_id, SKU/GTIN, brand+name), strip HTML in content.
    Dropped duplicates are linked to the kept record in dataset_stats.json ("duplicates")."""
    out, seen, dupes = [], {}, []
    for n in read_jsonl(NORM_FILE):
        if n["quality_status"] == "reject":
            continue
        dom = n["source"]["merchant_domain"]
        keys = {("id", n["product_id"]), ("name", dom, (n["identity"]["brand"] or "").lower(), (n["identity"]["product_name"] or "").lower())}
        keys |= {("sku", dom, i["sku"]) for i in n["variants"]["items"] if i["sku"]}
        keys |= {("sku", dom, n["commerce"]["sku"])} if n["commerce"]["sku"] else set()
        keys |= {("gtin", g) for g in [n["commerce"]["gtin"]] + [i["gtin"] for i in n["variants"]["items"]] if g}
        hit = next((k for k in keys if k in seen), None)
        if hit:
            dupes.append({"product_id": n["product_id"], "url": n["source"]["url"], "kept": seen[hit], "reason": hit[0]})
            continue
        seen.update(dict.fromkeys(keys, n["product_id"]))
        c = n["content"]
        for k in ("title", "full_description", "short_description", "meta_title", "meta_description", "h1"):
            c[k] = plain(c[k])
        c["bullet_points"] = [b for b in (plain(b) for b in c["bullet_points"]) if b]
        out.append(n)
    with open(OUT / "shirts_clean.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(n, ensure_ascii=False) + "\n" for n in out)
    stats_file = OUT / "dataset_stats.json"
    if stats_file.exists():
        stats = json.loads(stats_file.read_text(encoding="utf-8"))
        stats["clean_records"] = len(out)
        stats["duplicates_dropped"] = dict(Counter(d["reason"] for d in dupes))
        stats["duplicates"] = dupes
        stats_file.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"clean: {len(out)} records -> {OUT / 'shirts_clean.jsonl'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--stores", nargs="*", help="domains from stores.csv (default: all with use=yes)")
    c.add_argument("--max-products", type=int, default=20)
    c.add_argument("--per-store", type=int, default=4)
    c.add_argument("--types", choices=["tees", "shirts"], default="tees", help="tees: T-shirts only (default); shirts: all shirt types")
    c.add_argument("--workers", type=int, default=4, help="stores fetched in parallel (one thread per store)")
    c.add_argument("--fresh", action="store_true", help="delete existing output and start over")
    c.add_argument("--no-cache", action="store_true", help="refetch pages instead of using dataset/.cache")
    sub.add_parser("clean")
    sub.add_parser("report")
    args = ap.parse_args()
    {"collect": collect, "clean": clean, "report": report}[args.cmd](args)


if __name__ == "__main__":
    main()
