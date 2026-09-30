"""Raw record -> normalized record (dataset/schema/normalized_record.schema.json).

Deterministic rules only (regex + lookup tables, English and Spanish). Every value is backed by an
evidence item whose source_text is an exact substring of the raw field named by source_location, after
HTML-entity decoding (decoded_text; the raw record keeps the page's own encoding).
Values not stated on the page stay null. Disagreeing sources are recorded in `conflicts` and the
value is left null (no authority ranking is approved yet, docs/DATASET_SPEC.md Part B).
"""
import html
import re

from extract import BULLET_RE, hash_id, canonical_key

OZ_TO_GSM = 33.906

# Most specific first. Tencel covers lyocell and modal, so it maps to "other" unless the fibre is named.
MATERIALS = [
    ("organic_cotton", r"organic cotton|algod[oó]n org[aá]nico|bio-?baumwolle|coton bio"),
    ("recycled_polyester", r"recycled polyester|poli[eé]ster reciclado|\brpet\b"),
    ("merino_wool", r"merino"),
    ("modal", r"\bmodal\b"),
    ("lyocell", r"\blyocell\b"),
    ("other", r"\btencel\b"),
    ("cotton", r"\bcotton\b|\balgod[oó]n\b|\bbaumwolle\b|\bcoton\b"),
    ("polyester", r"\bpolyester\b|\bpoli[eé]ster\b"),
    ("linen", r"\blinen\b|\blino\b|\bleinen\b|\bflax\b"),
    ("viscose", r"\bviscose\b|\bviscosa\b|\becovero\b"),
    ("rayon", r"\brayon\b"),
    ("elastane", r"\belastane\b|\belastano\b|\belasthan\b"),
    ("spandex", r"\bspandex\b"),
    ("wool", r"\bwool\b|\blana\b|\bwolle\b"),
    ("nylon", r"\bnylon\b|\bpolyamide\b|\bpoliamida\b"),
    ("hemp", r"\bhemp\b|\bc[aá][ñn]amo\b"),
    ("silk", r"\bsilk\b|\bseda\b"),
]
FIT = [
    ("oversized", r"\boversi[sz]ed?\b"),
    ("slim", r"\bslim(?:[ -]fit)?\b|\bentallad[oa]\b"),
    ("relaxed", r"\brelaxed(?:[ -]fit)?\b|\bholgad[oa]\b|\bboxy\b|\bloose[ -]fit\b"),
    ("athletic", r"\bathletic[ -]fit\b|\bmuscle[ -]fit\b"),
    ("tailored", r"\btailored[ -]fit\b"),
    ("regular", r"\bregular[ -]fit\b|\bfit:? regular\b|\bcorte regular\b|\bpatr[oó]n regular\b|\bclassic[ -]fit\b"),
]
SLEEVE = [
    ("short", r"\bshort[ -]sleeves?d?\b|\bmangas? cortas?\b|\bkurzarm\b"),
    ("long", r"\blong[ -]sleeves?d?\b|\blongsleeve\b|\bmangas? largas?\b|\blangarm\b"),
    ("sleeveless", r"\bsleeveless\b|\bsin mangas\b|\btank top\b|\bde tirantes\b"),
    ("three_quarter", r"3/4[ -]sleeves?|\bthree[ -]quarter\b|\bmanga 3/4"),
]
NECKLINE = [
    ("crew", r"\bcrew[ -]?neck(?:line)?\b|\bround[ -]neck(?:line)?\b|\bcuello redondo\b|\bcuello caja\b"),
    ("v_neck", r"\bv[ -]neck(?:line)?\b|\bcuello (?:de pico|en v|pico)\b"),
    ("scoop", r"\bscoop[ -]neck(?:line)?\b"),
    ("henley", r"\bhenley\b"),
]
PATTERN = [
    ("striped", r"\bstripe[sd]?\b|\brayas\b|\brayad[oa]\b"),
    ("plaid", r"\bplaid\b|\bchecked\b|\bcuadros\b|\btartan\b|\bgingham\b|\bvichy\b"),
    ("graphic", r"\bgraphic\b"),
    ("printed", r"\bprint(?:ed)?\b|\bestampad[oa]\b"),
    ("solid", r"\bsolid colou?r\b|\bliso\b|\blisa\b"),
]
PRODUCT_TYPE = [  # style types first; generic shirts fall back to the sleeve type
    ("overshirt", r"\bover ?shirts?\b|\bsobrecamisas?\b|\bshackets?\b"),
    ("polo", r"\bpolos?\b"),
    ("henley", r"\bhenleys?\b"),
    ("flannel", r"\bflannel\b|\bfranela\b"),
    ("oxford", r"\boxford\b"),
    ("work_shirt", r"\bwork ?shirts?\b"),
    ("t_shirt", r"\bt-?shirts?\b|\btees?\b|\bcamisetas?\b|\bplayeras?\b|\bremeras?\b"),
    ("_dress_shirt", r"\b(?:dress|formal|business) shirts?\b|\bnon-?iron\b.*\bshirts?\b|\bcamisas? de vestir\b"),
    ("_shirt", r"\bshirts?\b|\bcamisas?\b|\bguayaberas?\b"),
]
SHIRT_TYPES = {v for v, _ in PRODUCT_TYPE if not v.startswith("_")} | {"short_sleeve_shirt", "long_sleeve_shirt"}
AUDIENCE = [
    ("women", r"\b(?:women'?s?|woman|mujer|damen|femme)\b"),
    ("men", r"\b(?:men'?s?|man|hombre|herren|homme)\b"),
    ("unisex", r"\bunisex\b"),
    ("kids", r"\b(?:kids?|niñ[oa]s?|boys?|girls?|baby|toddler)\b"),
]
COLORS = {
    "white": r"white|blanc[oa]|snow", "black": r"black|negr[oa]", "navy": r"navy|marino",
    "blue": r"blue|azul|[ií]ndigo|indigo", "red": r"red|roj[oa]", "green": r"green|verde|olive|oliva",
    "yellow": r"yellow|amarill[oa]|mustard|mostaza", "orange": r"orange|naranja",
    "pink": r"pink|rosa", "purple": r"purple|morad[oa]|lila|lilac|plum|ciruela",
    "brown": r"brown|marr[oó]n|chocolate|camel", "beige": r"beige|sand|arena|ecru|crudo|cream|crema",
    "grey": r"gr[ae]y|gris|charcoal", "khaki": r"khaki|caqui",
}
LETTER_SIZE = re.compile(r"^(?:XXS|XS|S|M|L|XL|XXL|XXXL|[2-6]XL)$", re.I)
COLOR_OPTION = re.compile(r"^(?:colou?r|farbe|couleur)$", re.I)
SIZE_OPTION = re.compile(r"^(?:size|talla|tama[ñn]o|gr[öo](?:ß|ss)e|taille)$", re.I)
ATTRIBUTE_SECTIONS = {"overview", "details", "fabric", "fit", "features", "care"}


