"""Shopify products.json entry + product page HTML -> raw record (dataset/schema/raw_record.schema.json)."""
import hashlib
import json
import re
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup, NavigableString

SCHEMA_VERSION = "0.1.0"
BLOCK_TAGS = {"p", "br", "li", "div", "td", "tr", "ul", "ol", "table", "section", "article",
              "h1", "h2", "h3", "h4", "h5", "h6", "details", "summary", "dd", "dt", "blockquote"}
BULLET_RE = re.compile(r"^\s*(?:→|•|·|-|\*|✓|✔|–)\s*")
SECTION_TYPES = [  # (section_type, heading keywords); first match wins
    ("size_guide", r"size guide|size chart|gu[ií]a de tallas|tabla de tallas|sizing"),
    ("shipping", r"shipping|delivery|env[ií]o|entrega"),
    ("returns", r"return|devoluc"),
    ("care", r"care|washing|cuidado|lavado"),
    ("fabric", r"fabric|material|composition|composici[oó]n|tejido"),
    ("fit", r"\bfit\b|ajuste|medidas|measurements"),
    ("sustainability", r"impact|sustainab|sostenib"),
    ("features", r"feature|caracter[ií]stica|benefit"),
    ("details", r"detail|detalle|specification"),
    ("overview", r"description|descripci[oó]n|overview|about|product"),
]


def html_lines(node):
    """Spec extraction rule: block elements -> line breaks, inline tags removed, entities decoded,
    whitespace collapsed inside a line, empty lines dropped."""
    if isinstance(node, str):
        node = BeautifulSoup(node, "html.parser")
    out = []

    def walk(n):
        for child in n.children:
            if isinstance(child, NavigableString):
                if child.__class__.__name__ in ("Comment", "Script", "Stylesheet", "Doctype"):
                    continue
                out.append(str(child))
            elif child.name in ("script", "style", "noscript", "template", "svg"):
                continue
            elif child.name in BLOCK_TAGS:
                out.append("\n")
                walk(child)
                out.append("\n")
            else:
                walk(child)

    walk(node)
    lines = (re.sub(r"\s+", " ", ln).strip() for ln in "".join(out).split("\n"))
    return [ln for ln in lines if ln]


def text_or_none(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s or None


def canonical_key(url):
    """Spec: lowercase scheme and host, drop query and fragment, drop trailing slash."""
    p = urlsplit(url)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip("/") or "/", "", ""))


def hash_id(prefix, text):
    return prefix + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def section_type(heading):
    h = (heading or "").lower()
    for kind, pattern in SECTION_TYPES:
        if re.search(pattern, h):
            return kind
    return "other"


LD_WRAPPERS = re.compile(r"<!--|-->|<!\[CDATA\[|\]\]>|^\s*//.*$", re.M)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TRAILING_COMMA = re.compile(r",\s*([}\]])")


def lenient_json(text):
    """Values in one ld+json script: strict JSON first; else without HTML comment/CDATA wrappers, control characters
    and trailing commas, reading several concatenated values. [] when nothing parses."""
    try:
        return [json.loads(text, strict=False)]
    except ValueError:
        pass
    text = TRAILING_COMMA.sub(r"\1", CONTROL_CHARS.sub(" ", LD_WRAPPERS.sub("", text)))
    dec, out, i = json.JSONDecoder(strict=False), [], 0
    while True:
        start = min((j for j in (text.find("{", i), text.find("[", i)) if j >= 0), default=-1)
        if start < 0:
            return out
        try:
            value, i = dec.raw_decode(text, start)
            out.append(value)
        except ValueError:
            i = start + 1


