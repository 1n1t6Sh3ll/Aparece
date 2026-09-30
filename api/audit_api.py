"""Merchant shirt audit (TEAM-30): a product URL, page HTML/text, or a draft listing -> facts with evidence,
listing-quality rank among comparable shirts, side-by-side table, and a ranked action plan.

Reuses /v1/extract (main.extract), analysis.peers/gaps and the dashboard_api dataset/signals loaders; extraction
and peer matching are not duplicated here. Also serves the React UI build (web/dist) at "/".
Honesty rules: actions never state product facts we did not observe ("add if true"), never claim an effect on
search/AI ranking, and "not found on the page" is never reported as "the product lacks it".
"""
import html as htmllib
import json
import re
import statistics
from pathlib import Path
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import ValidationError

import dashboard_api as dash
import safe_fetch
from analysis.gaps import ATTRIBUTES, INTENTS, analyze, attributes_present, description_chars, description_coverage, description_text
from analysis.peers import SLEEVE_FILL, find_peers, get, price, unknown_sleeve
from normalize import PRODUCT_TYPE, SHIRT_TYPES, lang_code, match_lookup, shirt_type  # dataset/collect (on path via dashboard_api)
from tools.linkcheck import status as link

router = APIRouter()
WEB = Path(__file__).resolve().parents[1] / "web" / "dist"  # Vite build output (npm run build in web/)
K = 10          # most-similar shirts listed as "similar products"
RANK_K = 24     # comparable shirts ranked together with the target (up to 25 in total)
TOP = 10        # the action plan is derived from the top-ranked comparable shirts
TABLE_PEERS = 5
BASE_WEIGHTS = {"facts": 60, "description": 20, "structured_data": 20}  # renormalized over the components used
FACT_FIELDS = [f"{s}.{k}" for s, k in ATTRIBUTES if (s, k) != ("content", "full_description")]  # the text is scored once
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


SD_FLAGS = ("product_schema_present", "offer_schema_present")


def sd_known(rec):
    """Structured-data status is known only for records whose markup was read (live pages, normalized rows).
    Drafts and ground-truth dataset rows carry no status."""
    sd = rec.get("structured_data")
    return isinstance(sd, dict) and all(isinstance(sd.get(f), bool) for f in SD_FLAGS)


def weights(recs):
    """BASE_WEIGHTS over the components known for every record compared (target and peers alike); a component
    unknown for any of them is dropped for all and the rest renormalized to 100, so nobody gets free points."""
    use = {k: w for k, w in BASE_WEIGHTS.items() if k != "structured_data" or all(sd_known(r) for r in recs)}
    total = sum(use.values())
    return {k: round(100 * use.get(k, 0) / total, 2) for k in BASE_WEIGHTS}


def formula(w):
    sd = (f" + {w['structured_data']:g} x (schema.org Product and Offer markup found / 2)" if w["structured_data"]
          else "; structured data is not scored because it is unknown for the dataset shirts (or for a draft)")
    return (f"Listing quality = {w['facts']:g} x (key facts stated / {len(FACT_FIELDS)}) + {w['description']:g} x "
            f"(shopper questions the description answers in sentences and that match a verified fact / "
            f"{len(INTENTS)}, each counted once; keyword lists and repeated text do not count){sd}. Drafts and pages use the same formula. Ties share a position. It ranks listing "
            "completeness among comparable shirts only; it is not an AI-visibility or search rank.")


def quality(rec, w):
    """Transparent listing-quality components (0-100); every component is returned so the UI shows the formula."""
    facts_n = sum(attributes_present(rec)[f] for f in FACT_FIELDS)
    cov = description_coverage(rec)
    sd = rec.get("structured_data") or {}
    sd_n = sum(bool(sd.get(f)) for f in SD_FLAGS)
    points = {"facts": round(w["facts"] * facts_n / len(FACT_FIELDS), 1),
              "description": round(w["description"] * cov["value"], 1),
              "structured_data": round(w["structured_data"] * sd_n / 2, 1)}
    return {"score": round(sum(points.values()), 1), "points": points, "facts_stated": facts_n,
            "facts_checked": len(FACT_FIELDS), "description_chars": description_chars(rec),
            "description_intents": cov["intents"], "description_ref": cov["of"],
            "description_repetition": cov["repetition"], "structured_data_flags": sd_n}


