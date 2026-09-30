"""Find comparable products (peers) for a target normalized record.

Hard filters (a candidate is excluded if any fails):
  - same identity.product_type (target must have one)
  - same source.language
  - same commerce.currency, when the target's currency is known (even if its price is not)
  - price within +/-30% of the target price, when both prices are known and in the
    same known currency (otherwise the price criterion is skipped)
  - same identity.audience, when both audiences are known; kids vs adult always (unknown counts as adult)
  - same fit_and_style.sleeve_length, when both are known
  - same pack size (single vs '3-pack' etc., from the title)
  - no recorded dead/redirected link status (when a link_status exists)

Score (higher = more comparable), one point each when both sides are known and match:
  audience, price (in band), subcategory, fit, pattern, primary_material.
Ties break by absolute price difference (unknown last), then product_id.
The score only ranks candidates; it says nothing about product quality.

similar_peers() is a separate, softer ranking (no hard filters) using documented
weights over category, price band, attributes, use/style, market, language and text.
"""
import json
import math
import re
from collections import Counter

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


PACK_RE = re.compile(r"\b(\d{1,2})\s?-?\s?(?:pack|pk|pcs|pieces|piezas|unidades|er[- ]?pack)\b|"
                     r"\b(?:pack|set|paquete|lote) (?:of|de) (\d{1,2})\b", re.I)
DEAD_LINKS = {"dead", "broken", "gone", "not_found", "redirected", "redirect", "error"}


def pack_size(rec):
    """Items per listing from the title/name ('3-pack', 'pack of 2', '3 piezas'); 1 when none is stated."""
    for text in ((rec.get("content") or {}).get("title"), get(rec, "identity", "product_name")):
        m = PACK_RE.search(text or "")
        if m and int(m.group(1) or m.group(2)) > 1:
            return int(m.group(1) or m.group(2))
    return 1


def link_dead(rec):
    """True when a recorded link status says the URL is dead or redirected; no status recorded -> False.
    (Link checking itself is TEAM-50; this only reads a status if one is present.)"""
    s = rec.get("link_status") or get(rec, "source", "link_status")
    s = s.get("status") if isinstance(s, dict) else s
    if isinstance(s, int) or (isinstance(s, str) and s.isdigit()):
        return not 200 <= int(s) < 300
    return isinstance(s, str) and s.lower() in DEAD_LINKS


KIDS_RE = re.compile(r"\b(?:kids?|child(?:ren)?|toddlers?|bab(?:y|ies)|infants?|youth|boys?|girls?|niñ[oa]s?|"
                     r"bebés?|infantil)\b", re.I)


def adult(rec):
    """False for kids' items: audience 'kids', or no audience and a kids word in the title/name."""
    aud = get(rec, "identity", "audience")
    if aud:
        return aud != "kids"
    text = " ".join(x for x in ((rec.get("content") or {}).get("title"), get(rec, "identity", "product_name")) if x)
    return bool(re.search(r"\badults?\b|\badult[oa]s?\b", text, re.I)) or not KIDS_RE.search(text)


def _eligible(t, c):
    if c.get("product_id") == t.get("product_id"):
        return False
    if link_dead(c):
        return False
    ts, cs = get(t, "fit_and_style", "sleeve_length"), get(c, "fit_and_style", "sleeve_length")
    if ts and cs and ts != cs:
        return False
    if adult(t) != adult(c):
        return False  # unknown audience counts as adult: kids' items are never peers of adult/unknown targets
    if pack_size(t) != pack_size(c):
        return False
    if get(c, "identity", "product_type") != get(t, "identity", "product_type"):
        return False
    if get(c, "source", "language") != get(t, "source", "language"):
        return False
    tc = get(t, "commerce", "currency")
    if tc and get(c, "commerce", "currency") != tc:
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


# --- Weighted similarity (TEAM-43, vision section 6) ------------------------------
# Each component is in [0, 1]. A component whose inputs are unknown on either side is
# skipped and the remaining weights are renormalized, so missing data neither helps
# nor hurts. The weights are a documented starting point, not a fitted model.
SIM_WEIGHTS = {
    "category": 0.15,      # identity.product_type equal
    "subcategory": 0.05,   # identity.subcategory equal
    "price_band": 0.15,    # 1 inside +/-30%, linear to 0 at +/-100%; same currency only
    "attributes": 0.25,    # share of material/fit/style attributes (both known) that agree
    "use_style": 0.10,     # Jaccard of audience/style/pattern/features values
    "market": 0.10,        # mean of TLD match and currency match (known parts only)
    "language": 0.10,      # source.language equal
    "text": 0.10,          # cosine of title + name + description (TF-IDF or token counts)
}
SIM_ATTRS = [("materials", "primary_material"), ("materials", "fabric_type"),
             ("materials", "stretch"), ("materials", "texture"),
             ("fit_and_style", "fit"), ("fit_and_style", "neckline"),
             ("fit_and_style", "collar_type"), ("fit_and_style", "sleeve_length"),
             ("fit_and_style", "shirt_length"), ("fit_and_style", "pattern"),
             ("fit_and_style", "style")]


