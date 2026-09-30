"""Aggregate Amazon Reviews 2023 reviews per parent_asin for our products only.

Source: McAuley Lab, Amazon Reviews 2023 (https://amazon-reviews-2023.github.io/),
HF McAuley-Lab/Amazon-Reviews-2023, raw_review_Clothing_Shoes_and_Jewelry.
License undeclared: output is tagged research-only.

    python signals/reviews.py --products <amazon shirts_raw.jsonl> [--source URL_OR_PATH]
"""
import argparse
import heapq
import json
import os
import re
import sys
import time
import urllib.request

REVIEWS_URL = ("https://huggingface.co/datasets/McAuley-Lab/Amazon-Reviews-2023/resolve/main/"
               "raw/review_categories/Clothing_Shoes_and_Jewelry.jsonl")
PROVENANCE = {"source": "amazon-reviews-2023", "license": "undeclared-research-only",
              "dataset_url": REVIEWS_URL}
MAX_EXCERPT_CHARS = 280   # excerpts are whole review texts, never truncated
N_EXCERPTS = 3
ASIN_RE = re.compile(rb'"parent_asin":\s*"([^"]+)"')
OUT_DEFAULT = os.path.join("dataset", "output", "signals", "amazon_reviews_agg.jsonl")


def product_asins(raw_path):
    """parent_asin -> product_id from the Amazon raw records."""
    out = {}
    with open(raw_path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            orig = (r.get("provenance") or {}).get("original") or {}
            asin = orig.get("parent_asin") or r.get("sku")
            if asin:
                out[asin] = r["product_id"]
    return out


def _http_lines(url, retries=20):
    """Yield raw lines over HTTP, resuming with a Range header after a disconnect."""
    offset, tries = 0, 0
    while True:
        req = urllib.request.Request(url, headers={"User-Agent": "ProductLens-research/0.1",
                                                   "Range": "bytes=%d-" % offset})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                for line in resp:
                    if not line.endswith(b"\n"):
                        raise ConnectionError("partial line")
                    offset += len(line)
                    yield line
            return
        except Exception as e:  # network errors: resume from last full line
            tries += 1
            if tries > retries:
                raise
            print("reconnect at byte %d after %r" % (offset, e), file=sys.stderr)
            time.sleep(min(60, 2 ** tries))


def iter_lines(source):
    if source.startswith("http"):
        return _http_lines(source)
    return open(source, "rb")


def aggregate(lines, wanted):
    """Aggregate reviews for asins in `wanted`. Deterministic for a given input order."""
    agg = {}
    for i, line in enumerate(lines):
        m = ASIN_RE.search(line)
        if not m:
            continue
        asin = m.group(1).decode()
        if asin not in wanted:
            continue
        r = json.loads(line)
        a = agg.setdefault(asin, {"n": 0, "sum": 0.0, "hist": {str(k): 0 for k in range(1, 6)},
                                  "top": []})
        rating = r.get("rating")
        if isinstance(rating, (int, float)):
            a["n"] += 1
            a["sum"] += rating
            key = str(int(round(rating)))
            if key in a["hist"]:
                a["hist"][key] += 1
        text = (r.get("text") or "").strip()
        if text and len(text) <= MAX_EXCERPT_CHARS:
            # rank: most helpful, then earliest, then file order
            item = (r.get("helpful_vote") or 0, -(r.get("timestamp") or 0), -i,
                    {"text": text, "rating": rating, "helpful_vote": r.get("helpful_vote"),
                     "verified_purchase": r.get("verified_purchase"), "timestamp": r.get("timestamp")})
            if len(a["top"]) < N_EXCERPTS:
                heapq.heappush(a["top"], item)
            else:
                heapq.heappushpop(a["top"], item)
    out = {}
    for asin, a in agg.items():
        out[asin] = {
            "parent_asin": asin,
            "rating_mean": round(a["sum"] / a["n"], 3) if a["n"] else None,
            "rating_count": a["n"],
            "rating_histogram": a["hist"],
            "excerpts": [t[3] for t in sorted(a["top"], reverse=True)],
            "provenance": PROVENANCE,
        }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--products", required=True, help="Amazon shirts_raw.jsonl")
    ap.add_argument("--source", default=REVIEWS_URL)
    ap.add_argument("--out", default=OUT_DEFAULT)
    args = ap.parse_args(argv)
    asins = product_asins(args.products)
    res = aggregate(iter_lines(args.source), set(asins))
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for asin in sorted(res):
            f.write(json.dumps(dict(res[asin], product_id=asins[asin]), ensure_ascii=False) + "\n")
    print("products=%d with_reviews=%d" % (len(asins), len(res)))


if __name__ == "__main__":
    main()
