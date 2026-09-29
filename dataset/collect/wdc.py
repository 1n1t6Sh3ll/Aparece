"""Web Data Commons schema.org Product subset (2024-12, Common Crawl Oct 2024) -> raw shirt records.

  python dataset/collect/wdc.py --files part_1156.gz [--local-dir DIR] [--max-products 1500] [--per-domain 30]

Each N-Quads line is `subject predicate object graph .`; the graph is the page URL. Quads are
grouped by page, Product entities that are T-shirts (name/category) become one raw record each.
Only schema.org data is available (no page HTML), so HTML-only raw fields stay null.
Part files are streamed from WDC_BASE when not found in --local-dir; nothing is written to disk.
"""
import argparse
import gzip
import html
import io
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from extract import SCHEMA_VERSION, canonical_key, hash_id, text_or_none  # noqa: E402
from normalize import build_normalized  # noqa: E402
from run import NORM_FILE, NOT_SHIRT, OUT, RAW_FILE, SHIRT, clean, report  # noqa: E402

WDC_BASE = "https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific/Product/"
CRAWL_DATE = "2024-10-01T00:00:00Z"  # WDC 2024-12 = Common Crawl October 2024; no per-page fetch time is published
SDO = re.compile(r"^https?://schema\.org/", re.I)
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
TEE = re.compile(r"\b(t-?shirts?|tee-?shirts?|tees?|camisetas?|playeras?|remeras?)\b", re.I)
NOT_TEE = re.compile(r"\b(polos?|camisas?|button[- ]?(down|up)|henleys?|golf|transfers?|vinyl|svg|png|mock-?ups?|templates?|"
                     r"stickers?|mugs?|tazas?|posters?|totes?|bags?|bolsas?|patterns?|quilts?|books?|ebooks?|prints? only|"
                     r"digital|download|dtf|sublima\w*|plotter|ball|batting|conjuntos?|kits?|sets?|bundles?|tee time|tee box|decals?|cards?|necklaces?|pins?)\b", re.I)
QUAD = re.compile(r'^(<[^>]*>|_:\S+)\s+<([^>]*)>\s+(<[^>]*>|_:\S+|"(?:[^"\\]|\\.)*"(?:@[\w-]+|\^\^<[^>]*>)?)\s+<([^>]*)>\s*\.\s*$')
ESC = re.compile(r'\\(?:u([0-9A-Fa-f]{4})|U([0-9A-Fa-f]{8})|(.))')
ESC_CHARS = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", '"': '"', "'": "'", "\\": "\\"}
EN_WORDS = set("the and with for this our you your is of in to made from cotton fabric size fit".split())
ES_WORDS = set("el la los las del con por que una es y algodón tela talla hecho nuestra manga corta".split())
PT_WORDS = set("em com do da dos das não você algodão tamanho feito uma malha manga curta infantil gola".split())


# ---- quad parsing (unit tested) ----------------------------------------------------------

def unescape(s):
    """N-Quads string/IRI escapes -> text (\\uXXXX, \\UXXXXXXXX, \\n, \\", ...). HTML entities are kept."""
    return ESC.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)) if (m.group(1) or m.group(2))
                   else ESC_CHARS.get(m.group(3), "\\" + m.group(3)), s)


def term(t):
    """('iri'|'bnode'|'lit', value) for one N-Quads term."""
    if t.startswith("<"):
        return "iri", unescape(t[1:-1])
    if t.startswith("_:"):
        return "bnode", t
    return "lit", unescape(t[1:t.rindex('"')])


def parse_quad(line):
    """One N-Quads line -> (subject, predicate, (kind, object), graph), or None if malformed."""
    m = QUAD.match(line.strip())
    if not m:
        return None
    return term(m.group(1))[1], unescape(m.group(2)), term(m.group(3)), unescape(m.group(4))


def local(pred):
    """schema.org predicate -> local name with a lowercase first letter (WDC has 'Offers', 'Availability')."""
    if pred == RDF_TYPE:
        return "@type"
    if not SDO.match(pred):
        return None
    name = SDO.sub("", pred)
    return name[:1].lower() + name[1:]


def page_nodes(quads):
    """{subject: {prop: [(kind, value), ...]}} for one page's quads; non-schema.org predicates dropped."""
    nodes = defaultdict(lambda: defaultdict(list))
    for s, p, o, _ in quads:
        name = local(p)
        if name:
            if name == "@type":
                o = ("lit", SDO.sub("", o[1]))
            nodes[s][name].append(o)
    return nodes


def to_tree(nodes, subject, depth=0, seen=()):
    """Nested dict of one entity, blank/IRI references resolved within the page (cycle-safe)."""
    out = {"@id": subject}
    for prop, values in nodes[subject].items():
        vals = []
        for kind, v in values:
            if kind != "lit" and v in nodes and v not in seen and depth < 4:
                vals.append(to_tree(nodes, v, depth + 1, seen + (subject,)))
            else:
                vals.append(v)
        out[prop] = vals[0] if len(vals) == 1 else vals
    return out