def peer_key(target, recs):
    """The record used to match peers, plus a note. Dataset rows often have no recorded currency, and the
    same-currency hard filter would then leave a priced page with no peers; in that case peers are matched with
    the currency unknown (analysis.peers then skips the price band). Only matching changes, never the scored facts."""
    if not get(target, "commerce", "currency") or find_peers(target, recs, 1):
        return target, None
    alt = {**target, "commerce": {**(target.get("commerce") or {}), "currency": None}}
    if not find_peers(alt, recs, 1):
        return target, None
    return alt, ("Comparable shirts in our dataset have no recorded currency, so they were matched on type, language "
                 "and audience without a price band; prices were not compared.")


MIN_PEERS = 10  # fewer comparable shirts than this: widen the match step by step


def peer_group(match, recs, k, types=None):
    """find_peers, or (types given) the union over those shirt types, most comparable first."""
    if not types:
        return find_peers(match, recs, k)
    out = []
    for t in types:
        out += find_peers({**match, "identity": {**(match.get("identity") or {}), "product_type": t}}, recs, k)
    out.sort(key=lambda sp: (-sp[0], str(sp[1].get("product_id") or "")))
    return out[:k]


def widen(match, recs):
    """(match, types, step, note). Steps until MIN_PEERS comparable shirts match: exact -> without the price band
    -> without the sleeve length -> any shirt type. Only matching changes; every row is scored with one formula."""
    no_price = {**match, "commerce": {**(match.get("commerce") or {}), "price": None, "currency": None}}  # prices not compared
    no_sleeve = {**no_price, "fit_and_style": {**(no_price.get("fit_and_style") or {}), "sleeve_length": None}}
    steps = [("exact", match, None, None)]
    if price(match) or get(match, "commerce", "currency"):
        steps.append(("no_price_band", no_price, None, "without the price band"))
    if get(match, "fit_and_style", "sleeve_length"):
        steps.append(("no_sleeve", no_sleeve, None, "without the price band or sleeve length"
                      if price(match) else "without the sleeve length"))
    steps.append(("any_shirt_type", no_sleeve, sorted(SHIRT_TYPES), "across all shirt types, without the price band "
                  "or sleeve length"))
    for i, (step, m, types, how) in enumerate(steps):
        n = len(peer_group(m, recs, RANK_K, types))
        if n >= MIN_PEERS or i == len(steps) - 1:
            if n == 0 or step == "exact":
                return match, None, "exact", None
            return m, types, step, (f"Fewer than {MIN_PEERS} shirts matched exactly, so comparable shirts were matched "
                                    f"{how} ({n} found). The same scoring formula applies to every shirt in the ranking.")


def rank(target, recs, match=None, types=None):
    """Rank the target among comparable shirts (analysis.peers hard filters). `match` (default: target) is the
    record used for peer matching. Ties share a position ("position".."position_to"); inside a tie the order is
    neutral (by product_id), never in the target's favour. Returns (rank dict, shirts ordered by quality)."""
    group = [p for _, p in peer_group(match or target, recs, RANK_K, types)]
    w = weights(group + [target])
    tq = quality(target, w)
    rows = [(quality(x, w), x, False) for x in group] + [(tq, target, True)]
    rows.sort(key=lambda r: (-r[0]["score"], str(r[1].get("product_id") or "")))
    pos = 1 + next(i for i, r in enumerate(rows) if r[2])
    first = 1 + sum(q["score"] > tq["score"] for q, _, _ in rows)
    last = sum(q["score"] >= tq["score"] for q, _, _ in rows)
    board = [{**dash.summary(x), "url": get(x, "source", "url"), **(link.flag(x) if not you else {}), "is_you": you, **q} for q, x, you in rows]
    return {"position": pos, "position_from": first, "position_to": last, "tied": last - first,
            "total": len(group) + 1, "score": tq["score"], "components": tq, "formula": formula(w),
            "kind": "listing_quality", "weights": w,
            "price_band": bool(price(match or target) and get(match or target, "commerce", "currency")),
            "note": "Listing quality rank; an AI-visibility rank comes after the benchmark.",
            "leaderboard": board}, [x for _, x, you in rows if not you]


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


