"""Build the demo product set (TEAM-44): 25 adult short-sleeve T-shirt targets from small,
own-brand shops (~13 EN, up to 12 ES), 3-4 comparable competitors each (analysis.peers),
and 5 untouched controls (2 ES when the pool allows).

  python -m benchmark.demo.build_demo --data <dataset/output/final> [--cache FILE] [--no-fetch]

Only ids, URLs, brand and product names are written (no scraped text). Each target and
control URL gets ONE robots-respecting fetch via api/safe_fetch (cached in --cache so a
rerun never refetches); dead ones are dropped. Language is detected from the record's own
text, not the dataset label. Currency is not in the dataset; it is approximated from the
country TLD for the peer filter.
"""
import argparse
import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "dataset" / "collect"), str(ROOT / "api"), str(ROOT)]
from analysis.peers import find_peers  # noqa: E402

OUT = Path(__file__).resolve().parent / "demo_catalog.jsonl"
N_TARGETS, MAX_ES, N_CONTROL, ES_CONTROLS, K_PEERS = 25, 12, 5, 2, 4
# Big brands, licensed merch, marketplaces and large retailers (not small businesses).
DENY = re.compile(
    r"amazon|ebay|etsy|walmart|target\.com|zalando|modalia|modalova|redbubble|teepublic|spreadshirt|"
    r"cafepress|zazzle|merchoid|aliexpress|shein|asos|boohoo|primark|zara|mango|bershka|pull.?bear|"
    r"stradivarius|massimo|uniqlo|h&m|hm\.com|\bgap\b|levi|nike|adidas|puma|reebok|under.?armour|"
    r"champion|hanes|gildan|fruit.of.the.loom|carhartt|north.?face|patagonia|columbia|lacoste|tommy|"
    r"calvin|ralph|hugo|\bboss\b|guess|diesel|superdry|jack.?&.?jones|vans|converse|new.?balance|asics|"
    r"disney|marvel|star.?wars|harry.?potter|lord.of.the.rings|game.of.thrones|god.of.war|pokemon|"
    r"nintendo|dc.comics|warner|naf.?naf|el.?corte|liverpool|falabella|mercadoli|dafiti|next\.co|"
    r"\bm&s\b|debenhams|jdsports|sportsdirect|decathlon|lidl|kiabi|c&a|printify|printful|trendsi|"
    r"shopbase|thingson|quiksilver|regatta|\b4f\b|fila\b|wrangler|corona|stussy|ripndip|gucci|haiendo|"
    r"yeti|rip.?curl|john.?deere|ncaa|\bnfl\b|\bnba\b|\bmlb\b|r\.?\s?m\.?\s?williams|volcom|umbro|"
    r"palm.?angels|anine.?bing|outdoor.?research|drop.?shot|billabong|oakley|mercedes|mundodeportivo|"
    r"official|licensed|harley|stone.?island|fender|lucky.?brand|modelo|edwin|ice.?cube|dropship|"
    r"customcat|modesens|y-3|abarth|chevrolet|\bford\b|jeep|coca.?cola|pepsi|irn.?bru|steelers|rvca|"
    r"bella.?\+?.?canvas|eras.tour|taylor.swift|golden.knight|\bnhl\b|giii", re.I)
GENERIC_BRAND = {"other", "sindefinir", "dropship", "unbranded", "generic", "es", "en"}
# Adult short-sleeve tees only.
NOT_TEE = re.compile(
    r"long.?sleeve|longsleeve|\bls\b|manga.?larga|mangas.?largas|3/4|raglan|compression|compresi|"
    r"\btank\b|sin.?mangas|tirantes|sleeveless|hood|disfraz|costume|kids?\b|ni[ñn][oa]s?\b|beb[eé]|"
    r"baby|toddler|youth|infant|junior|\bgirls?\b|\bboys?\b|infantil|pack\b|polo\b|crop", re.I)