def json_ld_nodes(soup):
    """(parsed ld+json blocks, flat list of dict nodes incl. @graph members). When no Product/ProductGroup node
    exists, a node read from other page markup (fallback_product) is appended, marked "@fallback"."""
    blocks, nodes = [], []
    for tag in soup.find_all("script", type=lambda t: bool(t) and "ld+json" in t.lower()):
        for data in lenient_json(tag.string or tag.get_text()):
            blocks.append(data)
            stack = [data]
            while stack:
                item = stack.pop(0)
                if isinstance(item, list):
                    stack[:0] = item
                elif isinstance(item, dict):
                    graph = item.get("@graph")
                    if isinstance(graph, (list, dict)):
                        stack[:0] = graph if isinstance(graph, list) else [graph]
                    if set(item) - {"@context", "@graph"}:
                        nodes.append(item)
    if not any(ld_type(n, "Product") or ld_type(n, "ProductGroup") for n in nodes):
        fb = fallback_product(soup)
        if fb:
            nodes.append(fb)
    return blocks, nodes


def ld_type(node, name):
    """True if @type is name (also "schema:Product" / "https://schema.org/Product" forms)."""
    t = node.get("@type")
    return any(isinstance(x, str) and re.split(r"[/:]", x)[-1] == name for x in (t if isinstance(t, list) else [t]))


def fallback_product(soup):
    """Product facts from non-JSON-LD markup: schema.org microdata, hidden js-product-markup-* spans (pages that
    build their JSON-LD in JavaScript), Open Graph / product:* meta tags, then <h1>. Returns a Product-like node
    marked "@fallback" (so it never counts as JSON-LD schema), or None without both a name and a price."""
    scope = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product/?$", re.I)})

    def micro(name, own=False):
        for el in (scope.find_all(attrs={"itemprop": name}) if scope else []):
            if own and el.find_parent(attrs={"itemscope": True}) is not scope:
                continue
            v = text_or_none(el.get("content") or (el.get("href") if el.name == "link" else None) or el.get_text(" "))
            if v:
                return v
        return None

    def markup(name):
        el = soup.find(class_=f"js-product-markup-{name}")
        return text_or_none(el.get_text(" ")) if el else None

    def meta(*names):
        for n in names:
            m = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if m and text_or_none(m.get("content")):
                return text_or_none(m.get("content"))
        return None

    def h1():
        el = soup.find("h1")
        if not el:
            return None
        el = BeautifulSoup(str(el), "html.parser")
        for hidden in el.select(".accessibility-hidden, .sr-only, .visually-hidden, .screen-reader-text"):
            hidden.decompose()
        return text_or_none(el.get_text(" "))

    is_product = (meta("og:type") or "").lower().startswith("product")
    name = micro("name", own=True) or markup("name") or (meta("og:title") if is_product else None) or h1()
    price = micro("price") or markup("offer-price") or meta("product:price:amount", "og:price:amount")
    if not name or not price:
        return None
    source = "microdata" if micro("price") else "page_markup"
    node = {"@type": "Product", "@fallback": source, "name": name}
    for key, value in (("description", micro("description", own=True) or markup("description") or meta("og:description")),
                       ("sku", micro("sku", own=True) or markup("sku")), ("image", markup("image") or meta("og:image"))):
        if value:
            node[key] = value
    offer = {"@type": "Offer", "@fallback": source, "price": price if "." in price else price.replace(",", "."),
             "priceCurrency": micro("priceCurrency") or markup("offer-currency")
             or meta("product:price:currency", "og:price:currency"),
             "availability": micro("availability") or markup("offer-availability") or meta("product:availability")}
    node["offers"] = {k: v for k, v in offer.items() if v}
    rating = markup("rating") or micro("ratingValue")
    count = markup("rating-count") or micro("ratingCount") or micro("reviewCount")
    if rating:
        node["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": rating, **({"ratingCount": count} if count else {})}
    return node


def as_list(x):
    return x if isinstance(x, list) else [] if x is None else [x]


