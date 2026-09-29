"""Find comparable products (peers) for a target normalized record.

Hard filters (a candidate is excluded if any fails):
  - same identity.product_type (target must have one)
  - same source.language
  - price within +/-30% of the target price, when both prices are known and in the
    same known currency (otherwise the price criterion is skipped)
  - same identity.audience, when both audiences are known

Score (higher = more comparable), one point each when both sides are known and match:
  audience, price (in band), subcategory, fit, pattern, primary_material.
Ties break by absolute price difference (unknown last), then product_id.
The score only ranks candidates; it says nothing about product quality.
"""
import json

PRICE_BAND = 0.30
SOFT_FIELDS = [("identity", "subcategory"), ("fit_and_style", "fit"),
               ("fit_and_style", "pattern"), ("materials", "primary_material")]


def load_records(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def get(rec, section, key):
    return (rec.get(section) or {}).get(key)


def price(rec):
    p = get(rec, "commerce", "price")
    return p if isinstance(p, (int, float)) and p > 0 else None


def price_comparable(t, c):
    """Prices are compared only when both are known and in the same known currency."""
    cur = get(t, "commerce", "currency")
    return bool(price(t) and price(c) and cur and cur == get(c, "commerce", "currency"))


def _eligible(t, c):
    if c.get("product_id") == t.get("product_id"):
        return False
    if get(c, "identity", "product_type") != get(t, "identity", "product_type"):
        return False
    if get(c, "source", "language") != get(t, "source", "language"):
        return False
    if price_comparable(t, c) and abs(price(c) - price(t)) > PRICE_BAND * price(t):
        return False
    ta, ca = get(t, "identity", "audience"), get(c, "identity", "audience")
    return not (ta and ca and ta != ca)


def score(t, c):
    s = 0
    ta = get(t, "identity", "audience")
    if ta and ta == get(c, "identity", "audience"):
        s += 1
    if price_comparable(t, c):
        s += 1  # in band, guaranteed by _eligible
    for sec, key in SOFT_FIELDS:
        v = get(t, sec, key)
        if v and v == get(c, sec, key):
            s += 1
    return s


def find_peers(target, records, k=10):
    """Return up to k (score, record) pairs, most comparable first."""
    if not get(target, "identity", "product_type"):
        return []
    def order(c):
        diff = abs(price(c) - price(target)) if price_comparable(target, c) else float("inf")
        return (-score(target, c), diff, c.get("product_id") or "")

    cands = sorted((c for c in records if _eligible(target, c)), key=order)
    return [(score(target, c), c) for c in cands[:k]]
