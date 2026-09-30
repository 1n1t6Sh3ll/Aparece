"""Generate Fix: Truth -> localization -> N candidates, scored with the verifiable reward (train/reward.py
copy_reward), guarded (hard filter), with at most MAX_RETRIES regeneration rounds. The best grounded candidate wins;
candidate/reward pairs are appended to PAIRS_LOG as preference data (chosen/rejected)."""
import json
import logging
import os
import threading
from pathlib import Path

from optimizer import guard, llm
from optimizer.truth import LANGS, TITLE_MAX, fact_sentences, fallback_title, json_ld, missing_attributes, product_truth

try:
    from train.reward import copy_reward
except (ImportError, OSError) as _e:  # reward file or its schema missing: guardrail-only ranking
    logging.getLogger(__name__).warning("train/reward.py unavailable (%s); ranking candidates by guardrail only", _e)

    def copy_reward(candidate, sentence_reports, covered, targets):
        bad = [r["sentence"] for r in sentence_reports if r["problems"]]
        return {"total": -float(len(bad)), "format_ok": bool(candidate.get("title") and candidate.get("description")),
                "hallucinated": bad, "errors": ["reward unavailable: guardrail only"]}

MAX_RETRIES = 2
MAX_CANDIDATES = 5
PAIRS_LOG = Path(__file__).resolve().parent / "data" / "pairs.jsonl"  # OPTIMIZER_PAIRS_LOG overrides; "" disables
_pairs_lock = threading.Lock()
MIN_FACTS = 2  # localized fact sentences needed to write any copy
LANG_NAME = {"en": "English", "es": "Spanish"}
STYLE = {"es": "Write like a Spanish online clothing shop, in neutral Spanish understood in Spain and Latin America: "
               "retail terms such as 'camiseta', 'manga corta', 'cuello redondo', 'corte regular', 'composición'; no "
               "word-for-word translation from English. Start with the garment, e.g. 'Camiseta para hombre de manga "
               "corta y cuello redondo.'\n"}
SYSTEM = ("You write factual e-commerce product copy. Use ONLY the facts given; they are verified. Do not add "
          "materials, features, certifications, origins, performance, sustainability or health claims, reviews, "
          "awards or numbers that are not in the facts. No marketing superlatives. Do not translate or reuse any "
          "other text. Reply with one JSON object: {\"title\": ..., \"description\": ...}.")


def _prompt(truth, lang, rejected, variant=None):
    data = {"language": LANG_NAME[lang], "brand": truth["facts"].get("identity.brand"),
            "product_name": truth["facts"].get("identity.product_name"),
            "facts": fact_sentences(truth, lang), "fallback_title": fallback_title(truth, lang)}
    note = ""
    if rejected:
        note = ("These sentences were rejected because Product Truth does not support them; do not repeat them: "
                + json.dumps(rejected, ensure_ascii=False) + "\n")
    if variant:
        note += f"This is candidate {variant[0]} of {variant[1]}: vary wording and sentence order, facts only.\n"
    return (f"Write a product title (max 90 characters) and a 2-5 sentence description in {LANG_NAME[lang]} "
            f"from these verified facts only.\n{STYLE.get(lang, '')}{note}" + json.dumps(data, ensure_ascii=False))


def _reports(cand, truth):
    """Guard rows for a {title, description}: the title as one unit (identity words allowed), then each sentence."""
    return guard.check_title(cand["title"], truth) + guard.check_text(cand["description"], truth)


def _flagged(report):
    return [{"sentence": r["sentence"], "problems": r["problems"]} for r in report if r["problems"]]


def _coverage_fields(truth, texts):
    """Verified attribute fields stated by grounded sentences of texts[0] (a title) and texts[1:] (description)."""
    reports = guard.check_title(texts[0], truth) + [r for t in texts[1:] for r in guard.check_text(t, truth)]
    return _covered(truth, {"title": "\n".join(texts), "description": ""}, reports)


def _covered(truth, cand, reports):
    fields = {c["field"] for r in reports if not r["problems"] for c in r["claims"] if c["status"] == guard.SUPPORTED}
    text = (cand["title"] + "\n" + cand["description"]).lower()
    fields.update(k for k in ("identity.brand", "identity.product_name")
                  if truth["facts"].get(k) and str(truth["facts"][k]).lower() in text)
    return sorted(fields)