# ---- pure rule functions (unit tested) -------------------------------------------------

def lang_code(tag):
    """BCP 47 tag -> lowercase primary subtag ('en-US', 'EN', 'es_MX' -> 'en'/'es'); other text is lowercased
    as-is (e.g. the dataset's 'other'); None if missing or blank."""
    if not isinstance(tag, str) or not tag.strip():
        return None
    m = re.fullmatch(r"([A-Za-z]{2,3})(?:[-_][A-Za-z0-9]{1,8})*", tag.strip())
    return (m.group(1) if m else tag.strip()).lower()


def match_lookup(text, table):
    """All (value, matched_text) pairs from a lookup table, in table order, one per value."""
    hits = []
    for value, pattern in table:
        m = re.search(pattern, text or "", re.I)
        if m:
            hits.append((value, m.group(0)))
    return hits


def shirt_type(value, sleeve):
    """A PRODUCT_TYPE value -> product type: style types as is; generic shirts by sleeve length (None if unknown);
    dress/non-iron shirts are long-sleeved unless the sleeve evidence says short."""
    if value == "_dress_shirt":
        return "short_sleeve_shirt" if sleeve == "short" else "long_sleeve_shirt"
    if value == "_shirt":
        return f"{sleeve}_sleeve_shirt" if sleeve in ("short", "long") else None
    return value


def material_of(name):
    for value, pattern in MATERIALS:
        if re.search(pattern, name, re.I):
            return value
    return None


def parse_composition(line):
    """'55% hemp, 45% Tencel' -> ({'hemp': 55, 'other': 45}, '55% hemp, 45% Tencel').
    Returns (None, None) unless the percentages of known materials sum to 100."""
    pct = r"(\d{1,3}(?:[.,]\d+)?)\s*%"
    name = r"[^\d%,;:/+()\n]{2,40}"
    forward, reverse = [], []
    for m in re.finditer(pct + r"\s*(?:de\s+|of\s+)?(" + name + ")", line, re.I):  # 100% cotton
        mat = material_of(m.group(2))
        if mat:
            forward.append((mat, float(m.group(1).replace(",", ".")), m.start(), m.end()))
    for m in re.finditer(r"(" + name + r")\s+" + pct, line, re.I):  # cotton 100%
        mat = material_of(m.group(1))
        if mat:
            reverse.append((mat, float(m.group(2).replace(",", ".")), m.start(), m.end()))
    found = forward if abs(sum(p for _, p, _, _ in forward) - 100) <= 1 else reverse
    total = sum(p for _, p, _, _ in found)
    if not found or abs(total - 100) > 1:
        return None, None
    comp = {}
    for mat, p, _, _ in found:
        comp[mat] = comp.get(mat, 0) + p
    if any(v > 100 for v in comp.values()):  # e.g. '100% cotton ... 1% cotton' repeated; not a composition
        return None, None
    comp = {k: int(v) if float(v).is_integer() else v for k, v in comp.items()}
    span = line[found[0][2]:found[-1][3]].strip()
    return comp, span


def primary_material(comp):
    if not comp:
        return None
    top = max(comp.values())
    winners = [k for k, v in comp.items() if v == top]
    return winners[0] if len(winners) == 1 else None


