"""Controlled AI comparison of title, tags and description (TEAM-47, vision section 39 step 14).

For each target product, several generators write its description from the SAME verified facts with the SAME
instructions (the optimizer's own prompt). Each candidate is checked by the optimizer guardrail, scored
deterministically, and placed as the target's page in a simulated shopping context next to its 4 competitors'
real descriptions (shuffled). Judge models answer dev/val shopping prompts (never hidden); the target's mention
rate, top-3 and MRR are measured with benchmark.match / benchmark.metrics. This is a controlled evaluation,
not proof of real-world ranking.

  python -m benchmark.shootout.run --catalog C --data DATASET_DIR --dry-run
  python -m benchmark.shootout.run --catalog C --data DATASET_DIR --max-usd 3
  python -m benchmark.shootout.run --catalog C --report-only

Generators: original (merchant text) | productlens (optimizer, deterministic stub backend) |
productlens@provider:model (optimizer with that LLM; guard + retries) | provider:model (the LLM alone).
"""
import argparse
import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "dataset" / "collect"), str(ROOT / "api")]

from benchmark import harness  # noqa: E402
from benchmark.match import load_catalog, match_response  # noqa: E402
from benchmark.shootout import score  # noqa: E402
from benchmark.shootout.report import LABEL, build, load_rows  # noqa: E402
from optimizer import fix, llm  # noqa: E402
from optimizer.truth import fact_sentences, product_truth  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_GENERATORS = ("original,productlens,productlens@openai:gpt-4o-mini,openai:gpt-4o-mini,"
                      "anthropic:claude-haiku-4-5-20251001")
DEFAULT_JUDGES = "openai:gpt-4o-mini,anthropic:claude-haiku-4-5-20251001"
DESC_CAP = 1500  # characters of any description shown to a judge (same cap for every page)
ID_RE = re.compile(r'\{"product_id":\s*"([^"]+)"')
ASK = {"en": ("Product pages from online shops:\n\n{pages}\n\nShopper question: {q}\nRecommend the best matches "
              "from these products only, most recommended first. Name the brand and product."),
       "es": ("Fichas de producto de tiendas online:\n\n{pages}\n\nPregunta del comprador: {q}\nRecomienda las "
              "mejores opciones solo entre estos productos, la más recomendada primero. Indica la marca y el producto.")}
PAGE = "[{i}] Brand: {brand}\nProduct: {name}\nURL: {url}\n{tags}Description: {desc}"
# LLM generators get the optimizer's own instructions and facts, asked also for tags.
GEN_SYSTEM = fix.SYSTEM.replace('{"title": ..., "description": ...}', '{"title": ..., "description": ..., "tags": [...]}') + (
    " tags: 3-8 short shopping search tags in the output language, from the facts only.")


class BudgetExceeded(Exception):
    pass


class Budget:
    def __init__(self, cap, prices):
        self.cap, self.prices, self.spent, self.calls = cap, prices, 0.0, 0

    def price(self, model):
        return self.prices.get(model, {"input": 0, "output": 0})

    def check(self, model, system, text, max_tokens):
        if self.cap is not None and self.spent + harness.estimate_usd(self.price(model), system, text, max_tokens) > self.cap:
            raise BudgetExceeded(f"spend cap ${self.cap} reached (spent ${self.spent:.4f}); re-run to resume")

    def charge(self, model, out):
        cost = harness.actual_usd(self.price(model), out)
        self.spent, self.calls = self.spent + cost, self.calls + 1
        return cost


class StubGenerator:
    """provider 'mock' for generation: the optimizer's deterministic stub (valid JSON of the fact lines)."""

    def __init__(self, model):
        self.model = model

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        text = llm.stub(system, prompt)
        return {"text": text, "model_version": self.model, "input_tokens": 0, "output_tokens": 0}


def make_adapter(provider, model, products=(), role="judge"):
    if provider == "mock" and role == "gen":
        return StubGenerator(model)
    return harness.make_adapter(provider, model, products)