DRAFT_KEYS = ("title", "description", "details")
TEXT_KEYS = DRAFT_KEYS + ("text", "language", "currency")
CUR = {"€": "EUR", "$": "USD", "£": "GBP"}  # a bare "$" is read as USD only because the user typed "$"
ISO_4217 = set("""AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BZD CAD
CDF CHF CLP CNY COP CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL GHS GIP GMD GNF GTQ GYD HKD HNL
HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD
MMK MNT MOP MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR
SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU UZS VED
VES VND VUV WST XAF XCD XCG XOF XPF YER ZAR ZMW ZWG ZWL""".split())
NUM = r"(\d+(?:[.,]\d{1,2})?)"
PRICE_RE = re.compile(rf"(€|\$|£|\b[A-Z]{{3}})\s?{NUM}\b(?!\s?%)|\b{NUM}\s?(€|\$|£|[A-Z]{{3}}\b)")  # codes: uppercase
STOCK = [("out_of_stock", r"\bout of stock\b|\bnot in stock\b|\bsold out\b|\bagotad[oa]s?\b|\bsin stock\b|"
                          r"\bsin existencias?\b|\bfuera de stock\b"),
         ("preorder", r"\bpre-?orders?\b|\bpreventa\b"), ("backorder", r"\bback-?orders?\b"),
         ("in_stock", r"\bin stock\b|\bavailable now\b|\ben stock\b|\ben existencias?\b")]
LANG_WORDS = {  # draft language when none is given: the language with more of these words wins; a tie is unknown
    "en": {"the", "with", "for", "and", "of", "in", "our", "cotton", "shirt", "tee", "sleeve", "sleeves", "short", "long",
           "men", "women", "fit", "neck", "crew", "soft", "heavyweight", "slim", "relaxed", "boxy", "printed"},
    "es": {"de", "con", "para", "y", "el", "la", "los", "las", "algodón", "algodon", "camiseta", "camisa", "playera",
           "remera", "manga", "mangas", "hombre", "mujer", "cuello", "corte", "suave", "estampada", "talla"}}


def is_draft(payload):
    """Draft mode: any of title/description/details, or plain text without a URL or HTML."""
    return any(payload.get(k) for k in DRAFT_KEYS) or bool(payload.get("text") and not (payload.get("url") or payload.get("html")))


def detect_language(text):
    words = re.findall(r"[a-záéíóúñü]+", (text or "").lower())
    n = {k: sum(w in v for w in words) for k, v in LANG_WORDS.items()}
    return "es" if n["es"] > n["en"] else "en" if n["en"] > n["es"] else None


def check_price(v):
    """A draft price: a number or numeric text greater than 0, else 422."""
    try:
        p = None if isinstance(v, bool) or not isinstance(v, (int, float, str)) else float(str(v).strip().replace(",", "."))
    except ValueError:
        p = None
    if p is None or not 0 < p < 1e9:
        raise HTTPException(422, f"invalid_price: the price must be a number greater than 0 (got {str(v)[:20]!r})")
    return round(p, 2)


def check_currency(v):
    c = v.strip().upper() if isinstance(v, str) else None
    if c not in ISO_4217:
        raise HTTPException(422, "invalid_currency: use a 3-letter ISO 4217 code such as USD, EUR or MXN "
                                 f"(got {str(v)[:20]!r})")
    return c


def text_price(text):
    """(price, currency, matched text) for the first number next to a currency symbol or ISO 4217 code in the text."""
    for m in PRICE_RE.finditer(text):
        sym = m.group(1) or m.group(4)
        cur = CUR.get(sym) or (sym.upper() if sym.upper() in ISO_4217 else None)
        if cur:
            return (m.group(2) or m.group(3)).replace(",", "."), cur, m.group(0)
    return None, None, None