def parse_weight(text):
    """Return (gsm, raw_text, method, confidence, note) or None. See spec 'Fabric weight'."""
    m = re.search(r"(\d{2,4})\s*(?:gsm|g/m²|g/m2|gr/m2|grs?/m²|g/sqm|gramos(?: por metro cuadrado)?)(?![a-z])", text, re.I)
    if m:
        return int(m.group(1)), m.group(0), "direct", 1.0, None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:oz\.?\s*/\s*(?:yd²|yd2|sq\.? ?yd)|ounces? per square yard)", text, re.I)
    if m:
        return round(float(m.group(1).replace(",", ".")) * OZ_TO_GSM), m.group(0), "conversion", 1.0, None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*oz\b\.?(?!\s*/)", text, re.I)
    if m:
        before, after = text[max(0, m.start() - 12):m.start()].lower(), text[m.end():m.end() + 30].lower()
        if "weigh" not in before and re.search(r"fabric|cotton|jersey|heavyweight|midweight|lightweight|twill|denim|flannel|oxford", after):
            return (round(float(m.group(1).replace(",", ".")) * OZ_TO_GSM), m.group(0), "conversion", 0.9,
                    "bare oz read as oz/yd² by US apparel convention")
        return None, m.group(0), None, None, None
    return None


def normalize_color(name):
    hits = [c for c, p in COLORS.items() if re.search(r"\b(?:" + p + r")\b", name or "", re.I)]
    if "navy" in hits and "blue" in hits:
        hits.remove("blue")
    return hits[0] if len(hits) == 1 else None


def normalize_size(raw):
    return raw.strip().upper() if LETTER_SIZE.match(raw.strip()) else None


def is_size_option(name, value):
    """Size option by name, or Shopify's default 'Title' option holding letter sizes."""
    return bool(SIZE_OPTION.match(name) or (name.lower() == "title" and normalize_size(value)))


def map_availability(text):
    t = (text or "").lower()
    for key, value in (("instock", "in_stock"), ("outofstock", "out_of_stock"), ("soldout", "out_of_stock"),
                       ("preorder", "preorder"), ("backorder", "backorder"), ("discontinued", "discontinued")):
        if key in t.replace("_", "").replace(" ", ""):
            return value
    return {"true": "in_stock", "false": "out_of_stock"}.get(t, "unknown" if t else None)


def to_price(text):
    try:
        return round(float(str(text).replace(",", ".")), 2)
    except (TypeError, ValueError):
        return None


# ---- TEAM-37: rules for fields that were always null (fabric_type, texture, shirt_length, style,
# care, sizes, collar_type). Pure functions over (source_location, text) pairs; every value comes
# with the exact matched substring as evidence. Nothing is inferred beyond the matched text.