def page_sections(soup, body_lines):
    """Product description sections in page order: accordions/tabs on the page with a recognised
    heading, plus the Shopify description (body_html) if no accordion already contains it."""
    sections, used = [], set()
    headers = soup.select("details > summary, button[aria-controls], [class*='accordion__header'], [class*='collapsible__header']")
    for head in headers:
        if head.find_parent(["header", "nav", "footer"]):
            continue
        if head.name == "summary":
            body, skip = head.parent, len(html_lines(head))
            if body.find("details"):
                continue
        else:
            target = soup.find(id=head.get("aria-controls")) if head.get("aria-controls") else None
            body, skip = target or head.find_next_sibling(), 0
        if body is None or id(body) in used:
            continue
        heading = text_or_none(head.get_text(" "))
        kind = section_type(heading)
        if kind == "other" or len(heading or "") > 60:
            continue
        lines = html_lines(body)[skip:]
        if lines:
            used.add(id(body))
            sections.append({"heading": heading, "section_type": kind, "text": "\n".join(lines)})
    body_text = "\n".join(body_lines)
    if body_lines and not any(body_lines[0] in s["text"] for s in sections):
        sections.insert(0, {"heading": None, "section_type": "overview", "text": body_text})
    return sections or None


def find_lines(lines, pattern):
    hits = [ln for ln in lines if re.search(pattern, ln, re.I)]
    return "\n".join(hits) or None