def draft_fields(payload):
    """{title, description, price?, currency?, availability?, language, sources} from separate fields or plain text
    (first non-empty line = title, rest = description; details are appended). Nothing beyond the text is inferred:
    price/currency come from the fields or an explicit symbol/code next to a number in the text, availability only
    from explicit stock words, language from the field or, if absent, the words used. Bad types or values -> 422."""
    for k in TEXT_KEYS:
        if payload.get(k) is not None and not isinstance(payload[k], str):
            raise HTTPException(422, f"invalid_field: {k} must be text")
    title, desc = (payload.get("title") or "").strip(), (payload.get("description") or "").strip()
    text = (payload.get("text") or "").strip()
    if text and not title:
        lines = [x.strip() for x in text.splitlines() if x.strip()]
        title, text = (lines[0], "\n".join(lines[1:])) if lines else ("", "")
    desc = "\n".join(x for x in (desc, text, (payload.get("details") or "").strip()) if x)
    body, src = f"{title}\n{desc}", {}
    price_ = None if payload.get("price") in (None, "") else check_price(payload["price"])
    cur = None if payload.get("currency") in (None, "") else check_currency(payload["currency"])
    if price_ is not None:
        src["commerce.price"] = (str(payload["price"]), "draft.price")
    if cur:
        src["commerce.currency"] = (payload["currency"], "draft.currency")
    if price_ is None:
        p, c, hit = text_price(body)
        if p:
            price_, src["commerce.price"] = check_price(p), (hit, "draft text")
            if not cur:
                cur, src["commerce.currency"] = c, (hit, "draft text")
    avail = next(((v, m.group(0)) for v, rx in STOCK for m in [re.search(rx, body, re.I)] if m), None)
    if avail:
        src["commerce.availability"] = (avail[1], "draft text")
    lang = lang_code(payload.get("language"))
    detected = not lang
    lang = lang or detect_language(body)
    return {"title": title[:500], "description": desc[:200_000], "price": price_, "currency": cur,
            "availability": avail[0] if avail else None, "language": lang, "language_detected": detected and bool(lang),
            "sources": src}


def draft_facts(norm, d):
    """Replace the commerce facts the wrapper page produced with exactly what the draft states, with the draft
    field or text as evidence (never the wrapper's schema.org markup)."""
    fields = ("commerce.price", "commerce.currency", "commerce.availability")
    norm["commerce"] = {**(norm.get("commerce") or {}), "price": d["price"], "currency": d["currency"],
                        "availability": d["availability"]}
    ev = [e for e in norm.get("evidence") or [] if e.get("field") not in fields]
    for f in fields:
        if f in d["sources"]:
            txt, loc = d["sources"][f]
            ev.append({"field": f, "value": norm["commerce"][f.split(".")[1]], "source_text": txt,
                       "source_location": loc, "method": "direct" if loc.startswith("draft.") else "rule",
                       "confidence": 1.0})
    norm["evidence"] = ev


def draft_request(main, d):
    """A draft listing (not yet published) as an ExtractRequest. The draft is wrapped in a minimal page so
    extract/normalize run unchanged; that JSON-LD is ours, so the audit clears the structured-data flags and
    replaces the commerce facts afterwards (draft_facts). Price is optional."""
    node = {"@context": "https://schema.org", "@type": "Product", "name": d["title"], "description": d["description"]}
    if d["price"] is not None and d["currency"]:
        node["offers"] = {"@type": "Offer", "price": str(d["price"]), "priceCurrency": d["currency"]}
    lang = d["language"]
    ld = json.dumps(node, ensure_ascii=False).replace("</", "<\\/")
    t = htmllib.escape(node["name"])
    page = (f'<html lang="{htmllib.escape(str(lang or ""))}"><head><title>{t}</title>'
            f'<script type="application/ld+json">{ld}</script></head><body><h1>{t}</h1></body></html>')
    return main.ExtractRequest(html=page, language=lang)


def infer_type(target, d):
    """Draft product type: normalize.py PRODUCT_TYPE rules over the title, then the description."""
    sleeve = get(target, "fit_and_style", "sleeve_length")
    for text in (d["title"], d["description"]):
        hit = match_lookup(text, PRODUCT_TYPE)
        if hit and shirt_type(hit[0][0], sleeve):
            return shirt_type(hit[0][0], sleeve)
    return None


