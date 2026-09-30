"""Product Truth: only the normalized fields that carry evidence, plus origin/certification statements found on the
merchant's own page. Localized fact sentences and JSON-LD are rendered deterministically from it."""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dataset" / "collect"))

from benchmark.claims import CERTS, ORIGIN_RE, _country  # noqa: E402  (reused, not copied)

LANGS = ("en", "es")
FACT_FIELDS = [
    "identity.brand", "identity.product_name", "identity.product_type", "identity.audience",
    "materials.material_percentages", "materials.primary_material", "materials.fabric_weight_gsm", "materials.stretch",
    "fit_and_style.fit", "fit_and_style.sleeve_length", "fit_and_style.neckline", "fit_and_style.pattern",
    "variants.colors", "variants.sizes",
    "commerce.price", "commerce.sale_price", "commerce.currency", "commerce.availability", "commerce.gtin",
]


def _empty(v):
    return v in (None, "", [], {})


def _page_texts(rec):
    c = rec.get("content") or {}
    parts = [c.get("full_description"), c.get("short_description")] + (c.get("bullet_points") or [])
    return [p for p in parts + (rec.get("features") or []) if isinstance(p, str)]


def product_truth(rec):
    """{product_id, language, facts{field: value}, sources{field: [source_text]}, origins, certs, care}."""
    evidence = [e for e in rec.get("evidence") or [] if isinstance(e, dict)]
    sources = {}
    for e in evidence:
        if e.get("source_text"):
            sources.setdefault(e.get("field"), []).append(html.unescape(str(e["source_text"])))
    facts = {}
    for f in FACT_FIELDS:
        sec, key = f.split(".")
        v = (rec.get(sec) or {}).get(key)
        if f in sources and not _empty(v):
            facts[f] = " ".join(html.unescape(v).split()) if isinstance(v, str) else v  # pages may entity-encode
    if "variants.colors" in facts:
        facts["variants.colors"] = [c if isinstance(c, dict) else {"original_color_name": c, "normalized": c}
                                    for c in facts["variants.colors"]]
    if "variants.sizes" in facts:
        facts["variants.sizes"] = [s if isinstance(s, dict) else {"raw_size": s, "normalized_size": s}
                                   for s in facts["variants.sizes"]]
    page = "\n".join(_page_texts(rec))
    origins = sorted({_country(m) for m in ORIGIN_RE.findall(page)})
    certs = {}
    for key, pat in CERTS:
        m = re.search(pat, page, re.I)
        if m:
            certs[key] = m.group(0)
    return {"product_id": rec.get("product_id"), "language": (rec.get("source") or {}).get("language"),
            "url": (rec.get("source") or {}).get("canonical_url") or (rec.get("source") or {}).get("url"),
            "facts": facts, "sources": sources, "origins": origins, "certs": certs, "care": sources.get("care", [])}


def check_record(truth):
    """The Truth in the normalized-record shape benchmark/claims.check() expects."""
    f = truth["facts"]
    page = [f"Made in {COUNTRY['en'].get(o, o.title())}" for o in truth["origins"]] + list(truth["certs"].values())
    return {"materials": {"material_percentages": f.get("materials.material_percentages"),
                          "fabric_weight_gsm": f.get("materials.fabric_weight_gsm")},
            "fit_and_style": {k: f.get(f"fit_and_style.{k}") for k in ("fit", "sleeve_length", "neckline")},
            "identity": {"audience": f.get("identity.audience")},
            "commerce": {"price": f.get("commerce.price"), "sale_price": f.get("commerce.sale_price"),
                         "currency": f.get("commerce.currency")},
            "variants": {"colors": f.get("variants.colors") or [], "sizes": f.get("variants.sizes") or [], "items": []},
            "content": {"full_description": "\n".join(page)}, "features": [], "evidence": []}


# ---- localization (Truth -> localized fact sentences) --------------------------------------

MATERIAL = {"es": {"cotton": "algodón", "organic_cotton": "algodón orgánico", "polyester": "poliéster",
                   "recycled_polyester": "poliéster reciclado", "elastane": "elastano", "spandex": "elastano",
                   "wool": "lana", "merino_wool": "lana merino", "linen": "lino", "viscose": "viscosa",
                   "nylon": "poliamida", "hemp": "cáñamo", "silk": "seda"}}
COLOR = {"es": {"white": "blanco", "black": "negro", "navy": "marino", "blue": "azul", "red": "rojo", "green": "verde",
                "yellow": "amarillo", "orange": "naranja", "pink": "rosa", "purple": "morado", "brown": "marrón",
                "beige": "beige", "grey": "gris", "khaki": "caqui"}}
COUNTRY = {"en": {"usa": "USA", "uk": "UK"},
           "es": {"spain": "España", "mexico": "México", "turkey": "Turquía", "usa": "Estados Unidos", "italy": "Italia",
                  "peru": "Perú", "morocco": "Marruecos", "uk": "Reino Unido"}}
