"""Merchant shirt audit (TEAM-30): a product URL, page HTML/text, or a draft listing -> facts with evidence,
listing-quality rank among comparable shirts, side-by-side table, and a ranked action plan.

Reuses /v1/extract (main.extract), analysis.peers/gaps and the dashboard_api dataset/signals loaders; extraction
and peer matching are not duplicated here. Also serves the React UI build (web/dist) at "/".
Honesty rules: actions never state product facts we did not observe ("add if true"), never claim an effect on
search/AI ranking, and "not found on the page" is never reported as "the product lacks it".
"""
import html as htmllib
import json
import statistics
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError

import dashboard_api as dash
from analysis.gaps import ATTRIBUTES, analyze, attributes_present, description_chars
from analysis.peers import find_peers, get, price

router = APIRouter()
WEB = Path(__file__).resolve().parents[1] / "web" / "dist"  # Vite build output (npm run build in web/)
K = 10          # most-similar shirts listed as "similar products"
RANK_K = 24     # comparable shirts ranked together with the target (up to 25 in total)
TOP = 10        # the action plan is derived from the top-ranked comparable shirts
TABLE_PEERS = 5
W_FACTS, W_DESC, W_SD = 60, 20, 20
FORMULA = ("Listing quality = 60 x (key facts stated / 23) + 20 x min(1, description characters / group median) "
           "+ 20 x (schema.org Product and Offer markup present / 2). It ranks page completeness among comparable "
           "shirts only; it is not an AI-visibility or search rank.")
FORMULA_DRAFT = ("Draft listing quality = 75 x (key facts stated / 23) + 25 x min(1, description characters / group "
                 "median). Structured data is not scored for drafts. Not an AI-visibility or search rank.")
LABELS = {
    "identity.brand": "Brand", "identity.audience": "Who it's for (men, women, unisex)",
    "identity.subcategory": "Category", "content.full_description": "Product description",
    "materials.primary_material": "Main material", "materials.material_percentages": "Material composition (%)",
    "materials.fabric_type": "Fabric type (e.g. jersey, piqué)", "materials.fabric_weight_gsm": "Fabric weight (GSM)",
    "materials.stretch": "Stretch", "materials.texture": "Texture", "fit_and_style.fit": "Fit",
    "fit_and_style.neckline": "Neckline", "fit_and_style.collar_type": "Collar type",
    "fit_and_style.sleeve_length": "Sleeve length", "fit_and_style.shirt_length": "Length",
    "fit_and_style.pattern": "Pattern", "fit_and_style.style": "Style", "variants.colors": "Colours",
    "variants.sizes": "Sizes", "commerce.price": "Price", "commerce.currency": "Currency",
    "commerce.availability": "Stock availability", "commerce.gtin": "Barcode (GTIN/EAN)",
}
READABLE = {"commerce.price", "commerce.currency", "commerce.availability"}
EFFORT = {"commerce.gtin": "med", "variants.sizes": "med", "variants.colors": "med"}
SEO_SAFE = "Adds information only; does not change your URL or title."


def label(field):
    return LABELS.get(field, field.split(".")[-1].replace("_", " ").capitalize())


def present(v):
    return v not in (None, "", [], {})


def display(field, v):
    if field == "variants.colors":
        return [c.get("original_color_name") or c.get("normalized") for c in v if isinstance(c, dict)] or v
    if field == "content.full_description":
        return len(v)  # character count; the UI formats it
    return v


def action(kind, priority, title, why, evidence, lbl, effort, field=None, seo=SEO_SAFE):
    """title/why are English copy for API users; the UI renders its own EN/ES text from kind + field + evidence."""
    return {"id": f"{kind}:{field or kind}", "kind": kind, "priority": priority, "title": title, "why": why,
            "evidence": evidence, "label": lbl, "effort": effort, "field": field, "seo_note": seo}


def predictions(raw, norm):
    """Hook for model predictions of attributes not stated on the page: {field: {value, confidence, model}}.
    Empty until the fine-tuned model is wired (MODEL_BACKEND=qwen). Predictions are never reported as page facts."""
    return {}


