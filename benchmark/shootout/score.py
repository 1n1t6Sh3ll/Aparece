"""Deterministic audits (title, tags, description) and bootstrap statistics for the shoot-out. No model calls."""
import random
import re

import normalize as N
from benchmark.metrics import _entity_rows
from optimizer import guard
from optimizer.truth import MATERIAL, PHRASES, _material, color_names, fact_sentences

JSONLD_KEYS = ("name", "brand", "material", "color", "size", "audience", "gtin", "additionalProperty", "offers")
TITLE_RANGE = (15, 90)  # characters; the optimizer asks for <= 90
MAX_TAGS = 8
VOWELS = re.compile(r"[aeiouy]+")
TYPE_WORD = {"en": {"t_shirt": "t-shirt"}, "es": {"t_shirt": "camiseta"}}
GENERIC = {"fit", "corte", "sleeves", "sleeve", "manga", "mangas", "neck", "cuello", "for", "para", "fabric", "tejido"}
# Words that carry no shopping intent (on top of the guard's neutral vocabulary).
INTENT_STOP = set("""
can could you your recommend recommendation recommendations good great best need needs looking look want wants which what
some any suggestions suggest please would like something that with under ideally around about there does dont won't wont
should really also more most well just good-looking find where here them they their other than into after before
busco buscando quiero necesito recomiendas recomienda recomendarias alguna alguno algun cual cuales puedes sugerir
sugerencias mejor mejores para como donde algo tengo sirva sirvan pase quede queden sean tenga tengan otra otro
""".split())


def _fold_tokens(text):
    return guard._tokens(text or "")


def _words(text):
    return {t for t in _fold_tokens(text) if not t[0].isdigit()}


def guard_report(text, truth):
    """Optimizer guardrail on a text: flagged sentences, problems, claim accuracy."""
    rep = guard.check_text(text or "", truth)
    flagged = [{"sentence": r["sentence"], "problems": r["problems"]} for r in rep if r["problems"]]
    return {"sentences": len(rep), "flagged_sentences": len(flagged),
            "unsupported_claims": sum(c["status"] != guard.SUPPORTED for r in rep for c in r["claims"]),
            "accuracy": guard.accuracy(rep)["accuracy"], "flagged": flagged[:5]}


# ---------- ProductLens tags: localized verified values only ----------
def fact_tags(truth, lang):
    f, P, out = truth["facts"], PHRASES[lang], []
    ptype = f.get("identity.product_type")
    if ptype:
        out.append(TYPE_WORD[lang].get(ptype, str(ptype).replace("_", " ")))
    pct = f.get("materials.material_percentages") or {}
    for m in (sorted(pct, key=lambda k: -pct[k]) if isinstance(pct, dict) and pct else
              [f["materials.primary_material"]] if f.get("materials.primary_material") else []):
        out.append(MATERIAL.get(lang, {}).get(m, m.replace("_", " ")))
    for table, key in (("fit", "fit_and_style.fit"), ("sleeve", "fit_and_style.sleeve_length"),
                       ("neckline", "fit_and_style.neckline"), ("pattern", "fit_and_style.pattern"),
                       ("audience", "identity.audience")):
        phrase = P[table].get(f.get(key)) if f.get(key) else None
        if phrase:
            out.append(phrase.rstrip(".").lower())
    out += color_names(truth, lang)
    if f.get("materials.fabric_weight_gsm"):
        out.append(f"{f['materials.fabric_weight_gsm']:g} gsm" if isinstance(f["materials.fabric_weight_gsm"], (int, float))
                   else f"{f['materials.fabric_weight_gsm']} gsm")
    return list(dict.fromkeys(t for t in out if t))[:MAX_TAGS]


