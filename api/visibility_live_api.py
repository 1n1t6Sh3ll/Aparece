"""Live AI-assistant visibility check for one audited product (POST /v1/visibility/live).

Asks OpenAI and Anthropic models a small fixed set of realistic shopping questions (benchmark/prompts/tshirts.jsonl,
chosen deterministically for the product's type and language) and reports, from the observed answers only, whether
THIS product (its brand, name, domain or URL) was named or cited, at what position, and which brands were named
instead. A model runs only when its API key is set; no key, no results (never simulated). Spend is capped per
request (VISIBILITY_LIVE_MAX_USD, default $0.05) and per process per day (VISIBILITY_LIVE_DAILY_USD, default $1);
hitting a cap returns the partial results, labelled as such. Complete per-model results are cached in memory for 24 h
per (product domain+path, language, model). Rate limit: VISIBILITY_LIVE_RATE_LIMIT per minute (default 3).
"""
import json
import os
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request

from benchmark import harness
from benchmark.citations import cited_urls
from benchmark.match import LIST_ITEM_RE, host, match_response, norm, url_key
from benchmark.shootout.run import Budget, BudgetExceeded

router = APIRouter(prefix="/v1", tags=["visibility"])
ROOT = Path(__file__).resolve().parents[1] / "benchmark"
MODELS = (("openai", "gpt-4o-mini", "OPENAI_API_KEY"),
          ("anthropic", "claude-haiku-4-5-20251001", "ANTHROPIC_API_KEY"))
N_QUESTIONS, MAX_TOKENS, TTL, MAX_CACHE = 6, 400, 24 * 3600, 500
# product type -> (English, Spanish) patterns; matched against the product's name/type, then against question text
TYPES = {"polo": ("polo", "polo"), "long sleeve": (r"long[- ]sleeve|henley", r"manga larga"),
         "tank": (r"tank|vest|singlet", r"tirantes|sin mangas"), "oversized": ("oversize", "oversize|holgada"),
         "graphic": ("graphic", r"gr[aá]fic|estampad"), "heavyweight": ("heavy|thick", r"pesad|gruesa"),
         "performance": (r"moisture|performance|athletic|gym|running", r"deportiv|sudor|transpirable")}
GENERIC = ("INTENT_002", "INTENT_003", "INTENT_006", "INTENT_007", "INTENT_011", "INTENT_012")
_cache, _day, _lock = {}, {"date": None, "spent": 0.0}, threading.Lock()


def questions(rec, lang):
    """Six deterministic question dicts: intents matching the product's type first, then the generic basics."""
    lines = (ROOT / "prompts" / "tshirts.jsonl").read_text(encoding="utf-8").splitlines()
    rows = sorted((r for r in map(json.loads, filter(str.strip, lines)) if r["language"] == lang and r["split"] in ("dev", "val")),
                  key=lambda r: r["id"])
    ident = rec.get("identity") or {}
    what = " ".join(str(ident.get(k) or "") for k in ("product_name", "product_type", "subcategory")).lower().replace("_", " ")
    picked = []
    for en, es in TYPES.values():
        if re.search(en, what):
            picked += [r for r in rows if re.search(en if lang == "en" else es, r["text"].lower())]
    picked += [r for r in rows if r["canonical_intent"] in GENERIC] + rows
    seen, out = set(), []
    for r in picked:
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return [{**r, "text": _fix(r["text"])} for r in out[:N_QUESTIONS]]


MAX_FIELD = 300


def _text(d, key):
    """A str field of a dict: None or missing gives "", any other type or an oversize string is a 422."""
    v = d.get(key)
    if v is None:
        return ""
    if not isinstance(v, str) or len(v) > MAX_FIELD:
        raise HTTPException(422, f"bad_product: {key} must be text of at most {MAX_FIELD} characters")
    return v.strip()