def price_position(target, peers):
    """Price vs the signals peer group (same product type, language, observed currency), else vs comparable shirts."""
    p, cur = price(target), get(target, "commerce", "currency")
    if not (p and cur):
        return {"available": False, "price": p, "currency": cur, "reason": "price or currency not found on the page"}
    group = f"{get(target, 'identity', 'product_type')}|{get(target, 'source', 'language')}|{cur}|observed"
    st = next((s["peer"] for s in dash.signals().values() if (s.get("peer") or {}).get("group") == group), None)
    if st:
        src, n, p25, p50, p75 = "signals", st["n"], st["p25"], st["p50"], st["p75"]
    else:
        vals = sorted(price(x) for x in peers if price(x) and get(x, "commerce", "currency") == cur)
        if len(vals) < 3:
            return {"available": False, "price": p, "currency": cur, "peer_count": len(vals),
                    "reason": "fewer than 3 comparable products with a price in the same currency"}
        q = statistics.quantiles(vals, n=4, method="inclusive")
        src, n, p25, p50, p75 = "peers", len(vals), q[0], q[1], q[2]
    pos = "below" if p < p25 else "above" if p > p75 else "within"
    return {"available": True, "price": p, "currency": cur, "source": src, "peer_count": n,
            "p25": round(p25, 2), "median": round(p50, 2), "p75": round(p75, 2), "position": pos}


def weights(with_sd):
    """Drafts have no page markup yet, so they are ranked on facts and description only (75/25)."""
    return {"facts": W_FACTS, "description": W_DESC, "structured_data": W_SD} if with_sd else \
        {"facts": 75, "description": 25, "structured_data": 0}


def quality(rec, desc_ref, with_sd=True):
    """Transparent listing-quality components (0-100); every component is returned so the UI shows the formula."""
    w = weights(with_sd)
    facts_n = sum(attributes_present(rec).values())
    chars = description_chars(rec)
    sd = rec.get("structured_data") or {}
    sd_n = sum(bool(sd.get(f)) for f in ("product_schema_present", "offer_schema_present"))
    points = {"facts": round(w["facts"] * facts_n / len(ATTRIBUTES), 1),
              "description": round(w["description"] * (min(1.0, chars / desc_ref) if desc_ref else 0.0), 1),
              "structured_data": round(w["structured_data"] * sd_n / 2, 1)}
    return {"score": round(sum(points.values()), 1), "points": points, "facts_stated": facts_n,
            "facts_checked": len(ATTRIBUTES), "description_chars": chars, "description_ref": desc_ref,
            "structured_data_flags": sd_n}


def rank(target, recs, with_sd=True):
    """Rank the target among comparable shirts (analysis.peers hard filters: type, language, price band, audience).
    Returns (rank dict, comparable shirts ordered by listing quality)."""
    group = [p for _, p in find_peers(target, recs, RANK_K)]
    ref = statistics.median([description_chars(x) for x in group + [target]])
    scored = sorted(((quality(x, ref, with_sd), x) for x in group), key=lambda q: -q[0]["score"])
    tq = quality(target, ref, with_sd)
    pos = 1 + sum(q["score"] > tq["score"] for q, _ in scored)
    board = [{**dash.summary(x), "url": get(x, "source", "url"), "is_you": False, **q} for q, x in scored]
    board.insert(pos - 1, {**dash.summary(target), "url": get(target, "source", "url"), "is_you": True, **tq})
    return {"position": pos, "total": len(group) + 1, "score": tq["score"], "components": tq,
            "formula": FORMULA if with_sd else FORMULA_DRAFT, "kind": "listing_quality", "weights": weights(with_sd),
            "note": "Listing quality rank; an AI-visibility rank comes after the benchmark.",
            "leaderboard": board}, [x for _, x in scored]


