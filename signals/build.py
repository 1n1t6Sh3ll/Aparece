"""Build per-product review and price signals (deterministic, no network).

    python signals/build.py --amazon-dir <dir with shirts_clean/raw.jsonl> \
        --wdc-dir <dir> [--reviews dataset/output/signals/amazon_reviews_agg.jsonl]

Writes dataset/output/signals/signals.jsonl (one line per product_id) and
signals_stats.json. Rules are documented next to each constant.
TODO(TEAM-24): price over time from Common Crawl snapshots of the same URL.
"""
import argparse
import bisect
import collections
import json
import math
import os
import re

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from signals import reference as ref

MIN_PEERS = 5               # peer stats only for groups with at least this many priced products
OUTLIER_MIN_PEERS = 10      # outlier fence needs a larger group
OUTLIER_K = 3.0             # outlier: log(price) outside [Q1 - 3*IQR, Q3 + 3*IQR] of the peer group
SUSPICIOUS_DISCOUNT_PCT = 50.0  # rule A: discount of 50% or more
# rule B: list ("was") price above the peer p90 while the sale price is at or below peer p75
CONFLICT_RATIO = 2.0        # offers in one currency whose max/min price ratio exceeds 2
RATING_CONFLICT = 1.0       # listing rating vs aggregated review mean differ by more than 1 star
MAX_EXCERPT_CHARS = 280
LIST_PRICE_TYPES = re.compile(r"listprice|strikethrough|msrp|srp", re.I)
GUIDANCE_NOTE = ("Observed prices of comparable listings; evidence for positioning, "
                 "not a recommended or guaranteed price.")


def num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        x = float(str(v).strip().replace(",", ""))
    except ValueError:
        return None
    return x if math.isfinite(x) else None