# ---------- data ----------
def load_records(data_dir, ids):
    """Dataset rows (dataset/output/final/*.jsonl) for `ids`, as normalized records (api.dashboard_api.adapt)."""
    from dashboard_api import adapt
    out = {}
    for p in sorted(Path(data_dir).glob("*.jsonl")):
        with open(p, encoding="utf-8") as f:
            for line in f:
                m = ID_RE.match(line)
                if m and m.group(1) in ids:
                    out[m.group(1)] = adapt(json.loads(line))
    return out


def prepare(rec, cat_row):
    """Brand and name from the catalog (cleaned page values) become verified identity facts; text is unescaped."""
    ident = cat_row["identity"]
    rec["identity"].update(brand=ident["brand"], product_name=ident["product_name"])
    rec["evidence"] = [e for e in rec["evidence"] if e.get("field") not in ("identity.brand", "identity.product_name")]
    rec["evidence"] += [{"field": "identity.brand", "source_text": ident["brand"], "source_location": "raw_brand"},
                        {"field": "identity.product_name", "source_text": ident["product_name"],
                         "source_location": "raw_product_name"}]
    c = rec.get("content") or {}
    text = c.get("full_description") or " ".join(c.get("bullet_points") or [])
    c["full_description"] = html.unescape(text or "").strip()
    rec["content"], rec["source"]["canonical_url"] = c, cat_row["source"]["canonical_url"]
    return rec