def comparison_table(target, top):
    """Target vs the top-ranked comparable shirts on the union of attributes any of them states (nulls omitted)."""
    shirts = [(True, target)] + [(False, p) for p in top[:TABLE_PEERS]]
    fields = [f"{s}.{k}" for s, k in ATTRIBUTES if any(present(get(x, s, k)) for _, x in shirts)]
    rows = [{**dash.summary(x), "url": get(x, "source", "url"), "is_you": you,
             "values": {f: display(f, get(x, *f.split("."))) for f in fields if present(get(x, *f.split(".")))}}
            for you, x in shirts]
    return {"fields": fields, "labels": {f: label(f) for f in fields}, "rows": rows}


def build_actions(target, metrics, issues, pp):
    """Ranked: missing attributes most top-ranked shirts state > description > structured data > price > language."""
    n = metrics["peer_count"]
    acts = []
    for it in issues:
        f = it["field"]
        if it["type"] == "OBSERVED_FACT" and f in LABELS:
            c = it["evidence"]["count"]
            ev = {"peers_with_attribute": c, "of": n, "peer_ids": it["evidence"]["peers_with_attribute"]}
            if f in READABLE:  # a shop page almost always shows these; the gap is that we couldn't read them
                acts.append(action(
                    "missing_attribute", 1, f"Make your {label(f).lower()} readable by machines",
                    f"We couldn't read a {label(f).lower()} from your page's text or markup; it may be shown in a way "
                    f"tools can't read. {c} of the {n} top-ranked similar shirts expose it.",
                    {**ev, "readable": True}, "OBSERVED_FACT", "med", f,
                    "Markup or text change only; your URL and title stay the same."))
                continue
            acts.append(action(
                "missing_attribute", 1, f"Add {label(f).lower()}, if you can verify it",
                f"We couldn't find {label(f).lower()} on your page. {c} of the {n} top-ranked similar shirts state it.",
                ev, "OBSERVED_FACT", EFFORT.get(f, "low"), f))
    acts.sort(key=lambda a: -a["evidence"]["peers_with_attribute"])
    d = metrics["description_chars"]
    if d["peer_median"] and d["target"] < 0.5 * d["peer_median"]:
        acts.append(action(
            "description", 2, "Describe the product in more detail, using facts you can verify",
            f"Your description is {d['target']} characters; the median for the {n} top-ranked similar shirts is "
            f"{int(d['peer_median'])}. Length alone is not the goal: add concrete facts shoppers ask about.",
            {"target_chars": d["target"], "peer_median_chars": d["peer_median"], "of": n},
            "OBSERVED_FACT", "med", "content.full_description"))
    for f, v in metrics["structured_data"].items():
        if not v["target"] and (f == "product_schema_present" or (n and v["peers_present"] / n > 0.5)):
            what = {"product_schema_present": "Product", "offer_schema_present": "Offer (price and stock)",
                    "product_group_present": "ProductGroup (variants)"}[f]
            acts.append(action(
                "structured_data", 3, f"Add schema.org {what} markup that matches your visible page",
                f"We found no {what} structured data on your page"
                + (f"; {v['peers_present']} of the {n} top-ranked similar shirts have it." if n else "."),
                {"peers_present": v["peers_present"], "of": n}, "OBSERVED_FACT", "med", f"structured_data.{f}",
                "Machine-readable markup only; your visible page and URL stay the same."))
    if pp.get("available") and pp["position"] != "within":
        acts.append(action(
            "price", 4, "Check your price is correct and the page explains it",
            f"Your price {pp['price']:g} {pp['currency']} is {pp['position']} the middle half of "
            f"{pp['peer_count']} comparable listings ({pp['p25']:g} to {pp['p75']:g} {pp['currency']}). "
            "This is positioning evidence, not a recommended price.",
            {k: pp[k] for k in ("peer_count", "p25", "median", "p75", "source")},
            "OBSERVED_FACT", "low", "commerce.price", "No page change needed unless you decide to change it."))
    if not get(target, "source", "language"):
        acts.append(action(
            "language", 5, "Declare your page language", "We couldn't detect a language (no <html lang>), so "
            "we can't compare you with products in your language.", {}, "UNKNOWN", "low", "source.language"))
    return acts


