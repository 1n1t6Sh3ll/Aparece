"""Score API models on the same test prompts as the fine-tuned Qwen, with eval.py's metrics.

  python train/api_eval.py --data TEST.jsonl --models openai:gpt-4o-mini anthropic:claude-haiku-4-5-20251001 --dry-run
  python train/api_eval.py --data TEST.jsonl --models ... --max-usd 5

Keys come from OPENAI_API_KEY / ANTHROPIC_API_KEY only. Raw responses are appended to
{out}/{model}_responses.jsonl (resumable; a stored response is reused only while its prompt hash
still matches the data file). The spend cap covers every *_responses.jsonl in --out-dir.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from common import FIELDS, messages  # noqa: E402
from eval import parse, summarize  # noqa: E402
from benchmark.harness import actual_usd, estimate_usd  # noqa: E402

PRICES = HERE.parent / "benchmark" / "prices.json"
# Models that reject temperature; thinking is switched off so output is the answer only.
NO_TEMPERATURE = {"claude-sonnet-5-5": {"thinking": {"type": "between_tools"}}}


def load_rows(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    for r in rows:
        # The stored prompt is exactly what eval.py feeds Qwen; rebuild it only if absent.
        msgs = r["messages"][:-1] if r.get("messages") else messages(r["raw"])
        r["_system"], r["_user"] = msgs[0]["content"], msgs[1]["content"]
        r["_gold"] = json.loads(r["messages"][-1]["content"]) if r.get("messages") else r["gold"]
        r["_hash"] = hashlib.sha256((r["_system"] + "\0" + r["_user"]).encode()).hexdigest()[:16]
    return rows


def stratified(rows, n):
    """Deterministic subset of n rows, proportional per (language, source)."""
    groups = {}
    for r in sorted(rows, key=lambda r: hashlib.sha256(r["product_id"].encode()).hexdigest()):
        groups.setdefault((r.get("language"), r.get("source")), []).append(r)
    quota = {k: len(v) * n / len(rows) for k, v in groups.items()}
    take = {k: int(q) for k, q in quota.items()}
    for k in sorted(quota, key=lambda k: take[k] - quota[k])[:n - sum(take.values())]:
        take[k] += 1
    return [r for k, v in groups.items() for r in v[:take[k]]]


def safe(model):
    return model.replace("/", "_").replace(":", "_")


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()] if Path(path).exists() else []


def total_spent(out_dir):
    return sum(x.get("cost_usd", 0) for p in Path(out_dir).glob("*_responses.jsonl") for x in read_jsonl(p))


def call(provider, model, system, user, max_tokens):
    extra = NO_TEMPERATURE.get(model)
    if provider == "openai":
        import openai
        r = openai.OpenAI().chat.completions.create(
            model=model, temperature=0, max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return {"text": r.choices[0].message.content or "", "model_version": r.model,
                "stop": r.choices[0].finish_reason, "input_tokens": r.usage.prompt_tokens,
                "output_tokens": r.usage.completion_tokens, "raw": r.model_dump(mode="json")}
    if provider == "anthropic":
        import anthropic
        kw = extra if extra is not None else {"temperature": 0}
        r = anthropic.Anthropic().messages.create(
            model=model, system=system, max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}], **kw)
        return {"text": "".join(b.text for b in r.content if b.type == "text"), "model_version": r.model,
                "stop": r.stop_reason, "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens, "raw": r.model_dump(mode="json")}
    raise ValueError(f"unknown provider {provider!r}")


def run(args, rows, prices, call=call, log=print):
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    spent = total_spent(out)
    todo, est = [], 0.0
    for spec in args.models:
        provider, model = spec.split(":", 1)
        if model not in prices:
            raise SystemExit(f"{model} missing from {PRICES}; refusing a paid run")
        done = {x["product_id"]: x["prompt_hash"] for x in read_jsonl(out / f"{safe(model)}_responses.jsonl")}
        for r in rows:
            if done.get(r["product_id"]) != r["_hash"]:
                todo.append((provider, model, r))
                est += estimate_usd(prices[model], r["_system"], r["_user"], args.max_tokens)
    log(f"{len(todo)} calls to make; upper-bound estimate ${est:.4f}; already spent ${spent:.4f}; cap ${args.max_usd}")
    if args.dry_run:
        for spec in args.models:
            log(f"  {spec}: {sum(1 for p, m, _ in todo if f'{p}:{m}' == spec)} calls")
        return spent
    for provider, model, r in todo:
        if spent + estimate_usd(prices[model], r["_system"], r["_user"], args.max_tokens) > args.max_usd:
            log(f"spend cap ${args.max_usd} would be exceeded (spent ${spent:.4f}); stopping.")
            break
        t0 = time.time()
        try:
            o = call(provider, model, r["_system"], r["_user"], args.max_tokens)
        except Exception as e:  # keep going; the row stays undone and is retried on the next run
            log(f"{model} {r['product_id']}: {type(e).__name__}: {e}")
            continue
        cost = actual_usd(prices[model], o)
        spent += cost
        rec = {"product_id": r["product_id"], "prompt_hash": r["_hash"], "model": model,
               "model_version": o["model_version"], "timestamp": datetime.now(timezone.utc).isoformat(),
               "latency_ms": round((time.time() - t0) * 1000), "stop": o["stop"],
               "usage": {"input_tokens": o["input_tokens"], "output_tokens": o["output_tokens"]},
               "cost_usd": cost, "text": o["text"], "raw": o["raw"]}
        with open(out / f"{safe(model)}_responses.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"total spent in {out}: ${spent:.4f}")
    return spent


def score(rows, resp):
    """eval.py summary, plus per-language and per-source breakdowns. Missing responses count as invalid."""
    by_id = {x["product_id"]: x for x in resp}

    def summ(rs):
        return summarize([parse(by_id[r["product_id"]]["text"]) if r["product_id"] in by_id else None
                          for r in rs], [r["_gold"] for r in rs])

    res = summ(rows)
    for key, col in (("by_language", "language"), ("by_source", "source")):
        res[key] = {v: summ([r for r in rows if r.get(col) == v]) for v in sorted({r.get(col) for r in rows})}
    got = [by_id[r["product_id"]] for r in rows if r["product_id"] in by_id]
    res.update({
        "answered": len(got), "complete": len(got) == len(rows),
        "model_versions": sorted({x["model_version"] for x in got}),
        "cost_usd": round(sum(x["cost_usd"] for x in got), 6),
        "usage": {k: sum(x["usage"][k] for x in got) for k in ("input_tokens", "output_tokens")},
        "latency_ms": round(sum(x["latency_ms"] for x in got) / max(len(got), 1)),
        "stop_reasons": {s: sum(x["stop"] == s for x in got) for s in {x["stop"] for x in got}},
    })
    return res


def report(args, rows):
    out = Path(args.out_dir)
    golds = [r["_gold"] for r in rows]
    baseline = summarize([{f: None for f in FIELDS} for _ in golds], golds)
    results = {}
    for spec in args.models:
        model = spec.split(":", 1)[1]
        by_id = {x["product_id"]: x for x in read_jsonl(out / f"{safe(model)}_responses.jsonl")}
        resp = [by_id[r["product_id"]] for r in rows
                if r["product_id"] in by_id and by_id[r["product_id"]]["prompt_hash"] == r["_hash"]]
        res = score(rows, resp)
        res.update({"data": str(args.data), "max_tokens": args.max_tokens,
                    "generated_at": datetime.now(timezone.utc).isoformat()})
        results[model] = res
        with open(out / f"{safe(model)}_eval.json", "w", encoding="utf-8") as f:
            json.dump({"all_null_baseline": baseline, model: res}, f, indent=2)
        print(f"{model}: n={res['answered']}/{res['n']} json_valid={res['json_valid']:.3f} "
              f"non_null={res['non_null_acc']:.3f} null={res['null_acc']:.3f} mean_field={res['mean_field_exact']:.3f} "
              f"cost=${res['cost_usd']:.4f}")
    return baseline, results


LABELS = {"gpt-4o-mini": "GPT-4o mini (API)", "gpt-4.1": "GPT-4.1 (API)",
          "claude-haiku-4-5-20251001": "Claude Haiku 4.5 (API)", "claude-sonnet-5-5": "Claude Sonnet 5.5 (API)"}


def comparison_entry(label, res):
    n = max(res.get("answered", res["n"]), 1)
    langs = res.get("by_language", {})
    return {"label": label, **{k: res[k] for k in ("json_valid", "non_null_acc", "null_acc", "non_null_count",
                                                   "null_count", "field_exact", "n")},
            "by_language": {k: {m: v[m] for m in ("non_null_acc", "null_acc", "json_valid", "n")}
                            for k, v in langs.items()},
            "cost_per_1k_usd": round(res["cost_usd"] / n * 1000, 4) if "cost_usd" in res else 0.0,
            "latency_ms": res.get("latency_ms")}


def write_comparison(path, rows, baseline, results):
    """Merge into path, keeping model entries written by others (e.g. the fine-tuned Qwen)."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"models": {}}
    base = dict(baseline, by_language={
        v: summarize([{f: None for f in FIELDS}] * len(rs), [r["_gold"] for r in rs])
        for v in sorted({r.get("language") for r in rows}) for rs in [[r for r in rows if r.get("language") == v]]})
    doc["models"]["all_null_baseline"] = comparison_entry("All-null baseline", base)
    for model, res in results.items():
        doc["models"][model] = comparison_entry(LABELS.get(model, model), res)
    doc["generated_at"] = datetime.now(timezone.utc).isoformat()
    doc["test"] = {"products": len(rows), "stores": len({r.get("domain") for r in rows}),
                   "note": doc.get("test", {}).get("note", "Fine-tuned Qwen results coming next.")}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--models", nargs="+", required=True, help="provider:model, e.g. openai:gpt-4o-mini")
    ap.add_argument("--out-dir", default=str(HERE / "runs" / "api_compare"))
    ap.add_argument("--max-usd", type=float, required=True, help="cap on total spend across --out-dir")
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--sample", type=int, default=0, help="stratified subset size (language x source)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--comparison", help="also merge results into this comparison.json")
    ap.add_argument("--report-only", action="store_true", help="re-score stored responses, no calls")
    args = ap.parse_args(argv)
    prices = json.loads(PRICES.read_text(encoding="utf-8"))["models"]
    rows = load_rows(args.data)
    if args.sample:
        rows = stratified(rows, args.sample)
    if not args.report_only:
        run(args, rows, prices)
    if not args.dry_run:
        baseline, results = report(args, rows)
        if args.comparison:
            write_comparison(args.comparison, rows, baseline, results)


if __name__ == "__main__":
    main()