def tokens(s):
    return re.findall(r"[a-z0-9áéíóúñü]+", str(s or "").lower())


def _doc(rec):
    c = rec.get("content") or {}
    return " ".join(str(x) for x in (c.get("title"), get(rec, "identity", "product_name"),
                                     c.get("full_description")) if x)


def token_cosine(a, b):
    """Cosine similarity of raw token counts (no external dependency)."""
    ca, cb = Counter(tokens(a)), Counter(tokens(b))
    num = sum(ca[t] * cb[t] for t in ca)
    den = math.sqrt(sum(v * v for v in ca.values())) * math.sqrt(sum(v * v for v in cb.values()))
    return num / den if den else None


def text_similarities(target, cands, use_sklearn=True):
    """(method, [cosine or None per candidate]). Uses scikit-learn TF-IDF when it is
    installed (fit on target + candidates only), else token_cosine. No paid embeddings."""
    docs = [_doc(target)] + [_doc(c) for c in cands]
    if not docs[0] or not cands:
        return "none", [None] * len(cands)
    if use_sklearn:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            m = TfidfVectorizer().fit_transform([d or " " for d in docs])
            sims = cosine_similarity(m[0], m[1:])[0]
            return "tfidf", [float(s) if docs[i + 1] else None for i, s in enumerate(sims)]
        except (ImportError, ValueError):
            pass
    return "token_cosine", [token_cosine(docs[0], d) if d else None for d in docs[1:]]


def tld(rec):
    d = get(rec, "source", "merchant_domain") or ""
    return d.rsplit(".", 1)[-1].lower() if "." in d else None


def _eq(a, b):
    return None if a in (None, "") or b in (None, "") else float(a == b)


def _style_set(rec):
    s = {get(rec, "identity", "audience"), get(rec, "fit_and_style", "style"),
         get(rec, "fit_and_style", "pattern")}
    s |= {f.lower() for f in rec.get("features") or [] if isinstance(f, str)}
    return {x for x in s if x}


def similarity_components(t, c, text=None):
    """Per-component scores in [0, 1], or None when unknown on either side."""
    comp = {"category": _eq(get(t, "identity", "product_type"), get(c, "identity", "product_type")),
            "subcategory": _eq(get(t, "identity", "subcategory"), get(c, "identity", "subcategory")),
            "price_band": None,
            "language": _eq(get(t, "source", "language"), get(c, "source", "language")),
            "text": text}
    if price_comparable(t, c):
        rel = abs(price(c) - price(t)) / price(t)
        comp["price_band"] = 1.0 if rel <= PRICE_BAND else max(0.0, 1 - (rel - PRICE_BAND) / (1 - PRICE_BAND))
    both = [(get(t, s, k), get(c, s, k)) for s, k in SIM_ATTRS]
    both = [(a, b) for a, b in both if a not in (None, "") and b not in (None, "")]
    comp["attributes"] = sum(a == b for a, b in both) / len(both) if both else None
    st, sc = _style_set(t), _style_set(c)
    comp["use_style"] = len(st & sc) / len(st | sc) if st and sc else None
    mk = [x for x in (_eq(tld(t), tld(c)),
                      _eq(get(t, "commerce", "currency"), get(c, "commerce", "currency"))) if x is not None]
    comp["market"] = sum(mk) / len(mk) if mk else None
    return comp


def weighted_similarity(comp, weights=SIM_WEIGHTS):
    known = {k: v for k, v in comp.items() if v is not None and k in weights}
    w = sum(weights[k] for k in known)
    return round(sum(weights[k] * v for k, v in known.items()) / w, 4) if w else 0.0


def similar_peers(target, records, k=10, min_score=0.0, use_sklearn=True):
    """Rank every other record by weighted_similarity (no hard filters).
    Returns {"text_method", "weights", "peers": [{"product_id", "score", "components", "record"}]}.
    The score only measures comparability; it says nothing about product quality."""
    cands = [c for c in records if c.get("product_id") != target.get("product_id")]
    method, texts = text_similarities(target, cands, use_sklearn)
    rows = []
    for c, tx in zip(cands, texts):
        comp = similarity_components(target, c, None if tx is None else round(tx, 4))
        rows.append({"product_id": c.get("product_id"), "score": weighted_similarity(comp),
                     "components": comp, "record": c})
    rows = [r for r in rows if r["score"] >= min_score]
    rows.sort(key=lambda r: (-r["score"], r["product_id"] or ""))
    return {"text_method": method, "weights": SIM_WEIGHTS, "peers": rows[:k]}