def facts(target, norm):
    ev = {}
    for e in norm.get("evidence") or []:
        ev.setdefault(e.get("field"), e)
    out = []
    for s, k in ATTRIBUTES:
        f, v = f"{s}.{k}", get(target, s, k)
        if present(v) and f != "content.full_description":  # a length is a metric, not a product fact
            e = ev.get(f) or {}
            out.append({"field": f, "label": label(f), "value": display(f, v), "source_text": e.get("source_text"),
                        "source_location": e.get("source_location")})
    return out


def draft_request(main, payload):
    """A draft listing (title, description, optional price/currency; not yet published) as an ExtractRequest.
    The draft is wrapped in a minimal page so extract/normalize run unchanged; that JSON-LD is ours, so the
    audit clears the structured-data flags afterwards (a draft has no markup of its own)."""
    node = {"@context": "https://schema.org", "@type": "Product", "name": str(payload.get("title")).strip()[:500],
            "description": str(payload.get("text") or "")[:200_000]}
    if payload.get("price") not in (None, "") and payload.get("currency"):
        node["offers"] = {"@type": "Offer", "price": str(payload["price"]), "priceCurrency": str(payload["currency"])[:3]}
    lang = payload.get("language")
    ld = json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
    t = htmllib.escape(node["name"])
    page = (f'<html lang="{htmllib.escape(str(lang or ""))}"><head><title>{t}</title>'
            f'<script type="application/ld+json">{ld}</script></head><body><h1>{t}</h1></body></html>')
    return main.ExtractRequest(html=page, language=lang)


