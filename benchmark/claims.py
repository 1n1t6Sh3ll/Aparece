"""Claim checking (hallucination detection) for stored AI answers.

For each catalog product matched in a response, the sentences that mention it (plus following
sentences until another product, list item or blank line) are parsed with the deterministic rules in
dataset/collect/normalize.py. Each claim is compared only with that product's non-null ground truth:
SUPPORTED (matches), CONTRADICTED (conflicts), UNVERIFIABLE (gold null/unknown; never counted wrong).
Origin and certifications have no normalized field; they are checked against the product's page text
(description, bullets, features) and a certification absent there stays UNVERIFIABLE.
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from .match import LIST_ITEM_RE, match_response, norm
from .metrics import model_key

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dataset" / "collect"))
import normalize as N  # noqa: E402  (reused rules; not copied)

SUPPORTED, CONTRADICTED, UNVERIFIABLE = "SUPPORTED", "CONTRADICTED", "UNVERIFIABLE"
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
FINE = {"spandex": "elastane"}  # synonyms
COARSE = {"organic_cotton": "cotton", "recycled_polyester": "polyester", "merino_wool": "wool"}
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "XXL", "XXXL"]
SIZE_ALIAS = {"2XL": "XXL", "3XL": "XXXL"}
SIZE_PHRASE = re.compile(r"\b(?:sizes?|tallas?)\b[^.\n]{0,60}", re.I)
SIZE_TOKEN = r"(?:XXS|XS|XXXL|XXL|XL|[2-6]XL|S|M|L)"
SIZE_RANGE = re.compile(rf"\b({SIZE_TOKEN})\s*(?:-|–|to|a|hasta)\s*({SIZE_TOKEN})\b")
PRICE_NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)(?![\d]|[.,]\d)"
CUR_BEFORE = re.compile(r"(US\$|MX\$|C\$|A\$|USD|EUR|GBP|MXN|\$|€|£)\s?" + PRICE_NUM)
CUR_AFTER = re.compile(PRICE_NUM + r"\s?(€|EUR|USD|MXN|GBP|euros?\b|pesos?\b|d[oó]lares\b)", re.I)
CURRENCY = {"US$": {"USD"}, "USD": {"USD"}, "MX$": {"MXN"}, "MXN": {"MXN"}, "C$": {"CAD"}, "A$": {"AUD"},
            "$": {"USD", "MXN", "CAD", "AUD"}, "€": {"EUR"}, "EUR": {"EUR"}, "EURO": {"EUR"}, "EUROS": {"EUR"},
            "£": {"GBP"}, "GBP": {"GBP"}, "PESO": {"MXN"}, "PESOS": {"MXN"},
            "DOLARES": {"USD"}, "DÓLARES": {"USD"}}
ORIGIN_RE = re.compile(r"\b(?i:made in|hecho en|fabricad[oa] en|confeccionad[oa] en)\s+(?i:the\s+|el\s+)?"
                       r"([A-ZÁÉÍÓÚ][\wáéíóúñ]+(?:[ ]+[A-ZÁÉÍÓÚ][\wáéíóúñ]+)?)")
COUNTRY = {"espana": "spain", "mexico": "mexico", "turquia": "turkey", "portugal": "portugal",
           "estados unidos": "usa", "united states": "usa", "usa": "usa", "u s a": "usa",
           "italia": "italy", "peru": "peru", "marruecos": "morocco", "reino unido": "uk", "united kingdom": "uk",
           "england": "uk", "inglaterra": "uk", "bangladesh": "bangladesh", "india": "india", "china": "china"}
CERTS = [("gots", r"\bGOTS\b|global organic textile"), ("oeko_tex", r"oeko[- ]?tex"),
         ("fair_trade", r"fair ?trade|comercio justo"), ("b_corp", r"\bB[- ]?Corp"),
         ("ocs", r"\bOCS\b|organic content standard"), ("grs", r"\bGRS\b|global recycled standard"),
         ("bluesign", r"bluesign"), ("fair_wear", r"fair wear")]


def load_gold(path):
    """Normalized records (JSONL or JSON list) keyed by product_id."""
    text = Path(path).read_text(encoding="utf-8").strip()
    rows = json.loads(text) if text.startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    return {r["product_id"]: r for r in rows}


# ---- claim extraction ---------------------------------------------------------------------

def _size(tok):
    tok = SIZE_ALIAS.get(tok.upper(), tok.upper())
    return tok if tok in SIZE_ORDER else None


def extract_claims(text):
    """[(field, value)] claimed in `text`, using normalize.py rules."""
    out = []
    comp, _ = N.parse_composition(text)
    if comp:
        out.append(("materials.material_percentages", comp))
    for field, table in (("fit_and_style.fit", N.FIT), ("fit_and_style.sleeve_length", N.SLEEVE),
                         ("fit_and_style.neckline", N.NECKLINE), ("identity.audience", N.AUDIENCE)):
        hits = {v for v, _ in N.match_lookup(text, table)}
        if len(hits) == 1:  # several values in one context cannot be attributed
            out.append((field, hits.pop()))
    w = N.parse_weight(text)
    if w and w[0] is not None:
        out.append(("materials.fabric_weight_gsm", w[0]))
    for m in list(CUR_BEFORE.finditer(text)) + list(CUR_AFTER.finditer(text)):
        sym, num = (m.group(1), m.group(2)) if m.re is CUR_BEFORE else (m.group(2), m.group(1))
        curs = CURRENCY.get(sym.upper()) or CURRENCY.get(sym)
        price = N.to_price(num)
        if curs and price:
            out.append(("commerce.price", (price, sorted(curs))))
    colors = []
    for word in re.findall(r"[^\W\d_]+", text):
        c = N.normalize_color(word)
        if c and c not in colors:
            colors.append(c)
    if "navy" in colors and "blue" in colors and re.search(r"\bnavy\s+blue\b|\bazul\s+marino\b", text, re.I):
        colors.remove("blue")  # "navy blue" / "azul marino" is one colour (navy), not navy + blue
    out += [("variants.colors", c) for c in colors]
    sizes = []
    for phrase in SIZE_PHRASE.findall(text):
        for a, b in SIZE_RANGE.findall(phrase):
            if _size(a) and _size(b):
                i, j = SIZE_ORDER.index(_size(a)), SIZE_ORDER.index(_size(b))
                sizes += SIZE_ORDER[min(i, j):max(i, j) + 1]
        sizes += [_size(t) for t in re.findall(rf"\b{SIZE_TOKEN}\b", phrase) if _size(t)]
    out += [("variants.sizes", s) for s in dict.fromkeys(sizes)]
    out += [("origin", _country(m)) for m in dict.fromkeys(ORIGIN_RE.findall(text))]
    out += [("certification", c) for c, p in CERTS if re.search(p, text, re.I)]
    return out


def _country(name):
    key = norm(name).strip()
    return COUNTRY.get(key, key)


# ---- attribution: which sentences talk about which product --------------------------------

def product_contexts(text, products, mentioned):
    """{product_id: [sentences]} for products in `mentioned`. A sentence naming several products is skipped."""
    keys = {(norm(p["brand"]), norm(p["name"])) for p in products if p["product_id"] in mentioned}
    subset = [p for p in products if p["product_id"] in mentioned or (norm(p["brand"]), norm(p["name"])) in keys]
    ctx, current = defaultdict(list), None
    for line in (text or "").splitlines():
        if not line.strip():
            current = None
            continue
        item = LIST_ITEM_RE.match(line)
        if item:  # a new list item starts a new context
            current, line = None, item.group(1)
        for sent in SENTENCE_RE.split(line):
            found = match_response(sent, subset)["mentions"]
            if len(found) == 1:
                current = found[0]
            elif found:
                current = None  # several products in one sentence: not attributable
            if current:
                ctx[current].append(sent.strip())
    return ctx


# ---- comparison with ground truth ---------------------------------------------------------

def _evidence(rec, field):
    ev = next((e for e in rec.get("evidence") or [] if e.get("field") == field), None)
    return {"source_text": ev["source_text"], "source_location": ev["source_location"]} if ev else None


def _comp(c, coarse=False):
    out = {}
    for k, v in c.items():
        k = FINE.get(k, k)
        k = COARSE.get(k, k) if coarse else k
        out[k] = out.get(k, 0) + v
    return out


def _page_text(rec):
    c = rec.get("content") or {}
    parts = [c.get("full_description"), c.get("short_description"), c.get("title")] + (c.get("bullet_points") or [])
    parts += rec.get("features") or []
    return "\n".join(p for p in parts if isinstance(p, str))


def check(field, value, rec):
    """(status, gold_value, evidence) for one claim against one normalized record."""
    mat, fit, com, var = (rec.get(k) or {} for k in ("materials", "fit_and_style", "commerce", "variants"))
    if field == "materials.material_percentages":
        gold = mat.get("material_percentages") or None
        if not gold:
            return UNVERIFIABLE, None, None
        a, b = _comp(value, True), _comp(gold, True)
        if a.keys() != b.keys() or any(abs(a[k] - b[k]) > 1 for k in a):
            status = CONTRADICTED
        else:  # 'cotton' for gold 'organic_cotton' is fine; 'organic cotton' for gold 'cotton' is unknown
            fine_gold = _comp(gold)
            status = SUPPORTED if all(k in fine_gold or k in COARSE.values() for k in _comp(value)) else UNVERIFIABLE
        return status, gold, _evidence(rec, field)
    if field in ("fit_and_style.fit", "fit_and_style.sleeve_length", "fit_and_style.neckline", "identity.audience"):
        sec, key = field.split(".")
        gold = (rec.get(sec) or {}).get(key)
        if gold is None:
            return UNVERIFIABLE, None, None
        ok = value == gold or (key == "audience" and gold == "unisex" and value in ("men", "women"))
        return (SUPPORTED if ok else CONTRADICTED), gold, _evidence(rec, field)
    if field == "materials.fabric_weight_gsm":
        gold = mat.get("fabric_weight_gsm")
        if gold is None:
            return UNVERIFIABLE, None, None
        ok = abs(value - gold) <= max(5, 0.05 * gold)
        return (SUPPORTED if ok else CONTRADICTED), gold, _evidence(rec, field)
    if field == "commerce.price":
        price, curs = value
        cur = com.get("currency")
        golds = [p for p in [com.get("price"), com.get("sale_price")] + [i.get("price") for i in var.get("items") or []]
                 if isinstance(p, (int, float))]
        if not cur or cur not in curs or not golds:
            return UNVERIFIABLE, golds[0] if golds else None, None
        ok = any(abs(price - g) <= max(0.5, 0.02 * g) for g in golds)
        return (SUPPORTED if ok else CONTRADICTED), com.get("price", golds[0]), _evidence(rec, field)
    if field == "variants.colors":
        gold = [c.get("normalized") for c in var.get("colors") or []]
        if not gold:
            return UNVERIFIABLE, None, None
        ev = _evidence(rec, field)
        if value in gold:
            return SUPPORTED, sorted(g for g in gold if g), ev
        return (UNVERIFIABLE if None in gold else CONTRADICTED), sorted(g for g in gold if g), ev
    if field == "variants.sizes":
        gold = [_size(s.get("normalized_size") or "") for s in var.get("sizes") or []]
        if not gold:
            return UNVERIFIABLE, None, None
        ev = _evidence(rec, field)
        known = [g for g in gold if g]
        if value in known:
            return SUPPORTED, known, ev
        return (UNVERIFIABLE if None in gold else CONTRADICTED), known, ev
    page = _page_text(rec)
    if field == "origin":
        gold = sorted({_country(m) for m in ORIGIN_RE.findall(page)})
        if not gold:
            return UNVERIFIABLE, None, None
        m = ORIGIN_RE.search(page)
        return (SUPPORTED if value in gold else CONTRADICTED), gold, {"source_text": m.group(0), "source_location": "content/features"}
    if field == "certification":
        m = re.search(dict(CERTS)[value], page, re.I)
        if m:
            return SUPPORTED, value, {"source_text": m.group(0), "source_location": "content/features"}
        return UNVERIFIABLE, None, None
    return UNVERIFIABLE, None, None


# ---- report -------------------------------------------------------------------------------

def check_response(text, products, gold):
    """All checked claims for one response text."""
    mentioned = match_response(text, products)["mentions"]
    out = []
    for pid, sents in product_contexts(text, products, mentioned).items():
        rec = gold.get(pid)
        if not rec:
            continue
        for sent in sents:
            for field, value in extract_claims(sent):
                status, gold_value, ev = check(field, value, rec)
                out.append({"product_id": pid, "field": field, "claim": value, "status": status,
                            "quote": sent[:300], "gold": gold_value, "evidence": ev})
    return out


def _metrics(claims):
    n = defaultdict(int)
    for c in claims:
        n[c["status"]] += 1
    s, c, u = n[SUPPORTED], n[CONTRADICTED], n[UNVERIFIABLE]
    return {"claims": s + c + u, "supported": s, "contradicted": c, "unverifiable": u,
            "claim_accuracy": round(s / (s + c), 4) if s + c else None,
            "hallucination_rate": round(c / (s + c), 4) if s + c else None,
            "unverifiable_share": round(u / (s + c + u), 4) if s + c + u else None}


def claims_report(records, products, gold, examples=5):
    """Claim metrics per model and per model/language, with example claims."""
    providers = defaultdict(set)
    for r in records:
        providers[r["model"]].add(r.get("provider"))
    ambiguous = {m for m, p in providers.items() if len(p) > 1}
    by_model = defaultdict(list)
    for r in records:
        for c in check_response(r.get("response_text", ""), products, gold):
            by_model[model_key(r, ambiguous)].append(dict(c, language=r.get("language"), prompt_id=r.get("prompt_id")))
    models = {}
    for model, cs in sorted(by_model.items()):
        langs = defaultdict(list)
        for c in cs:
            langs[c["language"]].append(c)
        fields = defaultdict(list)
        for c in cs:
            fields[c["field"]].append(c)
        models[model] = dict(_metrics(cs),
                             languages={l: _metrics(v) for l, v in sorted(langs.items(), key=lambda x: str(x[0]))},
                             fields={f: _metrics(v) for f, v in sorted(fields.items())},
                             examples={st: [c for c in cs if c["status"] == st][:examples]
                                       for st in (CONTRADICTED, SUPPORTED)})
    return {"method": "deterministic normalize.py rules; compared only with non-null ground truth",
            "overall": _metrics([c for cs in by_model.values() for c in cs]), "models": models}


def _pct(v):
    return "n/a" if v is None else f"{v:.2f}"


def claims_markdown(rep):
    lines = ["", "## Claim accuracy (hallucination check)", "",
             "Claims about matched products, compared only with non-null ground truth. "
             "UNVERIFIABLE claims (gold unknown) are never counted as wrong.", "",
             "| model | language | claims | supported | contradicted | unverifiable | accuracy | hallucination | unverifiable share |",
             "|---|---|---|---|---|---|---|---|---|"]
    for model, m in rep["models"].items():
        for lang, s in [("all", m)] + list(m["languages"].items()):
            lines.append(f"| {model} | {lang} | {s['claims']} | {s['supported']} | {s['contradicted']} | "
                         f"{s['unverifiable']} | {_pct(s['claim_accuracy'])} | {_pct(s['hallucination_rate'])} | "
                         f"{_pct(s['unverifiable_share'])} |")
    for model, m in rep["models"].items():
        for status, cs in m["examples"].items():
            if cs:
                lines += ["", f"{model} - {status.lower()} examples:"]
            for c in cs:
                ev = c["evidence"] or {}
                lines.append(f"- {c['product_id']} {c['field']}: \"{c['quote']}\" -> claim {json.dumps(c['claim'], ensure_ascii=False)}, "
                             f"gold {json.dumps(c['gold'], ensure_ascii=False)}"
                             + (f" (evidence: \"{ev.get('source_text')}\" @ {ev.get('source_location')})" if ev else ""))
    return "\n".join(lines) + "\n"