_KNIT = r"(?:knit|fabric|cotton|material|cloth|weave)"
FABRIC_TYPE = [  # fabric words need a fabric context ("jersey" alone is often a sports jersey)
    ("french_terry", r"\bfrench[ -]terry\b|\bfelpa francesa\b"),
    ("pique", r"\bpiqu[eé]\b"),
    ("interlock", r"\binterlock[ -]" + _KNIT + r"\b|\b" + _KNIT + r" interlock\b"),
    ("slub", r"\bslub[ -](?:jersey|knit|fabric|cotton|yarn)\b"),
    ("oxford", r"\boxford (?:cloth|fabric|weave)\b|\btela oxford\b"),
    ("flannel", r"\bflannel (?:fabric|cotton|cloth)\b|\bcotton flannel\b|\btela (?:de )?franela\b"),
    ("twill", r"\btwill (?:fabric|weave|cloth)\b|\bcotton twill\b(?![ -]?tap)|\btela (?:de )?sarga\b"),
    ("poplin", r"\bpoplin\b|\bpopelina\b|\bpopel[ií]n\b"),
    ("mesh", r"\bmesh (?:fabric|knit|material|panels?)\b|\bbreathable mesh\b|\btejido de malla\b"),
    ("rib", r"\brib(?:bed)?[ -]knit\b(?![ -](?:collar|cuffs?|neck\w*|trim\w*|hem|waist\w*|band|sleeves?|crew))|\b1x1 rib\b|\bpunto (?:de )?canal[eé]\b"),
    ("jersey", r"\bjersey[ -](?:knit|fabric|cotton|material)\b|\b(?:cotton|single|slub|cotton-blend|combed cotton) jersey\b"
               r"|\bpunto (?:de )?jersey\b|\bjersey de algod[oó]n\b|\bpunto liso\b"),
]
TEXTURE = [  # texture words only next to a fabric word
    ("brushed", r"\bbrushed[ -](?:cotton|fabric|jersey|fleece|knit|finish)\b|\b(?:algod[oó]n|tejido) (?:perchad|cepillad)[oa]\b"),
    ("waffle", r"\bwaffle[ -](?:knit|weave|texture|fabric)\b|\bpunto gofrado\b"),
    ("ribbed", r"\bribbed (?:fabric|knit|texture|cotton|tee|t-shirt|tank|top)\b(?![ -](?:collar|cuffs?|neck\w*|trim\w*|hem|waist\w*|band|sleeves?|crew))|\btejido acanalado\b"),
    ("textured", r"\btextured (?:fabric|knit|cotton|jersey|weave)\b|\btejido texturizado\b"),
    ("soft", r"\b(?:super[ -]|ultra[ -]|extra[ -])?soft(?:[ -]touch)? (?:cotton|fabric|jersey|knit|material|feel|hand|blend|tri-?blend)\b"
             r"|\bsoft[ -](?:washed|touch|hand)\b|\b(?:algod[oó]n|tejido) (?:muy |super |ultra )?suave\b|\btacto suave\b"),
]
SHIRT_LENGTH = [
    ("cropped", r"\bcropped (?:tee|t-shirt|shirt|top|fit|length|hem)\b|\bcrop[ -]?top\b|\bcorte crop\b"),
    ("longline", r"\blong[ -]?line (?:tee|t-shirt|shirt|top|fit|length|hem)\b"),
    ("tunic", r"\btunic (?:tee|t-shirt|shirt|top|length)\b|\b(?:camiseta|camisa|blusa)(?: tipo)? t[uú]nica\b"),
    ("regular", r"\bregular[ -]length\b|\blargo regular\b|\blongitud regular\b"),
]
_NOUN = r"(?:tee|t-shirt|t shirt|shirt|polo|top|style)"
STYLE = [  # fixed vocabulary, only directly before a product noun (ES: after camiseta/camisa/polo/estilo)
    ("vintage", r"\b(?:vintage|retro)[ -]" + _NOUN + r"s?\b|\b(?:camiseta|camisa|polo|estilo) (?:vintage|retro)\b"),
    ("streetwear", r"\bstreetwear(?:[ -]" + _NOUN + r"s?)?\b|\bstreet[ -]style\b"),
    ("athletic", r"\bathletic[ -](?:tee|t-shirt|shirt|top|style)s?\b|\b(?:camiseta|camisa|polo) deportiv[oa]\b"),
    ("graphic", r"\bgraphic[ -](?:tee|t-shirt|t shirt|shirt|top)s?\b|\b(?:camiseta|camisa) gr[aá]fica\b"),
    ("minimalist", r"\bminimalist(?:ic)?[ -](?:" + _NOUN[3:-1] + r"|design)s?\b|\b(?:camiseta|camisa|estilo|dise[ñn]o) minimalista\b"),
    ("basic", r"\bbasic[ -](?:tee|t-shirt|t shirt|shirt|polo|top)s?\b|\b(?:camiseta|camisa|polo) b[aá]sic[oa]\b"),
    ("casual", r"\bcasual[ -](?:tee|t-shirt|t shirt|shirt|polo|top|fit)s?\b|\b(?:camiseta|camisa|polo) casual\b"),
]
CARE = [
    ("machine_wash", r"\bmachine[ -]wash(?:able)?\b|\blavar? a m[aá]quina\b|\blavado a m[aá]quina\b|\blavable a m[aá]quina\b|\blavable en lavadora\b"),
    ("hand_wash", r"\bhand[ -]wash\b|\blavar a mano\b|\blavado a mano\b"),
    ("wash_cold", r"\bwash(?:ing)?(?: \w+)? (?:in )?cold\b|\bcold (?:water )?wash\b|\bin cold water\b|\bagua fr[ií]a\b"),
    ("do_not_tumble_dry", r"\b(?:do not|don'?t|no) tumble[ -]dry\b|\bno (?:usar |utilizar )?(?:la )?secadora\b"),
    ("tumble_dry", r"(?<!not )(?<!n't )(?<!no )\btumble[ -]dry(?: low)?\b|\bsecar en secadora\b"),
    ("do_not_bleach", r"\b(?:do not|don'?t|no) bleach\b|\bno (?:usar |utilizar )?(?:lej[ií]a|blanqueador)\b|\bno blanquear\b"),
    ("do_not_iron", r"\b(?:do not|don'?t) iron\b|\bno planchar\b"),
    ("iron_low", r"\biron(?:ing)? (?:on )?(?:low|cool|warm)\b|\b(?:cool|warm|low) iron\b|\bplanchar a (?:baja )?temperatura(?: baja| media)?\b"),
    ("dry_clean", r"(?<!not )(?<!n't )\bdry[ -]clean(?:able)?\b|\blimpieza en seco\b"),
]
COLLAR_TYPE = [
    ("button_down", r"\bbutton[ -]down(?: collar)?\b|\bcuello (?:con )?botones\b"),
    ("spread", r"\bspread collar\b|\bcuello italiano\b"),
    ("mandarin", r"\bmandarin collar\b|\bband collar\b|\bcuello mao\b"),
    ("mock_neck", r"\bmock[ -]?neck\b|\bcuello perkins\b|\bmedio cuello\b"),
    ("polo", r"\bpolo collar\b|\bcuello (?:tipo )?polo\b"),
    ("henley", r"\bhenley\b|\bcuello panadero\b"),
    ("v_neck", r"\bv[ -]neck(?:line)?\b|\bcuello (?:de pico|en v|pico)\b"),
    ("crew", r"\bcrew[ -]?neck(?:line)?\b|\bround[ -]neck(?:line)?\b|\bcuello redondo\b|\bcuello caja\b"),
]
SIZE_ORDER = ["XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
_SZ = r"(?:XXXXXL|XXXXL|XXXL|XXL|XXS|XS|XL|[2-6]XL|S|M|L)"
_SIZECUE = r"(?i:\bsizes?\b|\btallas?\b|\bavailable in\b|\bdisponible en\b)\s*:?\s*"
SIZE_RANGE = re.compile(_SIZECUE + r"(?:from\s+|de\s+)?\b(" + _SZ + r")\s*(?:-|–|to|a|hasta)\s*(" + _SZ + r")\b")
SIZE_LIST = re.compile(_SIZECUE + r"((?:\b" + _SZ + r"\b\s*[-,/|]?\s*(?:and\s|y\s|&\s)?\s*){2,})")
NUM_SIZE_LIST = re.compile(_SIZECUE + r"((?:\b\d{2}\b\s*[,/|]\s*)+\b\d{2}\b)")
ONE_SIZE = re.compile(r"\bone[ -]size(?: fits (?:all|most))?\b|\btalla [uú]nica\b", re.I)


def size_label(tok):
    t = tok.upper()
    return {"XXL": "2XL", "XXXL": "3XL", "XXXXL": "4XL", "XXXXXL": "5XL"}.get(t, t)


def first_hit(sources, table):
    """(value, matched_text, loc) for the earliest match in the first source that has one."""
    for loc, text in sources:
        best = None
        for value, pattern in table:
            m = re.search(pattern, text or "", re.I)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), value, m.group(0))
        if best:
            return best[1], best[2], loc
    return None