def products(nodes):
    """Top-level Product entities: typed Product and not the object of another node's property."""
    referenced = {v for n in nodes.values() for vals in n.values() for k, v in vals if k != "lit"}
    return [s for s, n in nodes.items() if ("lit", "Product") in n.get("@type", []) and s not in referenced]


# ---- raw record ---------------------------------------------------------------------------

def first(x, *keys):
    """First non-empty string value of x (or of x[key] for the first key present)."""
    for k in keys or (None,):
        v = x.get(k) if k is not None and isinstance(x, dict) else x
        for item in v if isinstance(v, list) else [v]:
            if isinstance(item, dict):
                item = first(item, "name", "contentUrl", "url")
            if isinstance(item, str) and item.strip():
                return text_or_none(item)
    return None


def as_list(x):
    return x if isinstance(x, list) else [] if x is None else [x]


def domain_of(url):
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def detect_language(text):
    """'en', 'es' or 'other' (Portuguese and all other languages) from stop-word counts."""
    words = re.findall(r"[a-záéíóúñüãõç]+", (text or "").lower())
    en, es, pt = (sum(w in ws for w in words) for ws in (EN_WORDS, ES_WORDS, PT_WORDS))
    if re.search(r"\b(playeras?|remeras?)\b", text or "", re.I):
        es += 2
    if max(en, es) < 2 or pt >= max(en, es):
        return "other" if words else None
    return "en" if en > es else "es" if es > en else "other"


def is_tee(name, category):
    text = f"{name or ''} | {category or ''}"
    return bool(TEE.search(text)) and not NOT_SHIRT.search(text) and not NOT_TEE.search(name or "")


def is_shirt_any(name, category):
    text = f"{name or ''} | {category or ''}"
    return bool(SHIRT.search(text)) and not NOT_SHIRT.search(text) and not NOT_TEE.search(name or "")


def build_raw_wdc(tree, page_url):
    """Product tree (to_tree) -> raw record. Only values stated in the schema.org data are filled."""
    offers = []
    for o in as_list(tree.get("offers")):
        if isinstance(o, dict):
            offers.append(o)
            offers += [x for x in as_list(o.get("offers")) if isinstance(x, dict)]  # AggregateOffer.offers
    variants_src = [v for v in as_list(tree.get("hasVariant")) if isinstance(v, dict)]
    own_url = first(tree, "url")
    url = own_url if own_url and own_url.startswith("http") and domain_of(own_url) == domain_of(page_url) else page_url
    price_offer = next((o for o in offers if first(o, "price", "lowPrice")), {})
    name, desc = first(tree, "name"), first(tree, "description")
    rating = tree.get("aggregateRating") if isinstance(tree.get("aggregateRating"), dict) else {}
    images = [i for i in (first(x) for x in as_list(tree.get("image"))) if i and re.match(r"https?://", i)]

    raw_variants = []
    for v in variants_src:
        vid = first(v, "sku", "productID", "gtin13", "gtin", "@id")
        opts = {k: first(v, k) for k in ("color", "size") if first(v, k)}
        vo = next((o for o in as_list(v.get("offers")) if isinstance(o, dict)), {})
        raw_variants.append({
            "merchant_variant_id": vid, "raw_name": first(v, "name"), "raw_options": opts or None,
            "raw_price_text": first(vo, "price"), "raw_availability_text": first(vo, "availability"),
            "sku": first(v, "sku"), "gtin": first(v, "gtin13", "gtin12", "gtin14", "gtin8", "gtin"), "mpn": first(v, "mpn"),
            "url": first(v, "url") if re.match(r"https?://", first(v, "url") or "") else None, "image_url": None,
        })
    raw_variants = [v for v in raw_variants if v["merchant_variant_id"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "record_type": "raw",
        "product_id": hash_id("p_", canonical_key(url)),
        "source_url": url,
        "final_url": url,
        "canonical_url": None,
        "merchant_name": domain_of(page_url),
        "merchant_domain": domain_of(page_url),
        "brand": first(tree, "brand", "manufacturer"),
        "scraped_at": CRAWL_DATE,
        "page_language": None,
        "raw_product_name": name,
        "raw_title": None, "raw_h1": None, "raw_meta_title": None, "raw_meta_description": None,
        "raw_full_description": desc,
        "raw_short_description": None,
        "raw_description": {"sections": [{"heading": None, "section_type": "overview", "text": desc}] if desc else None,
                            "combined_text": desc},
        "raw_bullet_points": None,
        "raw_specifications": None,
        "raw_material_text": first(tree, "material"),
        "raw_fit_text": None,
        "raw_size_text": "\n".join(dict.fromkeys(filter(None, (first(s) for s in as_list(tree.get("size")))))) or None,
        "raw_color_text": "\n".join(dict.fromkeys(filter(None, (first(c) for c in as_list(tree.get("color")))))) or None,
        "raw_care_text": None, "raw_features_text": None, "raw_shipping_text": None, "raw_return_text": None,
        "raw_price_text": first(price_offer, "price", "lowPrice"),
        "raw_sale_price_text": None,
        "raw_availability_text": first(price_offer, "availability"),
        "raw_rating_text": first(rating, "ratingValue"),
        "raw_review_count_text": first(rating, "reviewCount", "ratingCount"),
        "raw_category_text": first(tree, "category"),
        "raw_breadcrumbs": None,
        "raw_variants": raw_variants or None,
        "raw_json_ld": None,
        "raw_product_schema": tree,
        "raw_offer_schema": offers or None,
        "raw_product_group_schema": None,
        "raw_variant_schema": variants_src or None,
        "image_urls": images or None,
        "image_alt_text": [None] * len(images) or None,
        "sku": first(tree, "sku"),
        "gtin": first(tree, "gtin13", "gtin12", "gtin14", "gtin8", "gtin"),
        "mpn": first(tree, "mpn"),
    }


ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-f]+|[a-z]+\d*);", re.I)