def _target(rec):
    """The match target from an audited record; malformed or oversize fields raise 422 (before any spend)."""
    ident, src = rec.get("identity") or {}, rec.get("source") or {}
    if not isinstance(ident, dict) or not isinstance(src, dict):
        raise HTTPException(422, "bad_product: identity and source must be objects")
    url = _text(src, "canonical_url") or _text(src, "url")
    site = host(_text(src, "merchant_domain") or url)
    brand, name = _text(ident, "brand"), _text(ident, "product_name")
    for k in ("product_type", "subcategory"):
        _text(ident, k)
    aliases = [a for a in (brand if len(norm(brand).strip()) >= 3 else "", site) if a]
    return {"product_id": "target", "brand": brand, "name": name, "url": url, "site": site, "aliases": aliases}


TIPS = {"wash", "use", "air", "avoid", "choose", "look", "check", "consider", "turn", "dry", "pre", "wear", "buy", "try",
        "select", "opt", "read", "follow", "hang", "iron", "store", "fold", "size", "size-up", "keep", "add", "pick"}


def _brand(item):
    """Best-effort brand from a list item: the bold text if any, else the words before a separator. Advice such as
    "Wash in cold water" is not a brand and gives ""."""
    m = re.search(r"\*\*(.+?)\*\*", item) or re.match(r"([^:(,]+)", item)
    b = re.split(r"\s[-–—:(]\s?|:", re.sub(r"^[\d.)\s*_]+|[*_`]", "", m.group(1)).strip(" .")) [0] if m else ""
    words = b.split()
    return "" if not words or words[0].lower().rstrip(",") in TIPS or not words[0][0].isupper() else " ".join(words[:4])


def _fix(text):
    """The prompt file has broken pound signs in places (UTF-8 read as Latin-1, or U+FFFD); restore them."""
    return re.sub("\u00c2\u00a3|\ufffd(?=[0-9])", "\u00a3", text)


def analyze(text, target):
    """{mentioned, cited, position, others}. position = place among the answer's list items (None if named only in
    prose); cited = the answer links this product's page or its domain."""
    hit = lambda s: bool(match_response(s, [target])["mentions"])  # noqa: E731
    site, url = target["site"], target["url"]
    cited = bool(site) and any(host(u) == site or (url and url_key(u) == url_key(url)) for u in cited_urls(text))
    items = [m.group(1) for m in map(LIST_ITEM_RE.match, (text or "").splitlines()) if m]
    ours = [hit(it) or (bool(site) and site in it.lower()) for it in items]
    position = ours.index(True) + 1 if True in ours else None
    brand = norm(target["brand"])
    others = [b for it, o in zip(items, ours) if not o and (b := _brand(it)) and norm(b) != brand]
    return {"mentioned": hit(text) or cited or position is not None, "cited": cited, "position": position, "others": others}


def _summary(results, asked, partial=False):
    n = len(results)
    pos = [r["position"] for r in results if r["position"]]
    named = Counter(x for r in results for x in dict.fromkeys(b.title() if b.islower() else b for b in r["others"]))
    out = {"asked": n, "questions": asked, "mentioned": sum(r["mentioned"] for r in results),
           "cited": sum(r["cited"] for r in results), "top3": sum(p <= 3 for p in pos),
           "best_position": min(pos) if pos else None, "partial": partial or n < asked,
           "brands_named_instead": [{"brand": b, "count": c} for b, c in named.most_common(8)]}
    out["mention_rate"] = round(out["mentioned"] / n, 4) if n else None
    return out