PHRASES = {
    "en": {"material": "Material: {}.", "gsm": "Fabric weight: {} gsm.", "stretch": "Stretch fabric.",
           "fit": {"oversized": "Oversized fit.", "slim": "Slim fit.", "relaxed": "Relaxed fit.",
                   "athletic": "Athletic fit.", "tailored": "Tailored fit.", "regular": "Regular fit."},
           "sleeve": {"short": "Short sleeves.", "long": "Long sleeves.", "sleeveless": "Sleeveless.",
                      "three_quarter": "3/4 sleeves."},
           "neckline": {"crew": "Crew neck.", "v_neck": "V-neck.", "scoop": "Scoop neck.", "henley": "Henley neckline."},
           "pattern": {"striped": "Striped.", "plaid": "Plaid.", "graphic": "Graphic print.", "printed": "Printed.",
                       "solid": "Solid color."},
           "audience": {"men": "For men.", "women": "For women.", "unisex": "Unisex.", "kids": "For kids."},
           "colors": "Colors: {}.", "sizes": "Sizes: {}.", "price": "Price: {}.", "sale": "Sale price: {}.",
           "availability": {"in_stock": "In stock.", "out_of_stock": "Out of stock."},
           "origin": "Made in {}.", "cert": "Certification: {}.", "care": "Care: {}"},
    "es": {"material": "Material: {}.", "gsm": "Gramaje: {} gsm.", "stretch": "Tejido elástico.",
           "fit": {"oversized": "Corte oversize.", "slim": "Corte entallado.", "relaxed": "Corte holgado.",
                   "athletic": "Athletic fit.", "tailored": "Tailored fit.", "regular": "Corte regular."},
           "sleeve": {"short": "Manga corta.", "long": "Manga larga.", "sleeveless": "Sin mangas.",
                      "three_quarter": "Manga 3/4."},
           "neckline": {"crew": "Cuello redondo.", "v_neck": "Cuello en V.", "scoop": "Scoop neck.",
                        "henley": "Cuello henley."},
           "pattern": {"striped": "De rayas.", "plaid": "De cuadros.", "graphic": "Estampado gráfico.",
                       "printed": "Estampado.", "solid": "Liso."},
           "audience": {"men": "Para hombre.", "women": "Para mujer.", "unisex": "Unisex.", "kids": "Para niños."},
           "colors": "Colores: {}.", "sizes": "Tallas: {}.", "price": "Precio: {}.", "sale": "Precio rebajado: {}.",
           "availability": {"in_stock": "Disponible.", "out_of_stock": "Agotado."},
           "origin": "Hecho en {}.", "cert": "Certificación: {}.", "care": "Cuidado: {}"},
}


def _num(v):
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


def _material(truth, lang):
    f = truth["facts"]
    name = lambda m: MATERIAL.get(lang, {}).get(m, m.replace("_", " "))  # noqa: E731
    pct = f.get("materials.material_percentages")
    if isinstance(pct, dict) and pct:
        return ", ".join(f"{_num(p)}% {name(m)}" for m, p in sorted(pct.items(), key=lambda x: -x[1]))
    return name(f["materials.primary_material"]) if f.get("materials.primary_material") else None


def color_names(truth, lang):
    out = []
    for c in truth["facts"].get("variants.colors") or []:
        n = c.get("normalized")
        out.append(COLOR.get(lang, {}).get(n, n) if n else c.get("original_color_name"))
    return [c for c in dict.fromkeys(out) if c]


def fact_sentences(truth, lang):
    """Localized, deterministic sentences, one fact each. This is the only content an LLM may rephrase."""
    P, f, out = PHRASES[lang], truth["facts"], []
    one = lambda table, key: P[table].get(f.get(key)) if f.get(key) else None  # noqa: E731
    mat = _material(truth, lang)
    out += [P["material"].format(mat) if mat else None,
            P["gsm"].format(_num(f["materials.fabric_weight_gsm"])) if f.get("materials.fabric_weight_gsm") else None,
            P["stretch"] if f.get("materials.stretch") is True else None,
            one("fit", "fit_and_style.fit"), one("sleeve", "fit_and_style.sleeve_length"),
            one("neckline", "fit_and_style.neckline"), one("pattern", "fit_and_style.pattern"),
            one("audience", "identity.audience")]
    colors = color_names(truth, lang)
    sizes = [s.get("normalized_size") or s.get("raw_size") for s in f.get("variants.sizes") or []]
    out += [P["colors"].format(", ".join(colors)) if colors else None,
            P["sizes"].format(", ".join(s for s in sizes if s)) if any(sizes) else None]
    cur = f.get("commerce.currency")
    if cur and f.get("commerce.price") is not None:
        out.append(P["price"].format(f"{f['commerce.price']:.2f} {cur}"))
    if cur and f.get("commerce.sale_price") is not None:
        out.append(P["sale"].format(f"{f['commerce.sale_price']:.2f} {cur}"))
    out.append(one("availability", "commerce.availability"))
    out += [P["origin"].format(COUNTRY.get(lang, {}).get(o, o.title())) for o in truth["origins"]]
    out += [P["cert"].format(t) for t in truth["certs"].values()]
    if truth.get("language") and str(truth["language"]).lower().startswith(lang):  # care text is never translated
        out += [P["care"].format(c.rstrip(".") + ".") for c in truth["care"]]
    return [s for s in out if s]