def select_groups(cat_rows, records, limit, only=None):
    """Targets with >= fix.MIN_FACTS fact sentences; richest first; about half ES when available."""
    ok = {}
    for r in cat_rows:
        if r.get("role") != "target" or (only and r["group"] not in only):
            continue
        comps = [c for c in cat_rows if c.get("group") == r["group"] and c.get("role") == "competitor"]
        rec, lang = records.get(r["product_id"]), r["source"]["language"]
        if not rec or not comps or any(c["product_id"] not in records for c in comps):
            continue
        truth = product_truth(prepare(rec, r))
        n = len(fact_sentences(truth, lang))
        if n >= fix.MIN_FACTS:
            ok[r["group"]] = {"group": r["group"], "target": r, "competitors": comps, "record": rec, "truth": truth,
                              "language": lang, "facts": n}
    if only:
        return [ok[g] for g in only if g in ok]
    pick = lambda lang: sorted((g for g in ok.values() if g["language"] == lang), key=lambda g: (-g["facts"], g["group"]))  # noqa: E731
    es = pick("es")[:limit // 2]
    return pick("en")[:limit - len(es)] + es


def pick_prompts(prompts, lang, group, n):
    pool = sorted((p for p in prompts if p["language"] == lang), key=lambda p: p["id"])
    return sorted(random.Random(group).sample(pool, min(n, len(pool))), key=lambda p: p["id"])


# ---------- generation ----------
def parse_gen(spec):
    if spec == "original":
        return ("original", None, None)
    if spec == "productlens":
        return ("productlens", "stub", None)
    if spec.startswith("productlens@"):
        prov, model = spec.split("@", 1)[1].split(":", 1)
        return ("productlens", prov, model)
    prov, model = spec.split(":", 1)
    return ("llm", prov, model)


def generate(g, spec, args, budget, factory):
    kind, prov, model = parse_gen(spec)
    rec, truth, lang = g["record"], g["truth"], g["language"]
    row = {"group": g["group"], "product_id": g["target"]["product_id"], "language": lang, "generator": spec,
           "text": None, "title": None, "tags": [], "json_ld": None, "error": None, "cost_usd": 0.0, "calls": 0}
    if kind == "original":  # the page's own name and description; the dataset has no merchant tags
        row.update(text=rec["content"]["full_description"] or None, title=g["target"]["identity"]["product_name"])
        return row
    if kind == "productlens":
        adapter = factory(prov, model, role="gen") if prov != "stub" else None

        def backend(system, user):  # optimizer text backend on the harness adapter (usage + spend tracked)
            budget.check(model, system, user, args.gen_max_tokens)
            out = adapter.complete(system, user, args.gen_temperature, args.gen_max_tokens)
            row["cost_usd"] += budget.charge(model, out)
            row["calls"] += 1
            return out["text"]
        out = fix.generate(rec, lang, None, backend=backend if adapter else "stub")
        row.update(text=out["description"], title=out["title"], tags=score.fact_tags(truth, lang), json_ld=out["json_ld"],
                   removed_sentences=len(out["removed_sentences"]), used_fallback=out["used_fallback"])
        return row
    system, user = GEN_SYSTEM, fix._prompt(truth, lang, [])  # the optimizer's facts and instructions (+ tags)
    budget.check(model, system, user, args.gen_max_tokens)
    out = factory(prov, model, role="gen").complete(system, user, args.gen_temperature, args.gen_max_tokens)
    row["cost_usd"], row["calls"], row["raw_text"] = budget.charge(model, out), 1, out["text"]
    try:
        obj = llm.parse(out["text"])
        tags = obj.get("tags") if isinstance(obj.get("tags"), list) else []
        row.update(text=obj["description"].strip(), title=obj["title"].strip(),
                   tags=[t.strip() for t in tags if isinstance(t, str) and t.strip()])
    except ValueError as e:
        row["error"] = f"unparseable output: {e}"
    return row


# ---------- judging ----------
def target_product(g, cand, products):
    """Catalog entry of the target; a candidate title is added as an alias so the matcher finds it by that name."""
    p = dict(products[g["target"]["product_id"]])
    if cand.get("title") and cand["title"] != p["name"]:
        p["aliases"] = list(p["aliases"]) + [cand["title"]]
    return p


def context(g, cand, prompt, rep, products):
    """Target page with the candidate's title, tags and description + competitors' real pages, in an order fixed
    per (product, prompt, repeat) so every candidate sees the same positions."""
    ids = [g["target"]["product_id"]] + [c["product_id"] for c in g["competitors"]]
    random.Random(f"{g['group']}|{prompt['id']}|{rep}").shuffle(ids)
    pages = []
    for i, pid in enumerate(ids, 1):
        p, tags = products[pid], ""
        if pid == g["target"]["product_id"]:
            desc, name = cand["text"], cand.get("title") or p["name"]
            tags = f"Tags: {', '.join(cand['tags'])}\n" if cand.get("tags") else ""
        else:
            desc, name = g["descriptions"].get(pid), p["name"]
        desc = (desc or "(no description)")[:DESC_CAP]
        pages.append(PAGE.format(i=i, brand=p["brand"], name=name, url=p["url"], tags=tags, desc=desc))
    return ASK[g["language"]].format(pages="\n\n".join(pages), q=prompt["text"]), ids


def plan_judge(groups, candidates, judges, repeats, products):
    for g in groups:
        for c in candidates:
            if c["group"] != g["group"] or not c["text"]:
                continue
            for p in g["prompts"]:
                for rep in range(repeats):
                    text, order = context(g, c, p, rep, products)
                    for prov, model in judges:
                        yield {"key": f"{g['group']}|{c['generator']}|{p['id']}|{prov}:{model}|{rep}", "group": g,
                               "cand": c, "prompt": p, "rep": rep, "text": text, "order": order,
                               "provider": prov, "model": model}


# ---------- run ----------
def append(path, row):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def setup(args):
    cat_rows = load_rows(args.catalog)
    products = {p["product_id"]: p for p in load_catalog(args.catalog)}
    prompts = [p for p in harness.load_prompts(args.prompts) if p["split"] in ("dev", "val")]  # never hidden
    ids = {r["product_id"] for r in cat_rows}
    records = load_records(args.data, ids)
    for r in cat_rows:
        if r["product_id"] in records and r.get("role") == "competitor":
            prepare(records[r["product_id"]], r)
    only = [g.strip() for g in args.groups.split(",")] if args.groups else None
    groups = select_groups(cat_rows, records, args.limit, only)
    for g in groups:
        g["descriptions"] = {c["product_id"]: records[c["product_id"]]["content"]["full_description"]
                             for c in g["competitors"]}
        g["prompts"] = pick_prompts(prompts, g["language"], g["group"], args.prompts_per_product)
        g["intents"] = [p for p in prompts if p["language"] == g["language"]]
    return groups, products


def run(args, factory=make_adapter, log=print, sleep=time.sleep):
    out = Path(args.out_dir)
    gens = [s.strip() for s in args.generators.split(",") if s.strip()]
    judges = [tuple(j.strip().split(":", 1)) for j in args.judges.split(",") if j.strip()]
    prices = json.loads(Path(args.prices).read_text(encoding="utf-8"))["models"]
    groups, products = setup(args)
    if not groups:
        raise SystemExit("no target with enough verified facts and competitor records; check --catalog/--data")
    paid_models = {(prov, model) for prov, model in judges if prov not in harness.FREE}
    paid_models |= {(p, m) for k, p, m in map(parse_gen, gens) if p and m and p not in harness.FREE}
    missing = sorted(m for _, m in paid_models if m not in prices)
    if missing:
        raise SystemExit(f"no price for {missing} in {args.prices}; refusing")
    cand_path, judge_path = out / "candidates.jsonl", out / "judge_calls.jsonl"
    cached = {(r["group"], r["generator"]): r for r in load_rows(cand_path)}
    budget = Budget(args.max_usd, prices)

    if args.dry_run:
        gen_calls, gen_usd = 0, 0.0
        for g in groups:
            for spec in gens:
                kind, prov, model = parse_gen(spec)
                if (g["group"], spec) in cached or not model or prov in harness.FREE:
                    continue
                n = 1 + fix.MAX_RETRIES if kind == "productlens" else 1  # optimizer may regenerate
                gen_calls += n
                gen_usd += n * harness.estimate_usd(budget.price(model), fix.SYSTEM,
                                                    fix._prompt(g["truth"], g["language"], []), args.gen_max_tokens)
        stand_in = [{"group": g["group"], "generator": s, "text": "x" * DESC_CAP, "title": "x" * 90,
                     "tags": ["x" * 20] * 8} for g in groups for s in gens]
        done = harness.done_keys(judge_path)
        calls = [c for c in plan_judge(groups, stand_in, judges, args.repeats, products) if c["key"] not in done]
        paid = [c for c in calls if c["provider"] not in harness.FREE]
        judge_usd = sum(harness.estimate_usd(budget.price(c["model"]), harness.DEFAULT_SYSTEM, c["text"],
                                             args.judge_max_tokens) for c in paid)
        by_lang = {lang: sum(g["language"] == lang for g in groups) for lang in ("en", "es")}
        log(f"dry run: {len(groups)} products {by_lang} ({', '.join(g['group'] for g in groups)}), "
            f"{len(gens)} generators, {len(judges)} judges, {args.prompts_per_product} dev/val prompts x "
            f"{args.repeats} repeats per product")
        log(f"  generation: {gen_calls} paid calls (upper bound), est max ${gen_usd:.4f}")
        log(f"  judging: {len(calls)} calls ({len(paid)} paid, upper bound: every candidate judged), "
            f"est max ${judge_usd:.4f}")
        log(f"  total est max ${gen_usd + judge_usd:.4f}")
        return {"products": len(groups), "gen_calls": gen_calls, "judge_calls": len(calls),
                "est_usd": round(gen_usd + judge_usd, 4)}

    if paid_models and args.max_usd is None:
        raise SystemExit("paid providers require --max-usd (run --dry-run first)")
    for prov in {p for p, _ in paid_models}:
        if not os.environ.get(harness.KEY_ENV[prov]):
            raise SystemExit(f"{harness.KEY_ENV[prov]} not set")
    out.mkdir(parents=True, exist_ok=True)
    try:
        for g in groups:  # generation (cached per product x generator)
            for spec in gens:
                if (g["group"], spec) not in cached:
                    row = generate(g, spec, args, budget, factory)
                    cached[(g["group"], spec)] = row
                    append(cand_path, row)
        cands = [cached[(g["group"], s)] for g in groups for s in gens]
        done = harness.done_keys(judge_path)
        adapters = {}
        for c in plan_judge(groups, cands, judges, args.repeats, products):
            if c["key"] in done:
                continue
            target = c["group"]["target"]["product_id"]
            ctx = [target_product(c["group"], c["cand"], products) if pid == target else products[pid] for pid in c["order"]]
            if c["provider"] == "mock":  # the mock answers from the products it is given
                adapter = factory("mock", c["model"], ctx)
            else:
                adapter = adapters.setdefault(c["provider"] + ":" + c["model"], factory(c["provider"], c["model"]))
            budget.check(c["model"], harness.DEFAULT_SYSTEM, c["text"], args.judge_max_tokens)
            for attempt in range(args.retries + 1):
                try:
                    resp = adapter.complete(harness.DEFAULT_SYSTEM, c["text"], args.judge_temperature,
                                            args.judge_max_tokens, seed=c["rep"])
                    break
                except Exception as e:  # SDK errors vary; retry with backoff
                    if attempt == args.retries:
                        raise
                    log(f"retry {attempt + 1} for {c['key']}: {type(e).__name__}")
                    sleep(2 ** attempt)
            cost = budget.charge(c["model"], resp)
            m = match_response(resp["text"], ctx)
            append(judge_path, {
                "call_key": c["key"], "group": c["group"]["group"], "target": target,
                "language": c["group"]["language"], "generator": c["cand"]["generator"],
                "prompt_id": c["prompt"]["id"], "split": c["prompt"]["split"], "repeat": c["rep"],
                "judge": f"{c['provider']}:{c['model']}", "model_version": resp["model_version"],
                "target_position": c["order"].index(target) + 1, "mentions": m["mentions"],
                "response_text": resp["text"], "cost_usd": round(cost, 6),
                "usage": {"input_tokens": resp["input_tokens"], "output_tokens": resp["output_tokens"]},
                "settings": {"temperature": args.judge_temperature, "max_tokens": args.judge_max_tokens},
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds")})
            if args.min_interval and c["provider"] != "mock":
                sleep(args.min_interval)
    except BudgetExceeded as e:
        log(str(e))
    log(f"{budget.calls} calls, ${budget.spent:.4f} spent")
    return build(args, groups, gens, judges, log)


def parser():
    ap = argparse.ArgumentParser(prog="benchmark.shootout.run", description=LABEL)
    ap.add_argument("--catalog", required=True, help="demo-format catalog (role/group), e.g. benchmark/demo/demo_catalog.jsonl")
    ap.add_argument("--data", help="dataset dir with *.jsonl ground-truth rows (dataset/output/final)")
    ap.add_argument("--out-dir", default=str(HERE / "out"))
    ap.add_argument("--prompts", default=str(HERE.parent / "prompts" / "tshirts.jsonl"))
    ap.add_argument("--prices", default=str(HERE.parent / "prices.json"))
    ap.add_argument("--limit", type=int, default=5, help="targets (about half ES)")
    ap.add_argument("--groups", help="comma list of catalog groups (overrides --limit)")
    ap.add_argument("--generators", default=DEFAULT_GENERATORS)
    ap.add_argument("--judges", default=DEFAULT_JUDGES)
    ap.add_argument("--holdout-judge", default="anthropic:claude-haiku-4-5-20251001")
    ap.add_argument("--prompts-per-product", type=int, default=6)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--gen-temperature", type=float, default=0.0)
    ap.add_argument("--gen-max-tokens", type=int, default=600)
    ap.add_argument("--judge-temperature", type=float, default=0.7)
    ap.add_argument("--judge-max-tokens", type=int, default=400)
    ap.add_argument("--bootstrap", type=int, default=1000)
    ap.add_argument("--max-usd", type=float)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report-only", action="store_true", help="rebuild the report from --out-dir files (needs --data)")
    ap.add_argument("--min-interval", type=float, default=0.5)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--sample", action="store_true", help="mark the report as a sample (mock judges) for the UI")
    return ap


def main(argv=None):
    ap = parser()
    args = ap.parse_args(argv)
    if not args.data:
        ap.error("--data is required")
    if args.report_only:
        groups, _ = setup(args)
        gens = [s.strip() for s in args.generators.split(",") if s.strip()]
        judges = [tuple(j.strip().split(":", 1)) for j in args.judges.split(",") if j.strip()]
        return build(args, groups, gens, judges)
    return run(args)


if __name__ == "__main__":
    main()
