"""Grounding guardrail: every sentence of generated copy must be supported by Product Truth.

Per sentence (brand and product name removed first, since they are verified identity):
1. benchmark/claims.py extract_claims + check against the Truth; anything but SUPPORTED is a problem
   (UNVERIFIABLE means "not in the Truth", which for generated copy is a fabrication).
2. Material words (normalize.py MATERIALS) must be Truth materials.
3. Numbers must occur in the Truth (values or evidence text).
4. Risky claim terms (VISION §13: performance, sustainability, health, awards, reviews, certifications...) must
   occur in the Truth text.
This is deterministic and conservative; it cannot understand every paraphrase, so the merchant still reviews.
"""
import re

from benchmark.claims import COARSE, FINE, SUPPORTED, check, extract_claims
import normalize as N

from optimizer.truth import LANGS, check_record, fact_sentences

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
RISKY = re.compile(
    r"\b(?:water[- ]?proof|impermeable|water[- ]resistant|resistente al agua|breathable|transpirable|"
    r"moisture[- ]wicking|quick[- ]dry\w*|secado r[aá]pido|sustainab\w*|sostenib\w*|eco[- ]?friendly|ecol[oó]gic\w*|"
    r"organic|org[aá]nic\w*|recycled|reciclad\w*|vegan\w*|anti[- ]?bacterial|antibacterian\w*|hypoallergenic|"
    r"hipoalerg\w*|uv|upf|awards?|award[- ]winning|premiad\w*|premios?|best[- ]?sell\w*|m[aá]s vendid\w*|"
    r"reviews?|rese[ñn]as?|opiniones|stars?|estrellas|rated|valorad\w*|certifi\w*|handmade|hecho a mano|premium|"
    r"luxur\w*|lujos\w*|durable|duraderos?|duraderas?|wrinkle[- ]free|antiarrugas|carbon\w*|guarante\w*|"
    r"warrant\w*|garant\w*|patent\w*|clinically|dermatol\w*|ethical\w*|[eé]tic[oa]s?|fair trade|comercio justo)\b"
    r"|#1", re.I)


def allowed_text(truth):
    parts = [s for lang in LANGS for s in fact_sentences(truth, lang)]
    parts += [t for texts in truth["sources"].values() for t in texts]
    return "\n".join(parts)


def _materials(truth):
    f = truth["facts"]
    mats = set((f.get("materials.material_percentages") or {}).keys())
    if f.get("materials.primary_material"):
        mats.add(f["materials.primary_material"])
    mats |= {FINE.get(m, m) for m in mats} | {COARSE.get(m, m) for m in mats} | {k for k, v in FINE.items() if v in mats}
    return mats


def _numbers(text):
    return {float(n.replace(",", ".")) for n in NUMBER_RE.findall(text)}


def check_sentence(sentence, truth, rec=None, allowed=None):
    """(claims, problems). claims: checked claim dicts; problems: reasons the sentence is not grounded."""
    rec = rec or check_record(truth)
    allowed = allowed if allowed is not None else allowed_text(truth)
    s = sentence
    for k in ("identity.brand", "identity.product_name"):
        v = truth["facts"].get(k)
        if v:
            s = re.sub(re.escape(str(v)), " ", s, flags=re.I)
    claims, problems = [], []
    for field, value in extract_claims(s):
        status, gold, _ = check(field, value, rec)
        claims.append({"field": field, "claim": value, "status": status})
        if status != SUPPORTED:
            problems.append(f"{field}={value!r} is {status.lower()} against Product Truth")
    mats = _materials(truth)
    for value, pat in N.MATERIALS:
        if re.search(pat, s, re.I) and value not in mats:
            problems.append(f"material {value!r} not in Product Truth")
    extra = _numbers(re.sub(r"3/4", " ", s)) - _numbers(allowed)
    problems += [f"number {n:g} not in Product Truth" for n in sorted(extra)]
    for m in RISKY.finditer(s):
        if not re.search(r"(?<!\w)" + re.escape(m.group(0)[:6]), allowed, re.I):  # stem: certified ~ Certification
            problems.append(f"unsupported claim term {m.group(0)!r}")
    return claims, list(dict.fromkeys(problems))


def sentences(text):
    return [x.strip() for x in SENTENCE_RE.split(text or "") if x and x.strip()]


def check_text(text, truth):
    """[{sentence, claims, problems}] for each sentence."""
    rec, allowed = check_record(truth), allowed_text(truth)
    out = []
    for sent in sentences(text):
        claims, problems = check_sentence(sent, truth, rec, allowed)
        out.append({"sentence": sent, "claims": claims, "problems": problems})
    return out


def accuracy(report):
    """Share of checked claims (plus each extra problem) that are supported. 1.0 when nothing is claimed."""
    supported = sum(c["status"] == SUPPORTED for r in report for c in r["claims"])
    total = sum(len(r["claims"]) for r in report) + sum(
        sum(not p.startswith(("materials.", "fit_and_style.", "identity.", "commerce.", "variants.", "origin",
                              "certification")) for p in r["problems"]) for r in report)
    return {"accuracy": round(supported / total, 4) if total else 1.0, "claims": total, "supported": supported}