def _log_pairs(truth, language, backend, best, candidates):
    """Append chosen/rejected pairs (winner vs every lower-reward candidate). Product facts only, no actor/user data."""
    path = os.environ.get("OPTIMIZER_PAIRS_LOG", str(PAIRS_LOG))
    if not path or best is None or not best["guard_passed"]:  # never teach a flagged winner
        return
    chosen = json.dumps({"title": best["title"], "description": best["description"]}, ensure_ascii=False)
    rows = []
    for c in candidates:
        rej = json.dumps({"title": c["title"], "description": c["description"]}, ensure_ascii=False)
        if c is not best and rej != chosen and c["reward"]["total"] < best["reward"]["total"]:
            rows.append({"product_id": truth["product_id"], "language": language, "backend": backend,
                         "system": SYSTEM, "prompt": best["_prompt"], "chosen": chosen, "rejected": rej,
                         "chosen_reward": best["reward"]["total"], "rejected_reward": c["reward"]["total"]})
    if not rows:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with _pairs_lock, open(path, "a", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    except OSError as e:  # logging preference data must never fail a suggestion
        logging.getLogger(__name__).warning("could not append preference pairs to %s: %s", path, e)


def generate(record, language="en", gaps=None, backend=None, candidates=None):
    """record: audited normalized record (facts + evidence). gaps: analysis.gaps.analyze() output or None.
    backend: name or (system, user) -> str callable; default OPTIMIZER_BACKEND.
    candidates: N generations per round (default OPTIMIZER_CANDIDATES or 3, max MAX_CANDIDATES)."""
    if language not in LANGS:
        raise ValueError(f"language must be one of {LANGS}")
    n = int(candidates or os.environ.get("OPTIMIZER_CANDIDATES") or 3)
    if not 1 <= n <= MAX_CANDIDATES:
        raise ValueError(f"candidates must be 1..{MAX_CANDIDATES}")
    name, call = (getattr(backend, "__name__", "custom"), backend) if callable(backend) else llm.get_backend(backend)
    truth = product_truth(record)
    facts = fact_sentences(truth, language)
    if len(facts) < MIN_FACTS or not fallback_title(truth, language):
        raise ValueError(f"not enough verified facts: {len(facts)} fact sentences (need {MIN_FACTS}) and a verified "
                         "brand or product name; add evidence-backed attributes first")
    content = record.get("content") or {}
    before_text = "\n".join(x for x in (content.get("title"), content.get("full_description")) if isinstance(x, str))
    before = guard.accuracy(guard.check_text(before_text, truth))

    targets = _coverage_fields(truth, [fallback_title(truth, language)] + facts)
    rejected, attempts, candidates, out = [], [], [], None
    for rnd in range(1 + MAX_RETRIES):
        prior = list(dict.fromkeys(r["sentence"] for r in rejected))
        for i in range(n):
            prompt = _prompt(truth, language, prior, (i + 1, n) if n > 1 else None)
            try:
                cand = llm.parse(call(SYSTEM, prompt))
            except ValueError as e:  # includes JSON errors
                attempts.append({"attempt": len(attempts) + 1, "error": str(e)})
                continue
            cand = {"title": cand["title"], "description": cand["description"]}
            reports = _reports(cand, truth)
            bad = _flagged(reports)
            attempts.append({"attempt": len(attempts) + 1, "rejected": bad})
            rejected += bad
            candidates.append({"index": len(candidates), "round": rnd + 1, **cand, "guard_passed": not bad,
                               "reward": copy_reward(cand, reports, _covered(truth, cand, reports), targets),
                               "_prompt": prompt})
        if any(c["guard_passed"] and c["reward"]["format_ok"] for c in candidates):
            break

    # guardrail is a hard filter: only grounded, well-formed candidates can win; else the best one is stripped below
    eligible = [c for c in candidates if c["guard_passed"] and c["reward"]["format_ok"]] or candidates
    best = max(eligible, key=lambda c: c["reward"]["total"]) if eligible else None
    out = {"title": best["title"], "description": best["description"]} if best else None
    _log_pairs(truth, language, name, best, candidates)
    for c in candidates:
        c["chosen"] = c is best
        c.pop("_prompt")
    fallback = out is None
    if fallback:  # no usable output: the localized fact lines themselves
        out = {"title": fallback_title(truth, language), "description": " ".join(facts)}
    title_rep, desc_rep = guard.check_title(out["title"], truth), guard.check_text(out["description"], truth)
    title = out["title"].strip()
    if not title or len(title) > TITLE_MAX or _flagged(title_rep):
        title = fallback_title(truth, language)
    description = " ".join(r["sentence"] for r in desc_rep if not r["problems"])
    if not description:  # everything was stripped: deterministic template from the facts
        description, fallback = " ".join(facts), True
    removed = _flagged(title_rep) + _flagged(desc_rep)
    final = {"title": title, "description": description}
    if _flagged(_reports(final, truth)):  # never return copy that fails our own guard: template instead
        final, fallback = {"title": fallback_title(truth, language), "description": " ".join(facts)}, True
        if _flagged(_reports(final, truth)):
            raise RuntimeError("template copy failed the guardrail; refusing to return it")
    title, description = final["title"], final["description"]
    final_reports = _reports(final, truth)
    reward = copy_reward(final, final_reports, _covered(truth, final, final_reports), targets)
    after = guard.accuracy(guard.check_text(title + "\n" + description, truth))
    if after["accuracy"] < before["accuracy"]:  # cannot happen with only grounded sentences left; keep it a hard stop
        raise RuntimeError("accuracy_after < accuracy_before")
    return {"product_id": truth["product_id"], "language": language, "backend": name,
            "title": title, "description": description,
            "candidates": candidates, "reward": reward,
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
    problems = _flagged(guard.check_title(suggestion.get("title", ""), truth))
    problems += _flagged(guard.check_text(suggestion.get("description", ""), truth))
    if suggestion.get("json_ld") != json_ld(truth):
        problems.append({"sentence": "json_ld", "problems": ["JSON-LD differs from the one built from Product Truth"]})
    return problems