def all_hits(sources, table):
    """[(value, matched_text, loc)] for every table value found in any source, one per value, table order."""
    out = {}
    for loc, text in sources:
        for value, pattern in table:
            m = re.search(pattern, text or "", re.I)
            if m and value not in out:
                out[value] = (value, m.group(0), loc)
    return [out[v] for v, _ in table if v in out]


def find_sizes(sources):
    """(sizes, matched_text, loc): one size, an uppercase letter range (expanded), or an explicit size list."""
    for loc, text in sources:
        text = text or ""
        m = ONE_SIZE.search(text)
        if m:
            return ["one_size"], m.group(0), loc
        m = SIZE_LIST.search(text)
        full = [size_label(t) for t in re.findall(r"\b" + _SZ + r"\b", m.group(1))] if m else []
        if len(full) >= 3:  # "S-M-L-XL" is a list, not the range S..M
            return list(dict.fromkeys(full)), m.group(0).strip(" ,/|&-"), loc
        for m in SIZE_RANGE.finditer(text):
            a, b = size_label(m.group(1)), size_label(m.group(2))
            if a in SIZE_ORDER and b in SIZE_ORDER and SIZE_ORDER.index(a) < SIZE_ORDER.index(b):
                return SIZE_ORDER[SIZE_ORDER.index(a):SIZE_ORDER.index(b) + 1], m.group(0), loc
        m = SIZE_LIST.search(text)
        if m:
            sizes = list(dict.fromkeys(size_label(t) for t in re.findall(r"\b" + _SZ + r"\b", m.group(1))))
            if len(sizes) >= 2:
                return sizes, m.group(0).strip(" ,/|&-"), loc
        m = NUM_SIZE_LIST.search(text)
        if m:
            return list(dict.fromkeys(re.findall(r"\d{2}", m.group(1)))), m.group(0).strip(), loc
    return None


def extra_fields(sources):
    """TEAM-37 rules -> ({field: value}, [(field, value, source_text, loc)]) for the 7 extra fields."""
    values, evs = {}, []
    for field, table in (("materials.fabric_type", FABRIC_TYPE), ("materials.texture", TEXTURE),
                         ("fit_and_style.shirt_length", SHIRT_LENGTH), ("fit_and_style.style", STYLE),
                         ("fit_and_style.collar_type", COLLAR_TYPE)):
        hit = first_hit(sources, table)
        if hit:
            values[field] = hit[0]
            evs.append((field, hit[0], hit[1], hit[2]))
    care = all_hits(sources, CARE)
    found = {c[0] for c in care}
    drop = ({"tumble_dry"} if "do_not_tumble_dry" in found else set()) | ({"iron_low"} if "do_not_iron" in found else set())
    care = [c for c in care if c[0] not in drop]
    if care:
        values["care"] = [c[0] for c in care]
        evs += [("care", c[0], c[1], c[2]) for c in care]
    sz = find_sizes(sources)
    if sz:
        values["variants.sizes"] = sz[0]
        evs.append(("variants.sizes", sz[0], sz[1], sz[2]))
    return values, evs


# ---- record builder ---------------------------------------------------------------------

def text_sources(raw, kinds=ATTRIBUTE_SECTIONS):
    """(source_location, text) pairs searched for attributes, most specific first."""
    out = [("raw_product_name", raw["raw_product_name"])]
    out += [(f"raw_bullet_points[{i}]", b) for i, b in enumerate(raw["raw_bullet_points"] or [])]
    for i, s in enumerate(raw["raw_description"]["sections"] or []):
        if s["section_type"] in kinds:
            out += [(f"raw_description.sections[{i}].text", s["text"])]
    return [(loc, t) for loc, t in out if t]


