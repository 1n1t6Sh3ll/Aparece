"""Broken citation rate per model (TEAM-50): are the URLs that AI answers cite still real product pages?

  python -m benchmark.citations --results runs.jsonl [--check] [--status dataset/output/link_status.jsonl]

Citations are the http(s) URLs in each stored answer's response_text (benchmark.match.URL_RE). With --check, cited
URLs not yet in the status file are checked with tools/linkcheck (polite, robots-respecting; no model calls).
broken = gone or redirected_away; unverified = blocked or error; unchecked = not in the status file.
broken_citation_rate = broken / (citations with a verified status: live, gone or redirected_away).
"""
import argparse
import json
from collections import defaultdict

from tools.linkcheck import status as link

from .match import URL_RE
from .metrics import model_key


def cited_urls(text):
    return [m.group(0).rstrip(".,;:!?") for m in URL_RE.finditer(text or "")]


def citation_report(records, statuses=None):
    """{model: {answers, citations, live, broken, unverified, unchecked, broken_citation_rate, broken_urls}}.
    Every citation occurrence counts (an answer citing the same dead URL twice counts twice)."""
    statuses = link.load() if statuses is None else statuses
    ambiguous = {m for m in {r["model"] for r in records}
                 if len({r.get("provider") for r in records if r["model"] == m}) > 1}
    out = defaultdict(lambda: {"answers": 0, "citations": 0, "live": 0, "broken": 0, "unverified": 0,
                               "unchecked": 0, "broken_urls": set()})
    for r in records:
        row = out[model_key(r, ambiguous)]
        row["answers"] += 1
        for u in cited_urls(r.get("response_text")):
            row["citations"] += 1
            s = (statuses.get(link.url_key(u)) or {}).get("status")
            if s in link.EXCLUDE:
                row["broken"] += 1
                row["broken_urls"].add(u)
            elif s in link.UNVERIFIED:
                row["unverified"] += 1
            elif s == "live":
                row["live"] += 1
            else:
                row["unchecked"] += 1
    for row in out.values():
        verified = row["live"] + row["broken"]
        row["broken_citation_rate"] = round(row["broken"] / verified, 4) if verified else None
        row["broken_urls"] = sorted(row["broken_urls"])
    return dict(sorted(out.items()))


def citations_markdown(rep):
    lines = ["", "## Broken citations", "",
             "| model | answers | citations | live | broken | unverified | unchecked | broken rate |",
             "|---|---|---|---|---|---|---|---|"]
    for m, r in rep.items():
        rate = "n/a" if r["broken_citation_rate"] is None else f"{r['broken_citation_rate']:.2f}"
        lines.append(f"| {m} | {r['answers']} | {r['citations']} | {r['live']} | {r['broken']} | "
                     f"{r['unverified']} | {r['unchecked']} | {rate} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="benchmark.citations")
    ap.add_argument("--results", required=True, help="harness results JSONL (stored AI answers)")
    ap.add_argument("--status", default=str(link.path()), help="link status JSONL (read, and appended by --check)")
    ap.add_argument("--check", action="store_true", help="check cited URLs not yet in --status")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    with open(a.results, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    if a.check:
        from tools.linkcheck.check import run  # network code only when asked
        urls = list(dict.fromkeys(u for r in records for u in cited_urls(r.get("response_text"))))
        run([(u, None) for u in urls], a.status, a.workers)
    rep = citation_report(records, link.load(a.status))
    print(json.dumps(rep, indent=2, ensure_ascii=False))
    return rep


if __name__ == "__main__":
    main()
