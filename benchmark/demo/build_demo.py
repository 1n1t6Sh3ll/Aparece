"""Build the demo product set (TEAM-44): 25 T-shirt targets from small/independent shops,
3-5 comparable competitors each (analysis.peers), and 5 untouched controls.

  python -m benchmark.demo.build_demo --data <dataset/output/final> [--no-fetch]

Only ids, URLs, brand and product names are written (no scraped text). Each target and
control URL gets ONE robots-respecting fetch via api/safe_fetch; dead ones are dropped.
Currency is not in the dataset; it is approximated from the country TLD for the peer filter.
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
N_EN, N_ES, N_CONTROL, K_PEERS = 13, 12, 5, 4
# Big brands, licensed merch, marketplaces, large retailers, and non-tee items (costumes, tanks).
BIG = re.compile(r"amazon|ebay|etsy|walmart|target\.com|zalando|modalia|redbubble|teepublic|spreadshirt|"
                 r"cafepress|zazzle|merchoid|aliexpress|shein|asos|boohoo|primark|zara|mango|bershka|"
                 r"pull.?bear|stradivarius|massimo|uniqlo|h&m|hm\.com|\bgap\b|levi|nike|adidas|puma|reebok|"
                 r"under.?armour|champion|hanes|gildan|fruit.of.the.loom|carhartt|north.?face|patagonia|"
                 r"columbia|lacoste|tommy|calvin|ralph|hugo|boss|guess|diesel|superdry|jack.?&.?jones|"
                 r"vans|converse|new.?balance|asics|disney|marvel|star.?wars|harry.?potter|lord.of.the.rings|"
                 r"pokemon|nintendo|dc.comics|warner|naf.?naf|el.?corte|liverpool|falabella|mercadoli|"
                 r"dafiti|corona|stussy|fila|wrangler|disfraz|costume|game.of.thrones|god.of.war|trendsi|thingson|tank|sin.mangas|mercedes|mundodeportivo|printify|printful|modalova|quiksilver|regatta|4f|next\.co|marks|m&s|debenhams|jdsports|sportsdirect|decathlon|lidl|kiabi|c&a",
                 re.I)
CURRENCY = {"es": "EUR", "eu": "EUR", "mx": "MXN", "co": "COP", "ar": "ARS", "cl": "CLP", "pe": "PEN",
            "uk": "GBP", "au": "AUD", "ca": "CAD", "nz": "NZD", "ie": "EUR", "de": "EUR", "fr": "EUR"}
SPANISH = re.compile(r"camiseta|playera|remera|polera|franela|manga|algod[oó]n|hombre|mujer", re.I)
ES_TLD = {"es", "mx", "co", "ar", "cl", "pe", "uy"}
FIELDS = [("identity", "audience"), ("identity", "subcategory"), ("fit_and_style", "fit"),
          ("fit_and_style", "pattern"), ("materials", "primary_material")]


def clean(s):
    s = html.unescape(html.unescape(s or "")).strip()
    return re.split(r"\s[|–—]\s|\s-\s(?=[^-]*$)", s)[0].strip() if len(s) > 60 else s


def to_record(r):
    g, raw = r["gold"], r["raw"]
    url = raw.get("canonical_url") or raw.get("source_url") or r["provenance"]["url"]
    tld = r["domain"].rsplit(".", 1)[-1]
    rec = {"product_id": r["product_id"], "source": {"language": r["language"]},
           "commerce": {"currency": CURRENCY.get(tld)},
           "identity": {"product_type": g.get("identity.product_type")}}
    for sec, key in FIELDS:
        rec.setdefault(sec, {})[key] = g.get(f"{sec}.{key}")
    rec["_meta"] = {"url": url, "domain": r["domain"], "brand": clean(raw.get("brand")),
                    "name": clean(raw.get("raw_product_name") or raw.get("raw_title")),
                    "rich": sum(v is not None for v in g.values()), "q": r["provenance"]["quality_status"]}
    return rec


def load(data):
    out = []
    for name in ("train.jsonl", "test_gold.jsonl"):
        with open(Path(data) / name, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r["source"] == "amazon" or r["language"] not in ("en", "es"):
                    continue
                if r["gold"].get("identity.product_type") != "t_shirt":
                    continue
                rec = to_record(r)
                m = rec["_meta"]
                if not m["brand"] or not m["name"] or not m["url"].startswith("http"):
                    continue
                tld = m["domain"].rsplit(".", 1)[-1]
                if r["language"] == "es" and (tld in ("br", "pt") or not (tld in ES_TLD or SPANISH.search(m["name"]))):
                    continue  # dataset "es" label also covers some fr/it/pl pages
                if BIG.search(" ".join([m["url"], m["brand"], m["name"]])):
                    continue
                out.append(rec)
    return out


def own_brand(rec):
    """Small-business signal: the brand sells on its own domain."""
    b = re.sub(r"[^a-z]", "", rec["_meta"]["brand"].lower())
    d = re.sub(r"[^a-z]", "", rec["_meta"]["domain"].split(".")[-2] if "." in rec["_meta"]["domain"] else "")
    return len(b) >= 3 and (b[:6] in d or (len(d) >= 4 and d in b))


CACHE = {}  # url -> live? (so a rerun never fetches a URL twice)


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
    # Own-brand shops first, then richest. A shop is at most one target or control and
    # never a competitor anywhere; a competitor shop may appear in several groups.
    recs.sort(key=lambda r: (not own_brand(r), -r["_meta"]["rich"], r["_meta"]["q"] != "high", r["product_id"]))
    blocked, tried, checks = set(), set(), 0  # blocked = target/control shops

    def peers_of(rec, taken=frozenset()):
        """Distinct shops per group; a product is a competitor in one group only (`taken`)."""
        out, seen = [], set()
        pool = [c for c in recs if c["_meta"]["domain"] not in blocked and c["product_id"] not in taken]
        for _, c in find_peers(rec, pool, k=500):
            if c["_meta"]["domain"] not in seen:
                seen.add(c["_meta"]["domain"])
                out.append(c)
        return out[:K_PEERS]

    targets = {"en": [], "es": []}
    need = {"en": N_EN, "es": N_ES}
    for rec in recs:
        lang, dom = rec["source"]["language"], rec["_meta"]["domain"]
        if len(targets[lang]) >= need[lang] or dom in tried:
            continue
        tried.add(dom)  # one product per shop, live or not
        if len(peers_of(rec)) < 3 or BIG.search(dom):
            continue
        checks += 1
        if live(rec["_meta"]["url"], not a.no_fetch):
            targets[lang].append(rec)
            blocked.add(dom)
    controls = []
    for want in ("en", "es", "en", "es", "en"):  # from the other end of the ranking
        for rec in [r for r in reversed(recs) if r["source"]["language"] == want] + list(reversed(recs)):
            dom = rec["_meta"]["domain"]
            if rec["_meta"]["rich"] < 3 or dom in tried:
                continue  # falls back to any language when `want` runs out
            tried.add(dom)
            checks += 1
            if live(rec["_meta"]["url"], not a.no_fetch):
                controls.append(rec)
                blocked.add(dom)
                break
    rows, taken = [], set()
    for i, rec in enumerate(targets["en"] + targets["es"], 1):
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
    print(f"wrote {OUT.name}: {roles}, targets en={len(targets['en'])} es={len(targets['es'])}, "
          f"fetches={checks}")


if __name__ == "__main__":
    main()