SPANISH = re.compile(r"camiseta|playera|remera|polera|franela|manga.corta|algod[oó]n|hombre|mujer", re.I)
STOP = {
    "en": "the and with for this our you your is are made from to of in on it".split(),
    "es": "el los las del para y es tu nuestra nuestro por una su camiseta algodón hombre mujer manga".split(),
    "de": "der die das und mit für ist aus ein eine nicht sie".split(),
    "fr": "le les et avec pour est des une vous coton à au du sur".split(),
    "it": "il di e per è una questa cotone sul della gli".split(),
    "pt": "o a os de com para em é uma não algodão".split(),
    "pl": "i w z na do się jest koszulka".split(),
    "nl": "de het en met voor een van is".split(),
}
BAD_TLD = {"de", "at", "ch", "fr", "be", "it", "pt", "br", "pl", "nl", "se", "dk", "no", "fi", "jp", "ru"}
ES_TLD = {"es", "mx", "co", "ar", "cl", "pe", "uy"}
CURRENCY = {"es": "EUR", "eu": "EUR", "mx": "MXN", "co": "COP", "ar": "ARS", "cl": "CLP", "pe": "PEN",
            "uk": "GBP", "au": "AUD", "ca": "CAD", "nz": "NZD", "ie": "EUR"}
FIELDS = [("identity", "audience"), ("identity", "subcategory"), ("fit_and_style", "fit"),
          ("fit_and_style", "pattern"), ("materials", "primary_material")]


def clean(s):
    s = html.unescape(html.unescape(s or "")).strip()
    return re.split(r"\s[|–—]\s|\s-\s(?=[^-]*$)", s)[0].strip() if len(s) > 60 else s


def detect_lang(text):
    words = re.findall(r"[a-záéíóúñüàèìòùçäößąęłśżź]+", text.lower())
    counts = {lang: sum(w in set(sw) for w in words) for lang, sw in STOP.items()}
    best = max(counts, key=counts.get)
    return best if counts[best] >= 2 else None


def to_record(r):
    g, raw = r["gold"], r["raw"]
    url = raw.get("canonical_url") or raw.get("source_url") or r["provenance"]["url"]
    tld = r["domain"].rsplit(".", 1)[-1]
    name = clean(raw.get("raw_product_name") or raw.get("raw_title"))
    desc = clean(((raw.get("raw_description") or {}).get("combined_text") or "")[:2000])
    rec = {"product_id": r["product_id"], "source": {"language": detect_lang(f"{name} {desc}")},
           "commerce": {"currency": CURRENCY.get(tld)},
           "identity": {"product_type": g.get("identity.product_type")}}
    for sec, key in FIELDS:
        rec.setdefault(sec, {})[key] = g.get(f"{sec}.{key}")
    rec["_meta"] = {"url": url, "domain": r["domain"], "tld": tld, "brand": clean(raw.get("brand")),
                    "name": name, "sleeve": g.get("fit_and_style.sleeve_length"),
                    "rich": sum(v is not None for v in g.values()), "q": r["provenance"]["quality_status"]}
    return rec


def keep(rec, label):
    m = rec["_meta"]
    lang = rec["source"]["language"]
    if lang not in ("en", "es") or lang != label or m["tld"] in BAD_TLD:
        return False  # page text must match the dataset label (drops .de/.fr/.it pages labelled en/es)
    if lang == "es" and not (m["tld"] in ES_TLD or SPANISH.search(m["name"])):
        return False  # Spanish-market product: Spanish title or a Spanish-speaking country TLD
    if len(_norm(m["brand"])) < 2 or _norm(m["brand"]) in GENERIC_BRAND or not m["name"] or not m["url"].startswith("http"):
        return False
    if m["sleeve"] not in (None, "short") or rec["identity"]["audience"] == "kids":
        return False
    if NOT_TEE.search(f"{m['url']} {m['name']}") or DENY.search(f"{m['url']} {m['brand']} {m['name']}"):
        return False
    return not reseller(rec)