# ---------- title ----------
def title_audit(title, truth, lang):
    f, words = truth["facts"], _words(title)
    fold = " ".join(_fold_tokens(title))

    def has(value_words):
        return bool(value_words & words) if value_words else None
    brand = f.get("identity.brand")
    ptype = dict(N.PRODUCT_TYPE).get(f.get("identity.product_type"))
    mat = _material(truth, lang)
    fit = PHRASES[lang]["fit"].get(f.get("fit_and_style.fit")) if f.get("fit_and_style.fit") else None
    checks = {"brand": (" ".join(_fold_tokens(brand)) in fold) if brand else None,
              "type": bool(re.search(ptype, title or "", re.I)) if ptype else None,
              "material": has(_words(mat) - GENERIC) if mat else None,
              "fit": has(_words(fit) - GENERIC) if fit else None}
    chars = len((title or "").strip())
    g = guard_report(title, truth)
    present = [v for v in checks.values() if v is not None]
    length_ok = TITLE_RANGE[0] <= chars <= TITLE_RANGE[1]
    return {"chars": chars, "length_ok": length_ok, "has": checks, "guard": g, "passes": bool(title) and g["flagged_sentences"] == 0,
            "score": round((sum(present) + length_ok) / (len(present) + 1), 4)}


# ---------- tags ----------
def intent_keywords(text):
    return {t[:5] for t in guard._tokens(text) if len(t) >= 4 and not t[0].isdigit()
            and t not in guard.NEUTRAL and t not in INTENT_STOP}


def tags_audit(tags, truth, lang, prompts):
    tags = [t.strip() for t in tags or [] if isinstance(t, str) and t.strip()]
    if not tags:
        return {"n": 0, "passes": False, "score": 0.0, "passing": [], "false": [], "duplicates": 0,
                "fact_relevance": None, "intent_relevance": None, "language_match": None}
    rec, vocab = guard.check_record(truth), guard.vocabulary(truth)
    # a tag may name the product itself: its brand and product-name words count as supported (tags only)
    name_words = set(guard._tokens(" ".join(str(truth["facts"].get(k) or "") for k in ("identity.brand", "identity.product_name"))))
    vocab = (vocab[0] | {w for t in name_words for w in (t, *t.split("-"))}, vocab[1])
    fact_words = {w for s in fact_sentences(truth, lang) for w in _words(s)} - guard.NEUTRAL - GENERIC
    fact_words |= _words(truth["facts"].get("identity.brand") or "")
    other = "es" if lang == "en" else "en"
    foreign = {w for s in fact_sentences(truth, other) for w in _words(s)} - {w for s in fact_sentences(truth, lang) for w in _words(s)}
    intents = set().union(*(intent_keywords(p["text"]) for p in prompts)) if prompts else set()
    seen, dup, passing, false, fr, ir, lm = set(), 0, [], [], 0, 0, 0
    for t in tags:
        key = " ".join(_fold_tokens(t))
        if key in seen:
            dup += 1
            continue
        seen.add(key)
        _, problems = guard.check_sentence(t, truth, rec, vocab)
        (false if problems else passing).append(t)
        w = _words(t)
        fr += bool(w & fact_words) or bool(re.search(dict(N.PRODUCT_TYPE).get(truth["facts"].get("identity.product_type"), "(?!)"), t, re.I))
        ir += bool({x[:5] for x in w} & intents)
        lm += not (w & foreign)
    n = len(seen)
    out = {"n": len(tags), "duplicates": dup, "passing": passing, "false": false,
           "fact_relevance": round(fr / n, 4), "intent_relevance": round(ir / n, 4), "language_match": round(lm / n, 4)}
    out["passes"] = not false
    out["score"] = round((out["fact_relevance"] + out["intent_relevance"] + out["language_match"]) / 3
                         * (n / len(tags)) * (len(passing) / n), 4)
    return out


# ---------- description ----------
def _supported_fields(text, truth):
    return {c["field"] for r in guard.check_text(text, truth) for c in r["claims"] if c["status"] == guard.SUPPORTED}


def attribute_coverage(text, truth, lang):
    """Verified attributes stated (and supported) in the text / those the full fact list states."""
    full = _supported_fields(" ".join(fact_sentences(truth, lang)), truth)
    return round(len(_supported_fields(text or "", truth) & full) / len(full), 4) if full else None