def check(rec, lang, factory=harness.make_adapter, now=time.time):
    """Ask each keyed model the questions; `factory(provider, model)` returns an adapter (tests pass a fake)."""
    lang = lang if lang in ("en", "es") else "en"
    live = [m for m in MODELS if os.environ.get(m[2])]
    if not live:
        return {"available": False, "reason": "no_api_key"}
    target, qs = _target(rec), questions(rec, lang)
    if not qs:
        return {"available": False, "reason": "no_questions"}
    # everything the answers are judged against is in the key, so a caller cannot poison another product's cache
    key = (target["site"] + (url_key(target["url"])[len(target["site"]):] if target["url"] else ""), lang,
           norm(target["brand"]), norm(target["name"]), tuple(target["aliases"]), tuple(q["id"] for q in qs))
    today = datetime.now(timezone.utc).date().isoformat()
    with _lock:
        if _day["date"] != today:
            _day.update(date=today, spent=0.0)
        daily = float(os.environ.get("VISIBILITY_LIVE_DAILY_USD") or 1.0)
        cap = min(float(os.environ.get("VISIBILITY_LIVE_MAX_USD") or 0.05), max(0.0, daily - _day["spent"]))
        _day["spent"] += cap  # reserve; the unused part is refunded below
    budget = Budget(cap, json.loads((ROOT / "prices.json").read_text(encoding="utf-8"))["models"])
    models, notes, cached, capped = {}, [], [], False
    for prov, model, _ in live:
        name = f"{prov}:{model}"
        hit = _cache.get(key + (name,))
        if hit and now() - hit[0] < TTL:
            models[name] = hit[1]
            cached.append(name)
            continue
        if capped:
            notes.append(f"{name} was not asked: spend cap reached.")
            continue
        try:
            adapter = factory(prov, model)
        except Exception as e:  # e.g. SDK not installed
            notes.append(f"{name} unavailable ({type(e).__name__}).")
            continue
        results, err = [], None
        for q in qs:
            try:
                budget.check(model, harness.DEFAULT_SYSTEM, q["text"], MAX_TOKENS)
            except BudgetExceeded:
                capped = True
                break
            try:
                out = adapter.complete(harness.DEFAULT_SYSTEM, q["text"], 0.0, MAX_TOKENS)
            except Exception as e:  # one provider failing must not sink the other
                err = type(e).__name__
                break
            budget.charge(model, out)
            results.append(analyze(out["text"], target))
        if not results:
            notes.append(f"{name} gave no answers ({'call failed: ' + err if err else 'spend cap reached'}).")
            continue
        models[name] = summ = _summary(results, len(qs), partial=capped or bool(err))
        if not summ["partial"]:
            while len(_cache) >= MAX_CACHE:
                _cache.pop(next(iter(_cache)))  # oldest first
            _cache[key + (name,)] = (now(), summ)
    with _lock:
        if _day["date"] == today:  # a refund after UTC midnight belongs to the old day
            _day["spent"] = max(0.0, _day["spent"] - (cap - budget.spent))
    if not models:
        return {"available": False, "reason": "spend_cap" if capped else "model_error",
                "cost_usd": round(budget.spent, 6), "caveats": notes}
    partial = [m for m, s in models.items() if s["partial"]]
    caveats = [f"These are answers we observed just now. {len(qs)} shopping questions per assistant is a small sample, "
               "not a ranking guarantee or a prediction of sales, and answers vary between runs."]
    if partial:
        caveats.append(f"Partial results (a spend cap or an error stopped the run): {', '.join(partial)}.")
    if cached:
        caveats.append(f"Reused from the last 24 hours, no new spend: {', '.join(cached)}.")
    return {"available": True, "models": models, "questions_used": [{"id": q["id"], "text": q["text"]} for q in qs],
            "cost_usd": round(budget.spent, 6), "caveats": caveats + notes}


@router.post("/visibility/live")
def visibility_live(request: Request, payload: dict = Body(...)):
    """{product: <audited record from POST /v1/audits>, language} -> per-model mention results (see check())."""
    try:
        from profile_api import rate_limit
        rate_limit(request, "visibility_live", "VISIBILITY_LIVE_RATE_LIMIT", 3)
    except ImportError:
        pass
    rec = payload.get("product")
    if not isinstance(rec, dict) or not isinstance(rec.get("identity"), dict):
        raise HTTPException(422, "bad_product: send the audited record as {product: ...}")
    t = _target(rec)
    if not (t["brand"] or t["name"] or t["site"]):
        raise HTTPException(422, "bad_product: the record has no brand, name or site to look for")
    return check(rec, str(payload.get("language") or "en"))
