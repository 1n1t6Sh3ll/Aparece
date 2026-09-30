"""Grounding guardrail (allowlist): a sentence of generated copy passes only if
1. every claim benchmark/claims.py extracts from it is SUPPORTED by Product Truth (UNVERIFIABLE = not in the Truth,
   which for generated copy is a fabrication), and
2. every word and number in it comes from the Truth (its localized fact sentences in EN and ES, its evidence text,
   brand, product name, product-type words) or from a small neutral vocabulary (articles, connectors, labels).
Anything else ("bamboo", "health", "eco-conscious", "free shipping") rejects the sentence. Deterministic and strict:
harmless paraphrases may be rejected, which only costs a regeneration or the template fallback.
"""
import re
import unicodedata

from benchmark.claims import COARSE, FINE, SUPPORTED, check, extract_claims
import normalize as N

from optimizer.truth import LANGS, check_record, fact_sentences

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?|[^\W\d_]+(?:['’-][^\W\d_]+)*")
NEUTRAL = set("""
a an the this that these it its is are be has have with and or in of for from to at on by as per also both each all
which made available comes come offered offer options option choose choice features featuring
size sizes color colors colour colours fabric material materials composition blend weight weighs fit cut sleeve sleeves
neck neckline collar price priced care style garment piece item product tee tees t-shirt shirt shirts top
un una unos unas el la los las lo este esta estos estas es son esta estan tiene tienen con y e o u en de del para por
al a su sus que se hecho hecha hechos hechas fabricado fabricada disponible disponibles viene vienen ofrece opciones
talla tallas color colores tejido material materiales composicion mezcla gramaje peso corte manga mangas cuello precio
cuidado prenda producto camiseta camisetas camisa camisas
""".split())


def _fold(word):
    word = unicodedata.normalize("NFKD", word.lower().replace("’", "'"))
    return "".join(c for c in word if not unicodedata.combining(c))


def _tokens(text):
    return [_fold(t) for t in TOKEN_RE.findall(text or "")]


def _is_num(tok):
    return tok[0].isdigit()


def _num(tok):
    return float(tok.replace(",", "."))


def allowed_text(truth):
    parts = [s for lang in LANGS for s in fact_sentences(truth, lang)]
    # identity text (brand, product name, title) is never evidence for an attribute word
    parts += [t for field, texts in truth["sources"].items() if not str(field).startswith(("identity.", "content."))
              for t in texts]
    return "\n".join(parts)


def vocabulary(truth):
    """(words, numbers) a grounded sentence may use."""
    words, numbers = set(NEUTRAL), set()
    for t in _tokens(allowed_text(truth)):
        if _is_num(t):
            numbers.add(_num(t))
        else:
            words.add(t)
            words.update(t.split("-"))
    ptype = truth["facts"].get("identity.product_type")
    if ptype:
        key = "_shirt" if str(ptype).endswith("_shirt") and ptype not in dict(N.PRODUCT_TYPE) else ptype
        pattern = dict(N.PRODUCT_TYPE).get(key)
        if pattern:
            words.add("__type__:" + pattern)
    return words, numbers


def _word_ok(tok, words):
    if tok in words:
        return True
    return any(w.startswith("__type__:") and re.fullmatch(w[9:], tok, re.I) for w in words)


SALE_RE = re.compile(r"\b(?:sale|reduced|discount\w*|rebajad\w*|oferta|descuento)\b", re.I)
CURRENCY_RE = r"(?:eur|usd|gbp|mxn|cad|aud|euros?|pesos?|dolares|dollars?|€|\$|£)"
IN_STOCK_RE = re.compile(r"\bin stock\b|\ben stock\b|\bavailable now\b|^\W*disponible\W*$|\bready to ship\b", re.I)
OUT_STOCK_RE = re.compile(r"\bout of stock\b|\bsold out\b|\bagotad[oa]\b", re.I)


def _near(a, b):
    return a is not None and abs(a - b) <= 0.005 * max(1, abs(b))


def _number_problems(s, truth):
    """Every number must be the value of the field its context names: material %, gsm, price, sale price, 3/4."""
    f, out = truth["facts"], []
    pct = f.get("materials.material_percentages") or {}
    for m in re.finditer(r"\d+(?:[.,]\d+)?", s):
        n, after, before = _num(m.group(0)), s[m.end():m.end() + 30], _fold(s[max(0, m.start() - 30):m.start()])
        if after.startswith("/4") or before.endswith("3/"):
            ok = f.get("fit_and_style.sleeve_length") == "three_quarter"
        elif re.match(r"\s*%", after):
            mat = N.material_of(re.split(r"[\d,;.]", after.split("%", 1)[1])[0])
            ok = mat is not None and any(_near(v, n) for k, v in pct.items() if mat in (k, COARSE.get(k), FINE.get(k)))
        elif re.match(r"\s*(?:gsm|g/m|grs?\b|gramos|g\b)", after, re.I) or re.search(r"(?:weight|weighs|gramaje|peso)\W*$", before):
            ok = _near(f.get("materials.fabric_weight_gsm"), n)
        elif re.match(r"\s*" + CURRENCY_RE, _fold(after)) or re.search(CURRENCY_RE + r"\s*$", before):
            key = "commerce.sale_price" if SALE_RE.search(before) else "commerce.price"
            ok = bool(f.get("commerce.currency")) and _near(f.get(key), n)
        else:
            ok = False  # counts, years, ratings...: no verified field
        if not ok:
            out.append(f"number {m.group(0)} is not the verified value of the field it describes")
    if SALE_RE.search(s) and f.get("commerce.sale_price") is None:
        out.append("no verified sale price")
    if IN_STOCK_RE.search(s) and f.get("commerce.availability") != "in_stock":
        out.append("availability 'in stock' not verified")
    if OUT_STOCK_RE.search(s) and f.get("commerce.availability") != "out_of_stock":
        out.append("availability 'out of stock' not verified")
    return out


def check_sentence(sentence, truth, rec=None, vocab=None):
    """(claims, problems) for one sentence; problems empty means grounded."""
    rec = rec or check_record(truth)
    words, numbers = vocab or vocabulary(truth)
    s = sentence
    for k in ("identity.brand", "identity.product_name"):
        v = truth["facts"].get(k)
        if v:
            s = re.sub(re.escape(str(v)), " ", s, flags=re.I)
    for c in truth.get("care") or []:  # verbatim verified care text
        s = re.sub(re.escape(c.rstrip(".")), " ", s, flags=re.I)
    claims, problems = [], []
    for field, value in extract_claims(s):
        status, _, _ = check(field, value, rec)
        claims.append({"field": field, "claim": value, "status": status})
        if status != SUPPORTED:
            problems.append(f"{field}={value!r} is {status.lower()} against Product Truth")
    problems += _number_problems(s, truth)
    bad = [t for t in _tokens(s) if not _is_num(t) and not _word_ok(t, words)]
    if bad:
        problems.append("words not grounded in Product Truth: " + ", ".join(dict.fromkeys(bad)))
    return claims, list(dict.fromkeys(problems))


def sentences(text):
    return [x.strip() for x in SENTENCE_RE.split(text or "") if x and x.strip()]


def check_text(text, truth):
    """[{sentence, claims, problems}] for each sentence."""
    rec, vocab = check_record(truth), vocabulary(truth)
    out = []
    for sent in sentences(text):
        claims, problems = check_sentence(sent, truth, rec, vocab)
        out.append({"sentence": sent, "claims": claims, "problems": problems})
    return out


FIELD_PREFIXES = ("materials.", "fit_and_style.", "identity.", "commerce.", "variants.", "origin", "certification")


def accuracy(report):
    """Supported claims / (checked claims + sentences with ungrounded words). 1.0 when nothing is claimed."""
    supported = sum(c["status"] == SUPPORTED for r in report for c in r["claims"])
    total = sum(len(r["claims"]) for r in report) + sum(
        any(not p.startswith(FIELD_PREFIXES) for p in r["problems"]) for r in report)
    return {"accuracy": round(supported / total, 4) if total else 1.0, "claims": total, "supported": supported}