# Shirt words normalize.PRODUCT_TYPE (EN/ES) does not cover: FR/DE/IT/PT and compounds. Same values as PRODUCT_TYPE.
EXTRA_SHIRT = [
    ("polo", r"\bpolo-?(?:shirts?|hemd(?:en)?)\b"),
    ("henley", r"\bhenley-?shirts?\b"),
    ("t_shirt", r"\btee-?shirts?\b|\bt-?shirts?\b|\bmagliett[ae]\b|\bt-?shirt-?\w+|\bcamisetas?\b|\btees?\b"),
    ("_shirt", r"\bchemises?\b|\b(?:ober)?hemd(?:en)?\b|\bcamici[ae]\b|\bcamisas?\b"),
]
SHIRT_TABLE = PRODUCT_TYPE + EXTRA_SHIRT
# Other apparel and common products (EN/ES/FR/DE/IT/PT): audited in full but not ranked (we rank shirts only).
NON_SHIRT = [
    ("hoodie", r"\bhood(?:ie|y)s?\b|\bhooded\b|\bsudaderas? con capucha\b|\bkapuzen\w*|\bfelpe? con cappuccio\b"),
    ("sweatshirt", r"\bsweat-?shirts?\b|\bcrewnecks? sweat|\bsudaderas?\b|\bsweats?\b|\bfelpas?\b|\bmoletons?\b"),
    ("sweater", r"\bsweaters?\b|\bjumpers?\b|\bjers[eé]is?\b|\bsu[eé]teres?\b|\bpull-?overs?\b|\bpulls?\b"
                r"|\bpullis?\b|\bmagliones?\b|\bcardigans?\b|\bstrickjacke\b"),
    ("jacket", r"\bjackets?\b|\bchaquetas?\b|\bcazadoras?\b|\bvestes?\b|\bjacken?\b|\bgiacc(?:a|he)\b"
               r"|\bjaquetas?\b|\bblazers?\b|\bbombers?\b"),
    ("coat", r"\bcoats?\b|\babrigos?\b|\bmanteaux?\b|\bm[aä]ntel\b|\bcappott[oi]\b|\bcasacos?\b|\bparkas?\b"),
    ("jeans", r"\bjeans\b|\bvaqueros?\b"),
    ("pants", r"\bpants\b|\btrousers\b|\bpantal[oó]n(?:es)?\b|\bpantalons?\b|\bhosen?\b|\bpantaloni\b"
              r"|\bcal[çc]as?\b|\bchinos?\b|\bjoggers?\b|\bleggings?\b"),
    ("shorts", r"\bshorts\b|\bbermudas?\b"),
    ("dress", r"\bdress(?:es)?\b|\bvestidos?\b|\brobes?\b|\bkleid(?:er)?\b|\babiti?\b"),
    ("skirt", r"\bskirts?\b|\bfaldas?\b|\bjupes?\b|\bgonnas?\b|\bsaias?\b"),
    ("socks", r"\bsocks?\b|\bcalcetines\b|\bchaussettes\b|\bsocken\b|\bcalzini\b|\bmeias\b"),
    ("underwear", r"\bunderwear\b|\bboxers?\b|\bbriefs\b|\bcalzoncillos?\b|\bbragas?\b|\bbras?\b|\bsujetador(?:es)?\b"),
    ("swimwear", r"\bswim\w*|\bba[ñn]adores?\b|\bbikinis?\b|\bmaillots? de bain\b"),
    ("shoes", r"\bshoes?\b|\bsneakers?\b|\btrainers?\b|\bzapat(?:os|illas)\b|\bchaussures\b|\bschuhe\b"
              r"|\bscarpe\b|\bsapatos?\b|\bboots?\b|\bbotas?\b|\brunners?\b|\bsandal(?:s|ias)?\b"),
    ("hat", r"\bhats?\b|\bcaps?\b|\bbeanies?\b|\bgorras?\b|\bgorros?\b|\bsombreros?\b|\bm[üu]tzen?\b|\bcappell[oi]\b"),
    ("bag", r"\bbags?\b|\bbolsos?\b|\bmochilas?\b|\bbackpacks?\b|\btote\b|\btasche\b|\bborsa\b"),
    ("accessory", r"\bscar(?:f|ves)\b|\bbufandas?\b|\bbelts?\b|\bcinturones?\b|\bgloves?\b|\bguantes\b"
                  r"|\bwallets?\b|\bcarteras?\b|\bsunglasses\b|\bwatch(?:es)?\b|\bjewel\w*"),
    ("bottle", r"\bbottles?\b|\bbotellas?\b|\bmugs?\b|\btazas?\b"),
]
DESC_CHARS = 300  # only the start of a page description is read for the product type