TITLE_MAX = 90  # same limit as train/reward.py copy_reward


def fallback_title(truth, lang):
    """Deterministic title <= TITLE_MAX: brand + product name (brand not repeated) + material, else shorter exact
    identity, else the material or first fact. Names are never cut: only the exact verified name counts as identity."""
    f = truth["facts"]
    brand, name = (str(f.get(k) or "").strip() for k in ("identity.brand", "identity.product_name"))
    head = name if brand and name.lower().startswith(brand.lower()) else " ".join(x for x in (brand, name) if x)
    mat = _material(truth, lang)
    facts = fact_sentences(truth, lang)
    for cand in (f"{head} - {mat}" if head and mat else "", head, name, brand, mat or "",
                 facts[0].rstrip(".") if facts else ""):
        if cand and len(cand) <= TITLE_MAX:
            return cand
    return ""


# ---- schema.org JSON-LD (deterministic, verified facts only) --------------------------------

AVAILABILITY = {"in_stock": "InStock", "out_of_stock": "OutOfStock", "preorder": "PreOrder",
                "backorder": "BackOrder", "discontinued": "Discontinued"}
GENDER = {"men": "male", "women": "female", "unisex": "unisex"}


def json_ld(truth):
    f = truth["facts"]
    node = {"@context": "https://schema.org", "@type": "Product"}
    if f.get("identity.product_name"):
        node["name"] = f["identity.product_name"]
    if f.get("identity.brand"):
        node["brand"] = {"@type": "Brand", "name": f["identity.brand"]}
    mat = _material(truth, "en")
    if mat:
        node["material"] = mat
    colors = color_names(truth, "en")
    if colors:
        node["color"] = colors[0] if len(colors) == 1 else colors
    sizes = [s.get("normalized_size") or s.get("raw_size") for s in f.get("variants.sizes") or []]
    if any(sizes):
        node["size"] = [s for s in sizes if s]
    if f.get("identity.audience") in GENDER:
        node["audience"] = {"@type": "PeopleAudience", "suggestedGender": GENDER[f["identity.audience"]]}
    if f.get("commerce.gtin"):
        node["gtin"] = str(f["commerce.gtin"])
    if f.get("materials.fabric_weight_gsm"):
        node["additionalProperty"] = [{"@type": "PropertyValue", "name": "fabric weight",
                                       "value": f["materials.fabric_weight_gsm"], "unitText": "g/m²"}]
    price = f.get("commerce.sale_price") if f.get("commerce.sale_price") is not None else f.get("commerce.price")
    if price is not None and f.get("commerce.currency"):
        offer = {"@type": "Offer", "price": f"{price:.2f}", "priceCurrency": f["commerce.currency"]}
        if f.get("commerce.availability") in AVAILABILITY:
            offer["availability"] = "https://schema.org/" + AVAILABILITY[f["commerce.availability"]]
        if truth.get("url"):
            offer["url"] = truth["url"]
        node["offers"] = offer
    return node


# ---- missing attributes (ask the merchant; never invent) -----------------------------------

def missing_attributes(truth, gaps=None):
    """Attributes from analysis/gaps.py ATTRIBUTES with no verified value. Peer-backed gaps come first."""
    from analysis.gaps import ATTRIBUTES
    peer = {}
    for i in (gaps or {}).get("issues") or []:
        if i.get("type") == "OBSERVED_FACT" and (i.get("evidence") or {}).get("of"):
            peer[i["field"]] = f"{i['evidence']['count']}/{i['evidence']['of']}"
    out = []
    for sec, key in ATTRIBUTES:
        field = f"{sec}.{key}"
        if field == "content.full_description" or field in truth["facts"]:
            continue
        label = key.replace("_", " ")
        out.append({"field": field, "peers_with_attribute": peer.get(field),
                    "reason": "missing; present in most comparable products" if field in peer else "no verified value",
                    "question": f"What is the {label} of this product? Answer only from a label, spec sheet or "
                                f"supplier document, and attach it."})
    return sorted(out, key=lambda x: x["peers_with_attribute"] is None)