def decode(text):
    """HTML entities (also double-encoded) and literal \\uXXXX escapes -> characters. Normalized text only."""
    if not isinstance(text, str):
        return text
    for _ in range(2):
        text = html.unescape(text)
    text = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), text)
    return re.sub(r"[ \t]+", " ", text).strip() or None


def build_normalized_wdc(raw):
    norm = build_normalized(raw)
    norm["source"]["language"] = detect_language(f"{raw['raw_product_name'] or ''} {raw['raw_full_description'] or ''}")
    for k in ("brand", "product_name"):
        norm["identity"][k] = decode(norm["identity"][k])
    norm["content"]["full_description"] = decode(norm["content"]["full_description"])
    norm["quality_flags"] = [f for f in norm["quality_flags"] if f != "no_json_ld"] + ["wdc_schema_org_only"]
    if norm["commerce"]["price"] is not None and norm["commerce"]["price"] <= 0:
        norm["quality_status"] = "reject"
        norm["quality_flags"].append("zero_price")
    return norm


# ---- streaming ----------------------------------------------------------------------------

def open_part(name, local_dir):
    path = Path(local_dir or ".") / name
    if path.exists():
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    resp = urllib.request.urlopen(WDC_BASE + name, timeout=120)  # streamed, never saved
    return io.TextIOWrapper(gzip.GzipFile(fileobj=resp), encoding="utf-8", errors="replace")


def pages(lines):
    """Yield (page_url, quads) per page; pages of one domain are contiguous in WDC part files,
    so all buffered pages are flushed when the domain changes."""
    buf, dom = defaultdict(list), None
    for line in lines:
        q = parse_quad(line)
        if not q:
            continue
        d = domain_of(q[3])
        if d != dom and buf:
            yield from buf.items()
            buf = defaultdict(list)
        dom = d
        buf[q[3]].append(q)
    yield from buf.items()


def collect(args):
    OUT.mkdir(parents=True, exist_ok=True)
    per_dom, seen, n, skipped = Counter(), set(), 0, Counter()
    match = is_tee if args.types == "tees" else is_shirt_any
    with open(RAW_FILE, "w", encoding="utf-8") as fr, open(NORM_FILE, "w", encoding="utf-8") as fn:
        for part in args.files:
            print(f"[part] {part}", flush=True)
            with open_part(part, args.local_dir) as f:
                for page_url, quads in pages(f):
                    dom = domain_of(page_url)
                    if per_dom[dom] >= args.per_domain or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", dom):
                        continue
                    nodes = page_nodes(quads)
                    for s in products(nodes):
                        tree = to_tree(nodes, s)
                        if not match(first(tree, "name"), first(tree, "category")):
                            continue
                        raw = build_raw_wdc(tree, page_url)
                        if raw["product_id"] in seen or per_dom[dom] >= args.per_domain:
                            skipped["duplicate_url"] += 1
                            continue
                        norm = build_normalized_wdc(raw)
                        seen.add(raw["product_id"])
                        per_dom[dom] += 1
                        n += 1
                        fr.write(json.dumps(raw, ensure_ascii=False) + "\n")
                        fn.write(json.dumps(norm, ensure_ascii=False) + "\n")
                    if n >= args.max_products:
                        break
            print(f"[part done] {part}: {n} records, {len(per_dom)} domains", flush=True)
            if n >= args.max_products:
                break
    report(args)
    clean(args)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--files", nargs="+", required=True, help="WDC part file names, e.g. part_1156.gz")
    ap.add_argument("--local-dir", help="directory holding already-downloaded part files")
    ap.add_argument("--max-products", type=int, default=1500)
    ap.add_argument("--per-domain", type=int, default=30)
    ap.add_argument("--types", choices=["tees", "shirts"], default="tees")
    collect(ap.parse_args())


if __name__ == "__main__":
    main()