def intent_coverage(text, prompts):
    """Share of canonical intents whose content words the text addresses (>= 2 keywords, or all if fewer).
    A lexical proxy, not a relevance judgement."""
    have, hit = {t[:5] for t in guard._tokens(text or "")}, 0
    for p in prompts:
        kw = intent_keywords(p["text"])
        hit += bool(kw) and len(kw & have) >= min(2, len(kw))
    return round(hit / len(prompts), 4) if prompts else None


def readability(text, lang):
    """Flesch reading ease (en) or Fernandez-Huerta (es, corrected form). Higher = easier."""
    words = [t for t in guard._tokens(text or "") if not t[0].isdigit()]
    sents = max(1, len(guard.sentences(text or "")))
    if not words:
        return None
    syl = sum(max(1, len(VOWELS.findall(w))) for w in words) / len(words)
    wps = len(words) / sents
    score = 206.84 - 60 * syl - 1.02 * wps if lang == "es" else 206.835 - 1.015 * wps - 84.6 * syl
    return round(score, 1)


def jsonld_completeness(node):
    return round(sum(k in node for k in JSONLD_KEYS) / len(JSONLD_KEYS), 4) if isinstance(node, dict) else None


def description_audit(text, truth, lang, prompts, json_ld=None):
    g = guard_report(text, truth)
    return {"guard": g, "passes": bool(text) and g["flagged_sentences"] == 0,
            "attribute_coverage": attribute_coverage(text, truth, lang), "intent_coverage": intent_coverage(text, prompts),
            "readability": readability(text, lang), "words": len((text or "").split()), "chars": len(text or ""),
            "jsonld_completeness": jsonld_completeness(json_ld)}


# ---------- visibility statistics ----------
def metrics(obs, k=3):
    """Mention rate, top-k, MRR of the target via benchmark.metrics (the target id is mapped to 'T')."""
    if not obs:
        return None
    matched = [{"mentions": ["T" if pid == o["target"] else pid for pid in o["mentions"]]} for o in obs]
    row = _entity_rows(matched, {"T": "T"}, lambda m: (), k)["T"]
    return {"mention_rate": row["mention_rate"], "top3_rate": row[f"top{k}_rate"], "mrr": row["mrr"], "n": len(obs)}


def _units(obs):
    by = {}
    for o in obs:
        by.setdefault((o["group"], o["prompt_id"]), []).append(o)
    return by


def _pct(d, q):
    return round(d[min(len(d) - 1, int(q * len(d)))], 4)


def with_ci(obs, b=1000, seed=0):
    """Point estimates plus 95% percentile bootstrap CIs, resampling (product, prompt) clusters."""
    point = metrics(obs)
    if not point:
        return None
    units = list(_units(obs).values())
    rng, draws = random.Random(seed), {m: [] for m in ("mention_rate", "top3_rate", "mrr")}
    for _ in range(b):
        s = metrics([o for u in (rng.choice(units) for _ in units) for o in u])
        for m in draws:
            draws[m].append(s[m])
    out = {"n": point["n"], "units": len(units)}
    for m, d in draws.items():
        d.sort()
        out[m] = {"value": point[m], "lo": _pct(d, 0.025), "hi": _pct(d, 0.975)}
    return out


def paired_diff(obs_a, obs_b, metric="mrr", b=1000, seed=0):
    """metric(A) - metric(B) on shared (product, prompt) clusters, with a 95% bootstrap CI."""
    ua, ub = _units(obs_a), _units(obs_b)
    keys = sorted(set(ua) & set(ub))
    if not keys:
        return None
    pick = lambda ks, u: [o for k in ks for o in u[k]]  # noqa: E731
    value = metrics(pick(keys, ua))[metric] - metrics(pick(keys, ub))[metric]
    rng, d = random.Random(seed), []
    for _ in range(b):
        ks = [rng.choice(keys) for _ in keys]
        d.append(metrics(pick(ks, ua))[metric] - metrics(pick(ks, ub))[metric])
    d.sort()
    return {"metric": metric, "value": round(value, 4), "lo": _pct(d, 0.025), "hi": _pct(d, 0.975), "units": len(keys)}