def load(data):
    out = []
    for name in ("train.jsonl", "test_gold.jsonl"):
        with open(Path(data) / name, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r["source"] == "amazon" or r["gold"].get("identity.product_type") != "t_shirt":
                    continue
                rec = to_record(r)
                if keep(rec, r["language"]):
                    out.append(rec)
    return out


def _norm(s):
    return re.sub(r"[^a-z]", "", s.lower())


def shop_name(domain):
    parts = [p for p in domain.lower().split(".") if p not in ("www", "shop", "store", "es", "en")]
    return _norm(parts[0]) if parts else ""


def own_brand(rec):
    """Small-business signal: the brand sells on its own domain."""
    b, d = _norm(rec["_meta"]["brand"]), shop_name(rec["_meta"]["domain"])
    return len(b) >= 3 and len(d) >= 3 and (b[:6] in d or d in b)


def reseller(rec):
    """A shop selling another brand that it names in the title (e.g. 'Camiseta Fila ...')."""
    b = _norm(rec["_meta"]["brand"])
    return not own_brand(rec) and len(b) >= 3 and b in _norm(rec["_meta"]["name"])


CACHE = {}  # url -> live?


def live(url, fetch):
    if not fetch:
        return True
    if url in CACHE:
        return CACHE[url]
    import safe_fetch
    try:
        safe_fetch.fetch_page(url)
        CACHE[url] = True
    except Exception as e:  # dead, blocked by robots, or unreachable
        print(f"  drop {url}: {getattr(e, 'detail', e)}", file=sys.stderr)
        CACHE[url] = False
    time.sleep(1.0)  # polite pacing
    return CACHE[url]


def row(rec, role, group):
    m = rec["_meta"]
    return {"product_id": rec["product_id"],
            "source": {"canonical_url": m["url"], "merchant_domain": m["domain"],
                       "language": rec["source"]["language"]},
            "identity": {"brand": m["brand"], "product_name": m["name"]},
            "aliases": [], "role": role, "group": group}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--cache", help="JSON url->live cache, read and updated (keep outside the repo)")
    a = ap.parse_args(argv)
    if a.cache and Path(a.cache).exists():
        CACHE.update(json.loads(Path(a.cache).read_text(encoding="utf-8")))
    recs = load(a.data)
    # Own-brand shops first, then explicit short sleeve, then richest. A shop is at most one
    # target or control and never a competitor; a competitor shop may serve several groups.
    recs.sort(key=lambda r: (not own_brand(r), r["_meta"]["sleeve"] != "short", -r["_meta"]["rich"],
                             r["_meta"]["q"] != "high", r["product_id"]))
    blocked, tried, checks = set(), {}, 0  # tried: shop -> attempts

    def peers_of(rec, taken=frozenset()):
        out, seen = [], set()
        pool = [c for c in recs if c["_meta"]["domain"] not in blocked | {rec["_meta"]["domain"]}
                and c["product_id"] not in taken]
        for _, c in find_peers(rec, pool, k=500):
            if c["_meta"]["domain"] not in seen:
                seen.add(c["_meta"]["domain"])
                out.append(c)
        return out[:K_PEERS]

    def pick(cands, n, need_peers, tries=1):
        nonlocal checks
        got = []
        for rec in cands:
            dom = rec["_meta"]["domain"]
            if len(got) >= n:
                break
            if dom in blocked or tried.get(dom, 0) >= tries:
                continue  # one product per shop; `tries` > 1 allows another product after a dead URL
            if need_peers and len(peers_of(rec)) < 3:
                continue
            tried[dom] = tried.get(dom, 0) + 1
            checks += 1
            if live(rec["_meta"]["url"], not a.no_fetch):
                got.append(rec)
                blocked.add(dom)
        return got

    by = {lang: [r for r in recs if r["source"]["language"] == lang] for lang in ("en", "es")}
    # ES controls first (from the low end of the ranking), so the small ES pool still has them.
    controls = pick([r for r in reversed(by["es"]) if r["_meta"]["rich"] >= 3], ES_CONTROLS, False, 2)
    es = pick(by["es"], MAX_ES, True, 2)  # small ES pool: allow a second product per shop
    en = pick(by["en"], N_TARGETS - len(es), True)
    controls += pick([r for r in reversed(by["en"]) if r["_meta"]["rich"] >= 3],
                     N_CONTROL - len(controls), False)
    rows, taken = [], set()
    for i, rec in enumerate(en + es, 1):
        g = f"g{i:02d}"
        peers = peers_of(rec, taken)
        taken |= {c["product_id"] for c in peers}
        rows.append(row(rec, "target", g))
        rows += [row(c, "competitor", g) for c in peers]
    rows += [row(c, "control", "control") for c in controls]
    if a.cache:
        Path(a.cache).write_text(json.dumps(CACHE, indent=0), encoding="utf-8")
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    roles = {k: sum(r["role"] == k for r in rows) for k in ("target", "competitor", "control")}
    ctl = {lang: sum(c["source"]["language"] == lang for c in controls) for lang in ("en", "es")}
    print(f"wrote {OUT.name}: {roles}, targets en={len(en)} es={len(es)}, controls {ctl}, "
          f"new+cached checks={checks}")


if __name__ == "__main__":
    main()
