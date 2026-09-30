"""Generate Fix: Truth -> localization -> content, guarded, with at most MAX_RETRIES regenerations."""
import json

from optimizer import guard, llm
from optimizer.truth import LANGS, fact_sentences, fallback_title, json_ld, missing_attributes, product_truth

MAX_RETRIES = 2
LANG_NAME = {"en": "English", "es": "Spanish"}
SYSTEM = ("You write factual e-commerce product copy. Use ONLY the facts given; they are verified. Do not add "
          "materials, features, certifications, origins, performance, sustainability or health claims, reviews, "
          "awards or numbers that are not in the facts. No marketing superlatives. Do not translate or reuse any "
          "other text. Reply with one JSON object: {\"title\": ..., \"description\": ...}.")


def _prompt(truth, lang, rejected):
    data = {"language": LANG_NAME[lang], "brand": truth["facts"].get("identity.brand"),
            "product_name": truth["facts"].get("identity.product_name"),
            "facts": fact_sentences(truth, lang), "fallback_title": fallback_title(truth, lang)}
    note = ""
    if rejected:
        note = ("These sentences were rejected because Product Truth does not support them; do not repeat them: "
                + json.dumps(rejected, ensure_ascii=False) + "\n")
    return (f"Write a product title (max 90 characters) and a 2-5 sentence description in {LANG_NAME[lang]} "
            f"from these verified facts only.\n{note}" + json.dumps(data, ensure_ascii=False))


def _flagged(report):
    return [{"sentence": r["sentence"], "problems": r["problems"]} for r in report if r["problems"]]


def generate(record, language="en", gaps=None, backend=None):
    """record: audited normalized record (facts + evidence). gaps: analysis.gaps.analyze() output or None.
    backend: name or (system, user) -> str callable; default OPTIMIZER_BACKEND."""
    if language not in LANGS:
        raise ValueError(f"language must be one of {LANGS}")
    name, call = (getattr(backend, "__name__", "custom"), backend) if callable(backend) else llm.get_backend(backend)
    truth = product_truth(record)
    content = record.get("content") or {}
    before_text = "\n".join(x for x in (content.get("title"), content.get("full_description")) if isinstance(x, str))
    before = guard.accuracy(guard.check_text(before_text, truth))

    rejected, attempts, out = [], [], None
    for attempt in range(1 + MAX_RETRIES):
        try:
            out = llm.parse(call(SYSTEM, _prompt(truth, language, [r["sentence"] for r in rejected])))
        except ValueError as e:  # includes JSON errors
            attempts.append({"attempt": attempt + 1, "error": str(e)})
            out = None
            continue
        title_rep, desc_rep = guard.check_text(out["title"], truth), guard.check_text(out["description"], truth)
        bad = _flagged(title_rep) + _flagged(desc_rep)
        attempts.append({"attempt": attempt + 1, "rejected": bad})
        if not bad:
            break
        rejected += bad

    fallback = out is None
    if fallback:  # no usable output: the localized fact lines themselves
        out = {"title": fallback_title(truth, language), "description": " ".join(fact_sentences(truth, language))}
    title_rep, desc_rep = guard.check_text(out["title"], truth), guard.check_text(out["description"], truth)
    title = out["title"].strip() if not _flagged(title_rep) else fallback_title(truth, language)
    description = " ".join(r["sentence"] for r in desc_rep if not r["problems"])
    removed = _flagged(title_rep) + _flagged(desc_rep)
    after = guard.accuracy(guard.check_text(title + "\n" + description, truth))
    if after["accuracy"] < before["accuracy"]:  # cannot happen with only grounded sentences left; keep it a hard stop
        raise RuntimeError("accuracy_after < accuracy_before")
    return {"product_id": truth["product_id"], "language": language, "backend": name,
            "title": title, "description": description,
            "removed_sentences": removed, "attempts": attempts, "used_fallback": fallback,
            "accuracy_before": before, "accuracy_after": after,
            "missing_attributes": missing_attributes(truth, gaps),
            "json_ld": json_ld(truth),
            "verified_facts": truth["facts"],
            "status": "draft",
            "publish": "Merchant approval required: POST /v1/optimize/publish (never written to a storefront)."}


def verify_suggestion(record, suggestion):
    """Re-run the guardrail on a suggestion before publish. Returns the list of problems (empty = grounded)."""
    truth = product_truth(record)
    problems = _flagged(guard.check_text(suggestion.get("title", ""), truth))
    problems += _flagged(guard.check_text(suggestion.get("description", ""), truth))
    if suggestion.get("json_ld") != json_ld(truth):
        problems.append({"sentence": "json_ld", "problems": ["JSON-LD differs from the one built from Product Truth"]})
    return problems