def quantile(sorted_vals, q):
    """Linear interpolation between closest ranks (numpy default)."""
    pos = (len(sorted_vals) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def percentile_rank(sorted_vals, x):
    """Mid-rank percentile: share of peers below x plus half of ties, 0-100."""
    below = bisect.bisect_left(sorted_vals, x)
    equal = bisect.bisect_right(sorted_vals, x) - below
    return round(100.0 * (below + 0.5 * equal) / len(sorted_vals), 1)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def offers_of(raw):
    out = []
    for o in as_list(raw.get("raw_offer_schema")):
        if isinstance(o, dict):
            out.append(o)
            out.extend(x for x in as_list(o.get("offers")) if isinstance(x, dict))
    return out


def offer_prices(raw):
    """(price, currency) pairs from offers and lowPrice/highPrice."""
    pairs = []
    for o in offers_of(raw):
        cur = o.get("priceCurrency")
        cur = cur[0] if isinstance(cur, list) and cur else cur
        for key in ("price", "lowPrice", "highPrice"):
            for v in as_list(o.get(key)):
                p = num(v)
                if p is not None:
                    pairs.append((p, cur))
    return pairs


def list_price_of(raw):
    """Explicit list/strikethrough price from schema.org priceSpecification."""
    for o in offers_of(raw):
        for spec in as_list(o.get("priceSpecification")):
            if isinstance(spec, dict) and LIST_PRICE_TYPES.search(str(spec.get("priceType") or "")):
                p = num(spec.get("price"))
                if p is not None:
                    return p
    return None


def wdc_reviews(raw):
    ps = raw.get("raw_product_schema")
    ps = ps if isinstance(ps, dict) else {}
    agg = next((a for a in as_list(ps.get("aggregateRating")) if isinstance(a, dict)), None)
    excerpts = []
    for r in as_list(ps.get("review")):
        body = r.get("reviewBody") if isinstance(r, dict) else None
        body = body[0] if isinstance(body, list) and body else body
        if isinstance(body, str) and body.strip() and len(body.strip()) <= MAX_EXCERPT_CHARS:
            rr = r.get("reviewRating") if isinstance(r.get("reviewRating"), dict) else {}
            excerpts.append({"text": body.strip(), "rating": num(rr.get("ratingValue"))})
        if len(excerpts) == 3:
            break
    if not agg and not excerpts:
        return None
    agg = agg or {}
    value, best = num(agg.get("ratingValue")), num(agg.get("bestRating"))
    # 0-5 scale only when the page declares its scale (bestRating) and the value fits it
    rating_5 = round(value / best * 5, 2) if value is not None and best and 0 <= value <= best else None
    return {"source": "wdc-schema.org", "rating_value": value, "best_rating": best,
            "worst_rating": num(agg.get("worstRating")), "rating_5": rating_5,
            "review_count": num(agg.get("reviewCount")) or num(agg.get("ratingCount")),
            "excerpts": excerpts}


def rating_out_of_range(value, best=None, worst=None):
    """True if a rating is outside its declared scale, or outside 0-5 when no scale is declared."""
    if value is None:
        return False
    lo = worst if worst is not None else 0.0
    hi = best if best is not None else 5.0
    return not (lo <= value <= hi) or (best is None and value > 5)


def base_signal(clean, raw, source, reviews_agg):
    cm = clean.get("commerce") or {}
    flags = []
    currency = cm.get("currency")
    currency_source = "record" if currency else None
    if not currency:
        flags.append("missing_currency")
        if clean["source"].get("merchant_domain") == "amazon.com":
            currency, currency_source = "USD", "assumed:amazon.com lists USD"

    price, sale = num(cm.get("price")), num(cm.get("sale_price"))
    list_price = price if sale is not None else list_price_of(raw)
    effective = sale if sale is not None else price
    if list_price is not None and list_price == effective:
        list_price = None
    if effective is not None and effective <= 0:
        flags.append("nonpositive_price")
    if list_price is not None and effective is not None and effective > list_price:
        flags.append("sale_above_list")

    pairs = offer_prices(raw)
    if pairs:
        curs = {c for _, c in pairs if c}
        same = [p for p, c in pairs if c == currency and p > 0]
        if len(curs) > 1 or (same and max(same) / min(same) > CONFLICT_RATIO) or (
                same and effective is not None and not (min(same) <= effective <= max(same))):
            flags.append("conflicting_prices")

    if source == "amazon-reviews-2023":
        period = "2023"  # metadata crawl year; scraped_at is our run time
        asin = ((raw.get("provenance") or {}).get("original") or {}).get("parent_asin") or raw.get("sku")
        rv = reviews_agg.get(asin)
        reviews = dict(rv, source="amazon-reviews-2023", research_only=True) if rv else None
        if reviews:
            reviews.pop("product_id", None)
            reviews.pop("provenance", None)
    else:
        period = (clean["source"].get("scraped_at") or "")[:7] or None
        reviews = wdc_reviews(raw)

    rating = num(cm.get("rating"))
    bad = rating_out_of_range(rating)
    if reviews and reviews.get("source") == "wdc-schema.org":
        bad = bad or rating_out_of_range(reviews["rating_value"], reviews["best_rating"], reviews["worst_rating"])
    if bad:
        flags.append("rating_out_of_range")
    if reviews and reviews.get("rating_mean") is not None and rating is not None \
            and abs(reviews["rating_mean"] - rating) > RATING_CONFLICT:
        flags.append("rating_conflict")

    discount = None
    if list_price and effective and 0 < effective < list_price:
        discount = round(100.0 * (list_price - effective) / list_price, 1)

    fx_date = fx_date_for_period(period, currency)
    usd = ref.fx_to_usd(effective, currency, fx_date) if (effective and effective > 0 and currency and period) else None
    usd_target = ref.to_target_usd(usd, period)
    return {
        "product_id": clean["product_id"],
        "source": source,
        "research_only": source == "amazon-reviews-2023",
        "url": clean["source"].get("url"),
        "product_type": clean["identity"].get("product_type"),
        "language": clean["source"].get("language"),
        "currency": currency,
        "currency_source": currency_source,
        "price": effective,
        "list_price": list_price,
        "discount_pct": discount,
        "suspicious_discount": None,
        "price_period": period,
        "price_usd": round(usd, 2) if usd is not None else None,
        "fx": {"date": fx_date, "source": ref.FX_SOURCE} if usd is not None and currency != "USD" else None,
        "price_usd_2026": round(usd_target, 2) if usd_target is not None else None,
        "cpi": {"base_period": period, "target_period": ref.TARGET_PERIOD, "series": "CPI-U CUUR0000SA0",
                "source": ref.CPI_SOURCE} if usd_target is not None else None,
        "peer": None,
        "guidance": None,
        "reviews": reviews,
        "flags": flags,
    }


def fx_date_for_period(period, currency):
    if currency == "USD":
        return None
    return ref.fx_date_for(period)


def peer_key(s):
    """Assumed currencies (amazon.com USD) never share a peer group with observed ones."""
    basis = "observed" if s["currency_source"] == "record" else "assumed"
    return (s["product_type"], s["language"], s["currency"], basis)


def add_peer_signals(signals):
    groups = collections.defaultdict(list)
    for s in signals:
        if s["price"] and s["price"] > 0 and s["currency"] and s["product_type"]:
            groups[peer_key(s)].append(s["price"])
    stats = {}
    for key, vals in groups.items():
        vals.sort()
        if len(vals) >= MIN_PEERS:
            stats[key] = {"n": len(vals), "vals": vals, "p25": quantile(vals, .25), "p50": quantile(vals, .5),
                          "p75": quantile(vals, .75), "p90": quantile(vals, .9)}
    for s in signals:
        st = stats.get(peer_key(s))
        if st and s["price"] and s["price"] > 0:
            p = s["price"]
            pos = "below_peer_range" if p < st["p25"] else "above_peer_range" if p > st["p75"] else "within_peer_range"
            s["peer"] = {"group": "|".join(str(x) for x in peer_key(s)),
                         "n": st["n"], "p25": round(st["p25"], 2), "p50": round(st["p50"], 2),
                         "p75": round(st["p75"], 2), "percentile": percentile_rank(st["vals"], p), "position": pos}
            s["guidance"] = {
                "peer_range": [round(st["p25"], 2), round(st["p75"], 2)], "currency": s["currency"],
                "text": "Middle half of %d comparable listings (%s): %.2f-%.2f %s. This listing: %.2f %s, "
                        "percentile %.0f (%s)." % (st["n"], s["peer"]["group"], st["p25"], st["p75"], s["currency"],
                                                  p, s["currency"], s["peer"]["percentile"], pos.replace("_", " ")),
                "note": GUIDANCE_NOTE}
            if st["n"] >= OUTLIER_MIN_PEERS:
                q1, q3 = math.log(st["p25"]), math.log(st["p75"])
                iqr = q3 - q1
                if not (q1 - OUTLIER_K * iqr <= math.log(p) <= q3 + OUTLIER_K * iqr):
                    s["flags"].append("price_outlier")
        if s["discount_pct"] is not None:
            rule_a = s["discount_pct"] >= SUSPICIOUS_DISCOUNT_PCT
            rule_b = bool(st) and s["list_price"] > st["p90"] and s["price"] <= st["p75"]
            s["suspicious_discount"] = rule_a or rule_b
            if s["suspicious_discount"]:
                s["flags"].append("suspicious_discount")
    return signals


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def build(sources, reviews_agg):
    """sources: list of (source_name, clean_path, raw_path)."""
    signals = []
    for name, clean_path, raw_path in sources:
        raws = {r["product_id"]: r for r in read_jsonl(raw_path)}
        for c in read_jsonl(clean_path):
            signals.append(base_signal(c, raws.get(c["product_id"], {}), name, reviews_agg))
    signals.sort(key=lambda s: s["product_id"])
    return add_peer_signals(signals)


def coverage(signals):
    c = collections.Counter()
    for s in signals:
        c["products"] += 1
        c["source:" + s["source"]] += 1
        c["reviews_amazon_joined"] += bool(s["reviews"] and s["reviews"]["source"] == "amazon-reviews-2023")
        c["reviews_wdc_present"] += bool(s["reviews"] and s["reviews"]["source"] == "wdc-schema.org")
        c["price_with_record_currency"] += s["currency_source"] == "record"
        c["price_with_currency_incl_assumed"] += bool(s["currency"])
        c["price_usd"] += s["price_usd"] is not None
        c["inflation_adjusted"] += s["price_usd_2026"] is not None
        c["peer_percentile"] += s["peer"] is not None
        c["discount_found"] += s["discount_pct"] is not None
        for f in s["flags"]:
            c["flag:" + f] += 1
    return dict(sorted(c.items()))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--amazon-dir")
    ap.add_argument("--wdc-dir")
    ap.add_argument("--reviews", default=os.path.join("dataset", "output", "signals", "amazon_reviews_agg.jsonl"))
    ap.add_argument("--out-dir", default=os.path.join("dataset", "output", "signals"))
    a = ap.parse_args(argv)
    sources = []
    if a.amazon_dir:
        sources.append(("amazon-reviews-2023", os.path.join(a.amazon_dir, "shirts_clean.jsonl"),
                        os.path.join(a.amazon_dir, "shirts_raw.jsonl")))
    if a.wdc_dir:
        sources.append(("wdc", os.path.join(a.wdc_dir, "shirts_clean.jsonl"), os.path.join(a.wdc_dir, "shirts_raw.jsonl")))
    reviews = {r["parent_asin"]: r for r in read_jsonl(a.reviews)} if os.path.exists(a.reviews) else {}
    signals = build(sources, reviews)
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, "signals.jsonl"), "w", encoding="utf-8") as f:
        for s in signals:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    cov = coverage(signals)
    with open(os.path.join(a.out_dir, "signals_stats.json"), "w", encoding="utf-8") as f:
        json.dump(cov, f, indent=2)
    print(json.dumps(cov, indent=2))


if __name__ == "__main__":
    main()