def flat(v):
    """Text of a breadcrumb/category value (string, list, or schema.org dict)."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        return flat(v.get("name") or v.get("item") or "")
    if isinstance(v, (list, tuple)):
        return " > ".join(t for t in (flat(x) for x in v) if t)
    return ""


def type_sources(target, raw, d):
    """(label, text) pairs read for the product type, strongest first."""
    if d is not None:
        return [("title", d["title"]), ("description", d["description"])]
    schema = raw.get("raw_product_schema") if isinstance(raw.get("raw_product_schema"), dict) else {}
    url = get(target, "source", "url") or raw.get("source_url") or ""
    slug = unquote(urlsplit(url).path).strip("/").split("/")[-1] if url else ""
    desc = raw.get("raw_full_description") or get(target, "content", "full_description") or ""
    return [("title", get(target, "content", "title")), ("product name", get(target, "identity", "product_name")),
            ("meta title", raw.get("raw_meta_title")), ("category", flat(schema.get("category"))),
            ("category", raw.get("raw_category_text")), ("breadcrumbs", flat(raw.get("raw_breadcrumbs"))),
            ("URL", slug), ("description", desc[:DESC_CHARS])]


def first_match(text, table):
    return next((v for v, p in table if re.search(p, text or "", re.I)), None)


def settle_shirt_type(target, ptype):
    target.setdefault("identity", {})["product_type"] =         shirt_type(ptype, get(target, "fit_and_style", "sleeve_length")) or "unknown"


def shirt_rank(target, recs):
    """The audit's shirt ranking: peer matching, step-by-step widening, one formula. Shared with Monitor (#116)
    so a snapshot shows the same rank as the audit. Returns (rank, ranked shirts, match, types, notes)."""
    notes = []
    key, note = peer_key(target, recs)
    notes += [note] if note else []
    key, types, step, wnote = widen(key, recs)
    notes += [wnote] if wnote else []
    rk, ranked = rank(target, recs, match=key, types=types)
    rk.update(ranked=bool(ranked), match_step=step)
    return rk, ranked, key, types, notes


def record_rank(rec):
    """Rank a stored normalized record exactly as a URL audit of it would (Monitor snapshots). None when it is
    not a shirt (the audit leaves those unranked) or cannot be read."""
    target = dash.adapt(rec)
    if not target:
        return None
    kind, ptype, _, _ = classify(target, {}, None)
    if kind == "other":
        return None
    if get(target, "identity", "product_type") not in SHIRT_TYPES:
        settle_shirt_type(target, ptype)
    return shirt_rank(target, not_self(target))[0]


def classify(target, raw, d):
    """("shirt", PRODUCT_TYPE value, label, text) | ("other", NON_SHIRT type, label, text) | ("other", None, ...).
    The normalized type wins when it is a shirt; otherwise the first source (strongest first) naming a shirt or
    another product type decides, so a shirt word deep in a hoodie's description does not make it a shirt."""
    pt = get(target, "identity", "product_type")
    src = type_sources(target, raw, d)
    if pt in SHIRT_TYPES:
        return "shirt", pt, src[0][0], src[0][1]
    for lbl, text in src:
        if not text:
            continue
        shirt = first_match(text, SHIRT_TABLE)
        if shirt:
            return "shirt", shirt, lbl, text
        other = first_match(text, NON_SHIRT)
        if other:
            return "other", other, lbl, text
    return "other", None, src[0][0], src[0][1]



def url_key(u):
    """Same-product URL identity: host without www, path without trailing slash; query and fragment ignored."""
    m = re.match(r"(?i)^[a-z][a-z0-9+.-]*://(?:www\.)?([^/?#]+)([^?#]*)", u or "")
    return (m.group(1).lower(), m.group(2).rstrip("/").lower()) if m else None


def not_self(target):
    """Dataset rows that are not the audited product itself (same product_id, URL or canonical URL)."""
    pid = target.get("product_id")
    own = {url_key(get(target, "source", k)) for k in ("url", "canonical_url")} - {None}
    return [r for r in dash.records() if r.get("product_id") != pid
            and not ({url_key(get(r, "source", k)) for k in ("url", "canonical_url")} & own)]


def mark_archive(result, url):
    """If url was read from a Common Crawl copy (not the live page), say so: result["archive"] and a note (additive)."""
    a = safe_fetch.archive_of(url) if url else None
    if a:
        result["archive"] = a
        result["notes"] = [f"Read from a Common Crawl archive copy captured {a['capture_date']}, not the live page; "
                           "facts such as price or stock may be out of date."] + result["notes"]
    return result