RAW_KEEP = {"raw_json_ld", "raw_product_schema", "raw_offer_schema", "raw_product_group_schema", "raw_variant_schema",
            "source_url", "final_url", "canonical_url", "image_urls", "url", "image_url"}


ENTITY = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")


def unescape(s):
    """The single entity decoder: ";"-terminated named, decimal and hex entities, repeated until stable
    ("Lord&#x20;of" -> "Lord of", "&amp;amp;" -> "&"). Text like "cotton&notice" is left as is."""
    for _ in range(5):
        decoded = ENTITY.sub(lambda m: html.unescape(m.group(0)), s)
        if decoded == s:
            break
        s = decoded
    return s


def decoded_text(value, key=None):
    """A copy of a raw record (or part) with entities decoded in text fields; schema blobs and URLs untouched."""
    if key in RAW_KEEP:
        return value
    if isinstance(value, str):
        return unescape(value)
    if isinstance(value, list):
        return [decoded_text(v) for v in value]
    if isinstance(value, dict):
        return {k: decoded_text(v, k) for k, v in value.items()}
    return value


def build_normalized(raw):
    """Rules run on entity-decoded text (decoded_text); the stored raw record itself is not changed."""
    raw = decoded_text(raw)
    url = raw["final_url"]
    evidence, conflicts, flags = [], [], []

    def ev(field, value, text, loc, method="rule", conf=0.9, note=None):
        evidence.append({"field": field, "value": value, "source_text": text, "source_location": loc,
                         "source_url": url, "method": method, "confidence": conf, "note": note})

    def lookup(field, table, sources):
        """First hit wins; distinct values from other sources -> conflict, value null."""
        seen = {}
        for loc, text in sources:
            for value, m in match_lookup(text, table)[:1]:
                seen.setdefault(value, (m, loc))
        if not seen:
            return None
        if len(seen) > 1:
            conflicts.append({"field": field, "status": "conflicting", "resolution": None,
                              "observations": [{"value": m, "source": loc} for m, loc in seen.values()]})
            flags.append("conflict_" + field.split(".")[-1])
            return None
        value, (m, loc) = next(iter(seen.items()))
        ev(field, value, m, loc)
        return value

    sources = text_sources(raw)
    name_src = [("raw_product_name", raw["raw_product_name"])] if raw["raw_product_name"] else []

    # Materials: first line whose percentages sum to 100; a different composition elsewhere is a conflict.
    comps = []
    for loc, text in sources:
        lines = text.split("\n")
        for i in range(len(lines)):
            for k in range(1, 5):  # a composition may be split over up to 4 consecutive lines
                comp, span = parse_composition("\n".join(lines[i:i + k]))
                if comp:
                    if all(comp != c for c, _, _ in comps):
                        comps.append((comp, span, loc))
                    break
    comp = {}
    if len(comps) == 1:
        comp, span, loc = comps[0]
        note = "Tencel covers lyocell and modal; mapped to other." if "other" in comp and re.search("tencel", span, re.I) else None
        ev("materials.material_percentages", comp, span, loc, "rule", 0.95, note)
    elif len(comps) > 1:
        conflicts.append({"field": "materials.material_percentages", "status": "conflicting", "resolution": None,
                          "observations": [{"value": s, "source": loc} for _, s, loc in comps]})
        flags.append("conflict_material_percentages")
    primary = primary_material(comp)
    if primary:
        ev("materials.primary_material", primary, comps[0][1], comps[0][2], "rule", 0.95)

    gsm = weight_raw = None
    for loc, text in sources:
        w = parse_weight(text)
        if w:
            gsm, weight_raw, method, conf, note = w
            if gsm is not None:
                ev("materials.fabric_weight_gsm", gsm, weight_raw, loc, method, conf, note)
            ev("materials.fabric_weight_raw", weight_raw, weight_raw, loc, "direct", 1.0)
            break

    stretch = None
    for loc, text in sources:
        m = re.search(r"\bstretch(?:y)?\b|\bel[aá]stic[oa]\b", text, re.I)
        if m and not re.search(r"non[- ]stretch|no stretch|sin el[aá]stic", text, re.I):
            stretch = True
            ev("materials.stretch", True, m.group(0), loc, "rule", 0.8)
            break

    category_src = ([("raw_category_text", raw["raw_category_text"])] if raw["raw_category_text"] else []) \
        + [(f"raw_breadcrumbs[{i}]", b) for i, b in enumerate(raw["raw_breadcrumbs"] or [])]
    fit = lookup("fit_and_style.fit", FIT, sources)
    sleeve = lookup("fit_and_style.sleeve_length", SLEEVE, sources + category_src)
    neckline = lookup("fit_and_style.neckline", NECKLINE, sources)
    pattern = None
    for loc, text in sources:
        hit = match_lookup(text, PATTERN)
        if hit:
            pattern = hit[0][0]
            ev("fit_and_style.pattern", pattern, hit[0][1], loc, "rule", 0.8)
            break
    collar = None
    for loc, text in sources:
        m = re.search(r"\b(?:button[ -]down|mandarin|cuban|camp|spread|classic|mao|band|polo|shirt|resort) collar\b"
                      r"|\bcuello (?:mao|camisero|cubano|button[ -]down|italiano|ingl[eé]s|polo|solapa|cl[aá]sico)\b", text, re.I)
        if m:
            collar = m.group(0).lower()
            ev("fit_and_style.collar_type", collar, m.group(0), loc, "direct", 0.9)
            break

    # Product type: style from the name, then category, then breadcrumbs; generic shirts use sleeve.
    type_sources = name_src + category_src
    product_type = None
    for loc, text in type_sources:
        hit = match_lookup(text, PRODUCT_TYPE)
        if hit:
            value, m = hit[0]
            product_type = shirt_type(value, sleeve)
            if value == "_dress_shirt":
                ev("identity.product_type", product_type, m, loc, "rule", 0.75,
                   "Dress/non-iron shirt: long sleeve unless the sleeve evidence says short.")
            elif value == "_shirt" and product_type:
                ev("identity.product_type", product_type, m, loc, "rule", 0.8, "Generic shirt; sleeve length from the sleeve evidence.")
            elif value == "_shirt":
                flags.append("generic_shirt_type_unknown_sleeve")
            else:
                ev("identity.product_type", value, m, loc, "rule", 0.9)
            break

    audience = None
    for loc, text in type_sources + [("source_url", raw["source_url"])]:
        hit = match_lookup(text, AUDIENCE)
        if hit:
            audience, m = hit[0]
            ev("identity.audience", audience, m, loc, "rule", 0.8)
            break

    # Variants
    rv = raw["raw_variants"] or []
    colors, sizes, items = [], [], []
    for i, v in enumerate(rv):
        for opt, val in (v["raw_options"] or {}).items():
            if COLOR_OPTION.match(opt) and val not in [c["original_color_name"] for c in colors]:
                norm = normalize_color(val)
                colors.append({"original_color_name": val, "normalized": norm})
                ev("variants.colors", val, val, f"raw_variants[{i}].raw_options.{opt}", "direct", 1.0)
            if is_size_option(opt, val) and val not in [s["raw_size"] for s in sizes]:
                sizes.append({"raw_size": val, "normalized_size": normalize_size(val)})
                ev("variants.sizes", val, val, f"raw_variants[{i}].raw_options.{opt}", "direct", 1.0)
    if not colors and raw["raw_product_name"]:
        name = raw["raw_product_name"]
        spans = [m for c, p in COLORS.items() for m in re.finditer(r"\b(?:" + p + r")\b", name, re.I)]
        if spans:
            original = name[min(m.start() for m in spans):max(m.end() for m in spans)]
            colors.append({"original_color_name": original, "normalized": normalize_color(original)})
            ev("variants.colors", original, original, "raw_product_name", "rule", 0.7, "Colour taken from the product name; no colour option.")
    offers = raw["raw_offer_schema"] or []
    currency = next((o["priceCurrency"] for o in offers if isinstance(o.get("priceCurrency"), str)), None)
    cur_idx = next((i for i, o in enumerate(offers) if isinstance(o.get("priceCurrency"), str)), None)
    for i, v in enumerate(rv):
        opts = v["raw_options"] or {}
        items.append({
            "variant_id": hash_id("v_", canonical_key(raw["canonical_url"] or url) + "#" + (v["merchant_variant_id"] or v["sku"] or v["gtin"] or "|".join(f"{k}={opts[k]}" for k in sorted(opts)))),
            "merchant_variant_id": v["merchant_variant_id"],
            "color": next((val for k, val in opts.items() if COLOR_OPTION.match(k)), None),
            "size": next((val for k, val in opts.items() if is_size_option(k, val)), None),
            "sku": v["sku"],
            "gtin": v["gtin"] if v["gtin"] and re.fullmatch(r"[0-9]{8,14}", v["gtin"]) else None,
            "mpn": v["mpn"],
            "price": to_price(v["raw_price_text"]),
            "currency": currency,
            "availability": map_availability(v["raw_availability_text"]),
        })
        ev(f"variants.items[{i}]", v["merchant_variant_id"], v["merchant_variant_id"], f"raw_variants[{i}].merchant_variant_id", "direct", 1.0)
    if rv:
        ev("variants.variant_count", len(rv), rv[0]["merchant_variant_id"], "raw_variants[0].merchant_variant_id", "rule", 1.0, "Count of raw_variants.")
    group = raw["raw_product_group_schema"] or {}
    group_id = str(group["productGroupID"]) if group.get("productGroupID") else None
    if group_id:
        ev("variants.product_group_id", group_id, group_id, "raw_product_group_schema.productGroupID", "direct", 1.0)

    # Commerce
    price, sale = to_price(raw["raw_price_text"]), to_price(raw["raw_sale_price_text"])
    if price is not None:
        ev("commerce.price", price, raw["raw_price_text"], "raw_price_text", "direct", 1.0)
    if sale is not None:
        ev("commerce.sale_price", sale, raw["raw_sale_price_text"], "raw_sale_price_text", "direct", 1.0)
    if currency:
        ev("commerce.currency", currency, currency, f"raw_offer_schema[{cur_idx}].priceCurrency", "direct", 1.0)
    avail = map_availability(raw["raw_availability_text"])
    if avail:
        ev("commerce.availability", avail, raw["raw_availability_text"], "raw_availability_text", "rule", 1.0, "Any variant available.")
    rating = to_price(raw["raw_rating_text"])
    reviews = int(float(raw["raw_review_count_text"])) if raw["raw_review_count_text"] and re.fullmatch(r"\d+(\.0)?", raw["raw_review_count_text"]) else None
    if rating is not None:
        ev("commerce.rating", rating, raw["raw_rating_text"], "raw_rating_text", "direct", 1.0)
    if reviews is not None:
        ev("commerce.review_count", reviews, raw["raw_review_count_text"], "raw_review_count_text", "direct", 1.0)
    gtin = raw["gtin"] if raw["gtin"] and re.fullmatch(r"[0-9]{8,14}", raw["gtin"]) else None
    for field in ("sku", "mpn"):
        if raw[field]:
            ev(f"commerce.{field}", raw[field], raw[field], field, "direct", 1.0)
    if gtin:
        ev("commerce.gtin", gtin, gtin, "gtin", "direct", 1.0)
    if raw["brand"]:
        ev("identity.brand", raw["brand"], raw["brand"], "brand", "direct", 1.0)
    if raw["raw_product_name"]:
        ev("identity.product_name", raw["raw_product_name"], raw["raw_product_name"], "raw_product_name", "direct", 1.0)

    care = [ln for ln in (raw["raw_care_text"] or "").split("\n") if re.search(r"wash|lav|iron|planch|dry|sec|bleach|lej", ln, re.I)]
    for ln in care:
        ev("care", ln, ln, "raw_care_text", "direct", 1.0)
    features = [ln for ln in (raw["raw_features_text"] or "").split("\n") if ln]
    for ln in features:
        ev("features", ln, ln, "raw_features_text", "direct", 1.0)

    # Quality
    if all(i["availability"] == "out_of_stock" for i in items) and items:
        flags.append("all_variants_out_of_stock")
    for cond, flag in ((not raw["raw_json_ld"], "no_json_ld"), (not comp, "no_material_percentages"),
                       (gsm is None, "no_fabric_weight"), (fit is None, "no_fit"), (sleeve is None, "no_sleeve_length"),
                       (currency is None, "no_currency"), (rating is None, "no_rating_on_page"),
                       (product_type is None, "no_product_type"), (conflicts, "conflicts_present")):
        if cond:
            flags.append(flag)
    if not raw["raw_product_name"] or price is None:
        status = "reject"
    elif comp and (fit or sleeve) and currency and sizes and not conflicts and product_type:
        status = "high"
    elif comp or fit or sleeve or neckline:
        status = "medium"
    else:
        status = "low"

    bullets = [BULLET_RE.sub("", b) for b in raw["raw_bullet_points"] or []]
    return {
        "schema_version": raw["schema_version"],
        "record_type": "normalized",
        "product_id": raw["product_id"],
        "source": {"url": raw["source_url"], "canonical_url": raw["canonical_url"], "merchant": raw["merchant_name"],
                   "merchant_domain": raw["merchant_domain"], "scraped_at": raw["scraped_at"], "language": lang_code(raw["page_language"])},
        "identity": {"brand": raw["brand"], "product_name": raw["raw_product_name"], "product_type": product_type,
                     "subcategory": None, "audience": audience},
        "content": {"title": raw["raw_title"], "full_description": raw["raw_full_description"],
                    "short_description": raw["raw_short_description"], "bullet_points": [b for b in bullets if b],
                    "meta_title": raw["raw_meta_title"], "meta_description": raw["raw_meta_description"], "h1": raw["raw_h1"]},
        "materials": {"primary_material": primary, "material_percentages": comp, "fabric_type": None,
                      "fabric_weight_gsm": gsm, "fabric_weight_raw": weight_raw, "stretch": stretch, "texture": None},
        "fit_and_style": {"fit": fit, "neckline": neckline, "collar_type": collar, "sleeve_length": sleeve,
                          "shirt_length": None, "pattern": pattern, "style": None},
        "variants": {"product_group_id": group_id, "colors": colors, "sizes": sizes,
                     "variant_count": len(rv) if rv else None, "items": items},
        "features": features,
        "care": care,
        "commerce": {"price": price, "sale_price": sale, "currency": currency, "availability": avail, "rating": rating,
                     "review_count": reviews, "sku": raw["sku"], "gtin": gtin, "mpn": raw["mpn"]},
        # "@fallback" nodes were read from microdata/meta tags/page text by extract.py, not from JSON-LD.
        "structured_data": {"product_schema_present": bool(raw["raw_product_schema"] and "@fallback" not in raw["raw_product_schema"]
                                                           or raw["raw_variant_schema"]),
                            "offer_schema_present": any(not o.get("@fallback") for o in offers),
                            "product_group_present": bool(raw["raw_product_group_schema"]),
                            "raw_json_ld": raw["raw_json_ld"] or []},
        "evidence": evidence,
        "conflicts": conflicts,
        "quality_status": status,
        "quality_flags": list(dict.fromkeys(flags)),
        "human_reviewed": False,
    }
