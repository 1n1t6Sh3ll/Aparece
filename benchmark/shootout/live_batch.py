"""Run the live AI comparison on real product pages and summarise the results.

Needs a running API (run.sh) with OPENAI_API_KEY / ANTHROPIC_API_KEY set and the openai + anthropic packages
installed (benchmark/requirements.txt). Each product costs about $0.001-0.003; --max-usd stops the batch.

  python -m benchmark.shootout.live_batch run --out benchmark/results/live-real/report.json [--max-usd 0.5]
  python -m benchmark.shootout.live_batch report benchmark/results/live-real/report.json > report.md
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parent / "demo" / "demo_catalog.jsonl"


def post(base, path, body, timeout=240):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def run(args):
    with open(CATALOG, encoding="utf-8") as f:
        targets = [r for r in map(json.loads, filter(str.strip, f)) if r.get("role") == "target"][:args.limit]
    items, spent = [], 0.0
    for r in targets:
        url, lang = r["source"]["canonical_url"], r["source"].get("language") or "en"
        item = {"group": r["group"], "url": url, "language": lang}
        try:
            a = post(args.base, "/v1/audits", {"url": url, "language": lang})
            rk = a["audit"].get("rank") or {}
            item["audit"] = {"position": rk.get("position"), "total": rk.get("total"),
                             "score": (rk.get("components") or {}).get("score")}
            if spent >= args.max_usd:
                item["skipped"] = "spend cap"
            else:
                o = post(args.base, "/v1/shootout/live", {"product": a["record"], "language": lang})
                item["cost_usd"] = o["cost"]["generation_usd"]
                spent += item["cost_usd"]
                if o.get("available"):
                    item["parts_winner"] = {k: v.get("winner") for k, v in o["overall"]["parts"].items()}
                    item["generators"] = {g: {"qualified": v.get("qualified"), "flagged": v.get("flagged"),
                                              "unsupported_claims": v.get("unsupported_claims"),
                                              "error": (v.get("raw") or {}).get("error"),
                                              "title": (v.get("raw") or {}).get("title"),
                                              "tags": (v.get("raw") or {}).get("tags"),
                                              "description": (v.get("raw") or {}).get("text")}
                                          for g, v in o["products"][0]["candidates"].items()}
                else:
                    item["skipped"] = o.get("reason")
        except Exception as e:  # keep going; the failure is recorded on the item
            item["error"] = f"{type(e).__name__}: {e}"[:200]
        items.append(item)
        print(len(items), item.get("error") or item.get("skipped") or "ok", file=sys.stderr, flush=True)
        time.sleep(args.pause)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"spent_usd": round(spent, 6), "items": items}, ensure_ascii=False, indent=1), encoding="utf-8")


def report(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    ok = [i for i in d["items"] if i.get("generators")]
    gens = list(ok[0]["generators"]) if ok else []
    lines = [f"# Live AI comparison on {len(ok)} real products", "",
             f"{len(d['items'])} product pages fetched; {len(ok)} had enough verified facts. Spend: ${d['spent_usd']:.4f}.", "",
             "| Version | Ran | Passed fact check | Flagged sentences (total) | Unsupported claims |", "|---|---|---|---|---|"]
    for g in gens:
        rows = [i["generators"][g] for i in ok if g in i["generators"]]
        ran = [r for r in rows if not r["error"]]
        lines.append(f"| {g} | {len(ran)}/{len(rows)} | {sum(bool(r['qualified']) for r in ran)}/{len(ran)} | "
                     f"{sum(r['flagged'] or 0 for r in ran)} | {sum(r['unsupported_claims'] or 0 for r in ran)} |")
    wins = {}
    for i in ok:
        for part, w in (i.get("parts_winner") or {}).items():
            wins.setdefault(part, {}).setdefault(w, 0)
            wins[part][w] += 1
    lines += ["", "## Part winners (products won)", ""] + [f"- {p}: {w}" for p, w in wins.items()]
    lines += ["", "## Audit rank of each page", "", "| Group | Score | Position |", "|---|---|---|"]
    lines += [f"| {i['group']} | {(i.get('audit') or {}).get('score')} | {(i.get('audit') or {}).get('position')} of {(i.get('audit') or {}).get('total')} |"
              for i in d["items"]]
    errs = [i for i in d["items"] if i.get("error") or i.get("skipped")]
    if errs:
        lines += ["", "## Not compared", ""] + [f"- {i['group']}: {i.get('error') or i.get('skipped')}" for i in errs]
    lines += ["", "Checks facts and listing quality only. It does not measure AI-assistant visibility."]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--base", default="http://127.0.0.1:8000")
    r.add_argument("--out", required=True)
    r.add_argument("--limit", type=int, default=25)
    r.add_argument("--max-usd", type=float, default=0.5)
    r.add_argument("--pause", type=float, default=11, help="seconds between products (live route is rate-limited)")
    p = sub.add_parser("report")
    p.add_argument("path")
    a = ap.parse_args()
    run(a) if a.cmd == "run" else print(report(a.path))