@router.post("/v1/audit")
def audit(payload: dict = Body(...)):
    import main  # lazy: main imports this module
    try:
        req = draft_request(main, payload) if payload.get("title") else main.ExtractRequest(**payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"])
    except TypeError as e:
        raise HTTPException(422, str(e).splitlines()[0])
    ex = main.extract(req)
    norm, raw = ex["normalized"], ex["raw"]
    draft = bool(payload.get("title"))
    if draft:
        norm["structured_data"] = {"product_schema_present": False, "offer_schema_present": False,
                                   "product_group_present": False, "raw_json_ld": []}
    target = dash.adapt(norm)
    if not (get(target, "structured_data", "product_schema_present") or price(target)
            or get(target, "identity", "product_type")):
        raise HTTPException(422, "not_a_product_page: we couldn't find a product name, price or product type")
    url = get(target, "source", "url")
    recs = [r for r in dash.records() if not url or get(r, "source", "url") != url]  # the page itself is not its own peer
    matched = find_peers(target, recs, K)
    rk, ranked = rank(target, recs, with_sd=not draft)
    top = ranked[:TOP]
    res = analyze(target, top)  # the plan: what the top-ranked comparable shirts state that this one doesn't
    m = res["metrics"]
    pp = price_position(target, ranked)
    acts = [a for a in build_actions(target, m, res["issues"], pp)
            if not (draft and a["kind"] == "structured_data")]  # a draft's markup is not assessed
    counts = [sum(attributes_present(p).values()) for p in top]
    cov = m["attribute_peer_coverage"]
    pred = predictions(raw, norm)
    not_found = sorted(({"field": f, "label": label(f), "peers_with": cov[f]["present"], "of": cov[f]["of"],
                         "predicted": pred.get(f)} for f, ok in attributes_present(target).items() if not ok),
                       key=lambda x: -x["peers_with"])
    vis = dash.visibility()
    facts_found = sum(attributes_present(target).values())
    return {
        "product": {**dash.summary(target), "url": get(target, "source", "url"),
                    "image": (raw.get("image_urls") or [None])[0], "draft": draft},
        "facts": facts(target, norm),
        "not_found": not_found,
        "summary": {"facts_found": facts_found, "attributes_checked": len(ATTRIBUTES),
                    "top_median_facts": statistics.median(counts) if counts else None,
                    "top_count": len(top), "top_missing": [a["field"] for a in acts if a["kind"] == "missing_attribute"][:3],
                    "price_position": pp.get("position")},
        "rank": {k: v for k, v in rk.items() if k != "leaderboard"},
        "leaderboard": rk["leaderboard"],
        "table": comparison_table(target, ranked),
        "context": {"language": get(target, "source", "language"), "currency": get(target, "commerce", "currency"),
                    "merchant": get(target, "source", "merchant_domain"), "dataset_size": len(recs),
                    "quality_status": norm.get("quality_status")},
        "peers": [{**dash.summary(p), "url": get(p, "source", "url"), "match_score": s,
                   "facts_found": sum(attributes_present(p).values())} for s, p in matched],
        "comparison": {"basis": "top_ranked", "of": len(top),
                       "facts": {"target": facts_found, "top_median": statistics.median(counts) if counts else None,
                                 "of": len(ATTRIBUTES)},
                       "description_chars": {"target": description_chars(target),
                                             "top_median": m["description_chars"]["peer_median"]},
                       "structured_data": m["structured_data"],
                       "reviews": {"target_has_rating": get(target, "commerce", "rating") is not None,
                                   "top_with_rating": sum(get(p, "commerce", "rating") is not None for p in top)}},
        "price_position": pp,
        "actions": acts,
        "unknowns": [i["statement"] for i in res["issues"] if i["type"] in ("UNKNOWN", "SUPPORTED_HYPOTHESIS")],
        "visibility": {"available": isinstance(vis, dict) and bool(vis.get("models"))},
        "conflicts": norm.get("conflicts") or [],
    }


NEW_FIELDS = ["materials.fabric_type", "materials.texture", "fit_and_style.shirt_length", "fit_and_style.style",
              "care", "variants.sizes", "fit_and_style.collar_type"]  # TEAM-37 (dataset/build/fill_null_fields.py)
MODEL_LABELS = {"all_null_baseline": "All-null baseline", "base_zero_shot": "Base Qwen (zero-shot)",
                "base_qwen_0_5b": "Base Qwen 0.5B", "finetuned": "Fine-tuned Qwen", "ft_qwen_0_5b": "Fine-tuned Qwen 0.5B",
                "ft_qwen_1_5b": "Fine-tuned Qwen 1.5B", "gpt-4o-mini": "GPT-4o mini", "claude-haiku-4-5": "Claude Haiku 4.5"}


@router.get("/v1/model-comparison")
def model_comparison():
    """Read-only: extraction-model comparison from PRODUCTLENS_COMPARISON (default train/runs/comparison.json).
    Accepts {"models": {key: summary}} or train/eval.py's raw output (model keys at top level). Summaries are
    eval.py summarize() dicts, optionally with by_language, cost_per_1k_usd, latency_ms. Nothing is computed here."""
    rep = dash._cached("PRODUCTLENS_COMPARISON", "train/runs/comparison.json",
                       lambda p: json.loads(p.read_text(encoding="utf-8")), {})
    if not isinstance(rep, dict):
        rep = {}
    models = rep.get("models") if isinstance(rep.get("models"), dict) else \
        {k: v for k, v in rep.items() if isinstance(v, dict) and "non_null_acc" in v}
    models = {k: {**v, "label": v.get("label") or MODEL_LABELS.get(k, k)} for k, v in models.items() if isinstance(v, dict)}
    return {"available": bool(models), "sample": bool(rep.get("sample")), "generated_at": rep.get("generated_at"),
            "test": rep.get("test") if isinstance(rep.get("test"), dict) else {}, "models": models,
            "new_fields": NEW_FIELDS}


@router.get("/", include_in_schema=False)
def index():
    if not (WEB / "index.html").is_file():
        raise HTTPException(503, "web UI not built: run npm ci && npm run build in web/")
    return FileResponse(WEB / "index.html")


@router.get("/assets/{name}", include_in_schema=False)
def asset(name: str):
    d = WEB / "assets"
    if not d.is_dir() or name not in {p.name for p in d.iterdir() if p.is_file()}:
        raise HTTPException(404, "not found")
    return FileResponse(d / name)