def build_raw(product, html, url, final_url, store, scraped_at):
    """product: one entry from /products.json; html: product page; store: row of stores.csv."""
    soup = BeautifulSoup(html, "html.parser")
    blocks, nodes = json_ld_nodes(soup)
    group = next((n for n in nodes if ld_type(n, "ProductGroup")), None)
    prod = next((n for n in nodes if ld_type(n, "Product")), None)
    variant_nodes = [v for v in as_list(group.get("hasVariant")) if isinstance(v, dict)] if group else []
    offers = [o for n in ([prod] if prod else []) + variant_nodes for o in as_list(n.get("offers")) if isinstance(o, dict)]
    crumb_node = next((n for n in nodes if ld_type(n, "BreadcrumbList")), None)
    crumbs = [text_or_none(i.get("name") or (i.get("item") or {}).get("name") if isinstance(i.get("item"), dict) else i.get("name"))
              for i in as_list(crumb_node.get("itemListElement"))] if crumb_node else []
    if not any(crumbs):
        crumbs = [text_or_none(a.get_text(" ")) for a in soup.select('nav[aria-label*="readcrumb"] a, .breadcrumb a, .breadcrumbs a')]
    crumbs = [c for c in crumbs if c]

    def meta(**attrs):
        m = soup.find("meta", attrs=attrs)
        return text_or_none(m.get("content")) if m else None

    canonical = soup.find("link", rel="canonical")
    canonical = canonical.get("href") if canonical and canonical.get("href", "").startswith("http") else None
    h1 = soup.find("h1")
    body_lines = html_lines(product.get("body_html") or "")
    sections = page_sections(soup, body_lines)
    combined = "\n\n".join(((s["heading"] + "\n") if s["heading"] else "") + s["text"] for s in sections) if sections else None
    all_lines = [ln for s in (sections or []) for ln in s["text"].split("\n")]
    bullets = [ln for ln in all_lines if BULLET_RE.match(ln) and len(BULLET_RE.sub("", ln)) > 1]
    bullets += [text_or_none(li.get_text(" ")) for li in BeautifulSoup(product.get("body_html") or "", "html.parser").find_all("li")]
    bullets = list(dict.fromkeys(b for b in bullets if b))

    def section_text(kind):
        return "\n".join(s["text"] for s in sections or [] if s["section_type"] == kind) or None

    # Variants come from products.json; GTIN/availability are added from JSON-LD offers when they match.
    def offer_for(v):
        for o in offers:
            if str(v["id"]) in str(o.get("url", "")) or (v.get("sku") and o.get("sku") == v.get("sku")):
                return o
        return None

    option_names = [o["name"] for o in product.get("options", [])]
    raw_variants = []
    for v in product.get("variants", []):
        o = offer_for(v) or {}
        node = next((n for n in variant_nodes if o in as_list(n.get("offers"))), {}) if o else {}
        opts = {name: v.get(f"option{i + 1}") for i, name in enumerate(option_names) if v.get(f"option{i + 1}")}
        gtin = next((str(src.get(k)) for src in (o, node) for k in ("gtin", "gtin13", "gtin12", "gtin14", "gtin8") if src.get(k)), None)
        raw_variants.append({
            "merchant_variant_id": str(v["id"]),
            "raw_name": text_or_none(v.get("title")),
            "raw_options": opts or None,
            "raw_price_text": text_or_none(str(v.get("price") or "")),
            "raw_availability_text": text_or_none(o.get("availability")) or ("true" if v.get("available") else "false"),
            "sku": text_or_none(v.get("sku")),
            "gtin": gtin,
            "mpn": text_or_none(str(o.get("mpn") or node.get("mpn") or "")),
            "url": f"{canonical_key(final_url)}?variant={v['id']}",
            "image_url": (v.get("featured_image") or {}).get("src"),
        })
    first = product.get("variants", [{}])[0]
    compare = first.get("compare_at_price")
    on_sale = compare and first.get("price") and float(compare) > float(first["price"])
    rating = next((n.get("aggregateRating") for n in nodes if isinstance(n.get("aggregateRating"), dict)), None)
    images = [i["src"] for i in product.get("images", []) if str(i.get("src", "")).startswith("http")]
    top = prod or group or {}
    brand = top.get("brand")
    brand = brand.get("name") if isinstance(brand, dict) else brand
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "raw",
        "product_id": hash_id("p_", canonical_key(canonical or final_url)),
        "source_url": url,
        "final_url": final_url,
        "canonical_url": canonical,
        "merchant_name": store["merchant"],
        "merchant_domain": store["domain"],
        "brand": text_or_none(brand) or text_or_none(product.get("vendor")),
        "scraped_at": scraped_at,
        "page_language": text_or_none(soup.html.get("lang") if soup.html else None),
        "raw_product_name": text_or_none(top.get("name")) or text_or_none(product.get("title")),
        "raw_title": text_or_none(soup.title.get_text()) if soup.title else None,
        "raw_h1": text_or_none(h1.get_text(" ")) if h1 else None,
        "raw_meta_title": meta(property="og:title"),
        "raw_meta_description": meta(name="description"),
        "raw_full_description": "\n".join(body_lines) or None,
        "raw_short_description": None,
        "raw_description": {"sections": sections, "combined_text": combined},
        "raw_bullet_points": bullets or None,
        "raw_specifications": None,
        "raw_material_text": section_text("fabric") or find_lines(all_lines, r"\d\s*%|\bgsm\b|g/m|fabric:|tejido:|composition"),
        "raw_fit_text": section_text("fit") or find_lines(all_lines, r"\bfit\b|corte|ajuste"),
        "raw_size_text": None,
        "raw_color_text": None,
        "raw_care_text": section_text("care"),
        "raw_features_text": section_text("features"),
        "raw_shipping_text": section_text("shipping"),
        "raw_return_text": section_text("returns"),
        "raw_price_text": text_or_none(str(compare if on_sale else first.get("price") or "")),
        "raw_sale_price_text": str(first["price"]) if on_sale else None,
        "raw_availability_text": ("true" if any(v.get("available") for v in product["variants"]) else "false")
        if product.get("variants") else None,  # no variants/offers: availability unknown, not out of stock
        "raw_rating_text": text_or_none(str(rating.get("ratingValue", ""))) if rating else None,
        "raw_review_count_text": text_or_none(str(rating.get("reviewCount") or rating.get("ratingCount") or "")) if rating else None,
        "raw_category_text": text_or_none(product.get("product_type")),
        "raw_breadcrumbs": crumbs or None,
        "raw_variants": raw_variants or None,
        "raw_json_ld": blocks or None,
        "raw_product_schema": prod,
        "raw_offer_schema": offers or None,
        "raw_product_group_schema": group,
        "raw_variant_schema": variant_nodes or None,
        "image_urls": images or None,
        "image_alt_text": [text_or_none(i.get("alt")) for i in product.get("images", []) if str(i.get("src", "")).startswith("http")] or None,
        "sku": text_or_none(top.get("sku")),
        "gtin": text_or_none(str(next((top.get(k) for k in ("gtin", "gtin13", "gtin12", "gtin14", "gtin8") if top.get(k)), "") or "")),
        "mpn": text_or_none(top.get("mpn")),
    }