@router.post("/v1/audit")
def audit(payload: dict = Body(...)):
    import main  # lazy: main imports this module
    try:
        draft = is_draft(payload)
        d = draft_fields(payload) if draft else None
        if draft and not d["title"]:
            raise HTTPException(422, "draft_needs_title: add the product title")
        req = draft_request(main, d) if draft else main.ExtractRequest(**payload)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"])
    except TypeError as e:
        raise HTTPException(422, str(e).splitlines()[0])
    ex = main.extract(req)
    norm, raw = ex["normalized"], ex["raw"]
    notes = []
    if draft:
        norm["structured_data"] = {"product_schema_present": None, "offer_schema_present": None,
                                   "product_group_present": False, "raw_json_ld": []}
        draft_facts(norm, d)
        if d["language_detected"]:
            notes.append(f"No language was given, so we used '{d['language']}', detected from the words in your text.")
    target = dash.adapt(norm)
    if draft and not get(target, "identity", "product_type"):
        target.setdefault("identity", {})["product_type"] = infer_type(target, d)
    if not draft and not (get(target, "structured_data", "product_schema_present") or price(target)
            or get(target, "identity", "product_type")):
        raise HTTPException(422, "not_a_product_page: we couldn't find a product name, price or product type"
                                 " (the page may load them with JavaScript). Paste the title and description instead.")
    kind, ptype, read_from, read_text = classify(target, raw, d)
    ident = target.setdefault("identity", {})
    unranked = None
    if kind == "other":  # not a shirt: the full audit, without a rank (we rank shirts only for now)
        ident["product_type"] = ptype or "other"
        unranked = {"reason": "not_a_shirt", "type": ptype, "read_from": read_from, "read_text": (read_text or "")[:200]}
        notes.append(f"We rank against shirts only for now; this looks like {'a ' + ptype if ptype else 'a product that is not a shirt'}"
                     f" (we read the {read_from} as \"{(read_text or '')[:120]}\"), so here is its listing quality and "
                     "fixes without a rank. The fixes compare it with the best-listed shirts in our dataset.")
    elif get(target, "identity", "product_type") not in SHIRT_TYPES:
        settle_shirt_type(target, ptype)
        if read_from != "title":
            notes.append(f"We read the shirt type from the {read_from} (\"{(read_text or '')[:120]}\").")
    recs = not_self(target)  # the product is never its own peer
    if unranked:
        ref = {**target, "commerce": {**(target.get("commerce") or {}), "price": None, "currency": None},
               "fit_and_style": {**(target.get("fit_and_style") or {}), "sleeve_length": None}}
        rk, _ = rank(target, [])
        rk.update(position=None, position_from=None, position_to=None, tied=0, ranked=False)
        matched, ranked = [], []
        pool = [p for _, p in peer_group(ref, recs, RANK_K * 4, sorted(SHIRT_TYPES))]
        w = weights(pool + [target])  # the best-listed comparable shirts (same language), as the ranking would order them
        reference = sorted(pool, key=lambda x: (-quality(x, w)["score"], str(x.get("product_id") or "")))[:TOP]
    else:
        rk, ranked, key, types, rnotes = shirt_rank(target, recs)
        notes += rnotes
        matched = peer_group(key, recs, K, types)
        reference = None
        if get(target, "identity", "product_type") == "unknown":
            notes.append("It looks like a shirt, but we couldn't tell which type (e.g. t-shirt, polo, short or long "
                         "sleeve)" + (", so it was compared with all shirt types." if ranked else
                                      ", so there are no comparable shirts to rank against.") + " Name the type in the title.")
        elif not ranked:
            notes.append("No comparable shirts found: we need the same product type and language in our dataset.")
    n_unknown = unknown_sleeve(target, ranked) if rk.get("match_step") in ("exact", "no_price_band") else 0
    if n_unknown:
        notes.append(f"Fewer than {SLEEVE_FILL} comparable shirts state the same sleeve length as yours, so {n_unknown} "
                     "shirts that don't state a sleeve length were included.")
    top = ranked[:TOP] if reference is None else reference
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
    facts_found = sum(attributes_present(target).values())
    result = {
        "product": {**dash.summary(target), "url": get(target, "source", "url"),
                    "image": (raw.get("image_urls") or [None])[0], "draft": draft,
                    "description": description_text(target)},
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
        "peers": [{**dash.summary(p), "url": get(p, "source", "url"), **link.flag(p), "match_score": s,
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
        "visibility": dash.visibility_summary(get(target, "source", "merchant_domain")
                                              or (url_key(get(target, "source", "url")) or (None,))[0]),
        "conflicts": norm.get("conflicts") or [],
        "notes": notes,
        "unranked": unranked,
    }
    return mark_archive(result, req.url) if not (draft or req.html or req.text) else result


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
