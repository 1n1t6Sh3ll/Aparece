"""AI-visibility benchmark harness: prompts -> model calls -> JSONL -> report.

  python -m benchmark.harness run --prompts P --models mock:mock-1 --out runs.jsonl --catalog C
  python -m benchmark.harness report --results runs.jsonl --catalog C --out-dir reports/

Paid providers (anthropic, openai) read keys from ANTHROPIC_API_KEY / OPENAI_API_KEY only, require --max-usd, and should first be checked with --dry-run.
qwen calls a local OpenAI-compatible server at QWEN_BASE_URL (nothing is loaded here); it is
free by default, and --max-usd applies to it when prices.json has a price for its model.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .match import load_catalog
from .metrics import build_report, to_markdown

HERE = Path(__file__).parent
SPLITS = {"dev", "val", "hidden"}
REQUIRED = ("id", "text", "language", "market", "canonical_intent", "split")
DEFAULT_SYSTEM = ("You are a helpful shopping assistant. When recommending products, "
                  "name the brand and product, most recommended first.")
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
FREE = {"mock", "qwen"}  # qwen = local server, no spend


# ---------- prompts ----------
def load_prompts(path):
    path = Path(path)
    with open(path, encoding="utf-8", newline="") as f:
        if path.suffix == ".csv":
            rows = list(csv.DictReader(f))
            for r in rows:  # CSV candidates are pipe-separated
                r["candidates"] = [c.strip() for c in (r.get("candidates") or "").split("|") if c.strip()]
        else:
            rows = [json.loads(l) for l in f if l.strip()]
    seen = set()
    for r in rows:
        missing = [k for k in REQUIRED if not str(r.get(k) or "").strip()]
        if missing:
            raise ValueError(f"prompt {r.get('id')!r} missing {missing}")
        if r["split"] not in SPLITS:
            raise ValueError(f"prompt {r['id']!r} split must be one of {sorted(SPLITS)}")
        if r["id"] in seen:
            raise ValueError(f"duplicate prompt id {r['id']!r}")
        seen.add(r["id"])
        r["candidates"] = r.get("candidates") or []
    return rows


# ---------- adapters ----------
class MockAdapter:
    """Deterministic fake model: lists catalog products chosen by hash(prompt, seed)."""

    def __init__(self, model, products=()):
        self.model, self.products = model, list(products)

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        h = int(hashlib.sha256(f"{prompt}|{seed}".encode()).hexdigest(), 16)
        lines = ["Here are some options:"]
        if self.products:
            start = h % len(self.products)
            picks = [self.products[(start + i) % len(self.products)] for i in range(min(2, len(self.products)))]
            for i, p in enumerate(picks, 1):
                url = f" - {p['url']}" if (h >> i) & 1 else ""
                lines.append(f"{i}. {p['brand']} {p['name']}{url}")
        lines.append(f"{len(lines)}. Acme Basic Tee")
        text = "\n".join(lines)
        return {"text": text, "model_version": self.model, "input_tokens": len(prompt) // 4,
                "output_tokens": len(text) // 4, "raw": {"text": text}}


class AnthropicAdapter:
    def __init__(self, model):
        import anthropic  # official SDK; reads ANTHROPIC_API_KEY from env
        self.model, self.client = model, anthropic.Anthropic()

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        kw = {} if temperature is None else {"temperature": temperature}
        r = self.client.messages.create(model=self.model, system=system, max_tokens=max_tokens,
                                        messages=[{"role": "user", "content": prompt}], **kw)
        text = "".join(b.text for b in r.content if b.type == "text")
        return {"text": text, "model_version": r.model, "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens, "raw": r.model_dump(mode="json")}


class OpenAIAdapter:
    token_param = "max_completion_tokens"

    def __init__(self, model, **client_kw):
        import openai  # official SDK; reads OPENAI_API_KEY from env unless client_kw overrides
        self.model, self.client = model, openai.OpenAI(**client_kw)

    def complete(self, system, prompt, temperature, max_tokens, seed=0):
        kw = {} if temperature is None else {"temperature": temperature}
        kw[self.token_param] = max_tokens
        r = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}], **kw)
        return {"text": r.choices[0].message.content or "", "model_version": r.model,
                "input_tokens": r.usage.prompt_tokens, "output_tokens": r.usage.completion_tokens,
                "raw": r.model_dump(mode="json")}


class QwenAdapter(OpenAIAdapter):
    """Local Qwen via an already-running OpenAI-compatible server (Ollama, vLLM). Loads nothing itself."""
    token_param = "max_tokens"

    def __init__(self, model):
        super().__init__(model, base_url=os.environ.get("QWEN_BASE_URL", "http://localhost:11434/v1"),
                         api_key=os.environ.get("QWEN_API_KEY", "local"))


def make_adapter(provider, model, products=()):
    if provider == "mock":
        return MockAdapter(model, products)
    if provider == "anthropic":
        return AnthropicAdapter(model)
    if provider == "openai":
        return OpenAIAdapter(model)
    if provider == "qwen":
        return QwenAdapter(model)
    raise ValueError(f"unknown provider {provider!r}")


# ---------- planning, cost ----------
def plan_calls(prompts, models, repeats, shuffle):
    for p in prompts:
        variants = ["original"] + (["shuffled"] if shuffle and p["candidates"] else [])
        for rep in range(repeats):
            for variant in variants:
                cands = list(p["candidates"])
                if variant == "shuffled":
                    random.Random(f"{p['id']}|{rep}").shuffle(cands)
                text = p["text"].replace("{candidates}", "; ".join(cands)) if cands else p["text"]
                for provider, model in models:
                    yield {"key": f"{p['id']}|{provider}:{model}|{rep}|{variant}", "prompt": p,
                           "text": text, "provider": provider, "model": model, "repeat": rep,
                           "variant": variant, "candidates": cands}


def estimate_usd(price, system, text, max_tokens):
    """Upper-bound estimate: ~2 chars/token input (conservative), full max_tokens output."""
    return (math.ceil(len(system + text) / 2) * price["input"] + max_tokens * price["output"]) / 1e6


def actual_usd(price, out):
    return (out["input_tokens"] * price["input"] + out["output_tokens"] * price["output"]) / 1e6


def done_keys(path):
    if not Path(path).exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {json.loads(l)["call_key"] for l in f if l.strip()}


# ---------- run ----------
def run(args, sleep=time.sleep, log=print):
    prompts = [p for p in load_prompts(args.prompts) if p["split"] in args.splits]
    if "hidden" in args.splits:
        log("WARNING: hidden split included; never feed these results to the optimizer.")
    models = [tuple(m.split(":", 1)) for m in args.models]
    prices = json.loads(Path(args.prices).read_text(encoding="utf-8"))["models"]
    done = done_keys(args.out)
    calls = [c for c in plan_calls(prompts, models, args.repeats, args.shuffle) if c["key"] not in done]
    paid = {prov for prov, _ in models if prov not in FREE}
    missing = sorted({m for prov, m in models if prov not in FREE and m not in prices})
    if missing and paid:
        raise SystemExit(f"no price for {missing} in {args.prices}; refusing paid run")
    est = sum(estimate_usd(prices.get(c["model"], {"input": 0, "output": 0}), args.system,
                           c["text"], args.max_tokens) for c in calls)
    if args.dry_run:
        log(f"dry run: {len(calls)} calls ({len(done)} already done), estimated max ${est:.4f}")
        unverified = sorted({m for prov, m in models if prov not in FREE and not prices.get(m, {}).get("verified")})
        if unverified:
            log(f"prices UNVERIFIED for {unverified}; check sources in {args.prices}")
        return {"calls": len(calls), "est_usd": est}
    if paid and args.max_usd is None:
        raise SystemExit("paid providers require --max-usd")
    for prov in paid:
        if not os.environ.get(KEY_ENV[prov]):
            raise SystemExit(f"{KEY_ENV[prov]} not set")
    catalog = load_catalog(args.catalog) if args.catalog else []
    adapters = {f"{prov}:{mod}": make_adapter(prov, mod, catalog) for prov, mod in models}
    run_id = uuid.uuid4().hex[:12]
    settings = {"temperature": args.temperature, "max_tokens": args.max_tokens, "system": args.system}
    spent, made = 0.0, 0
    with open(args.out, "a", encoding="utf-8") as f:
        for c in calls:
            price = prices.get(c["model"], {"input": 0, "output": 0})
            if args.max_usd is not None and spent + estimate_usd(price, args.system, c["text"], args.max_tokens) > args.max_usd:
                log(f"spend cap ${args.max_usd} reached (spent ${spent:.4f}); stopping. Re-run to resume.")
                break
            adapter = adapters[f"{c['provider']}:{c['model']}"]
            for attempt in range(args.retries + 1):
                try:
                    out = adapter.complete(args.system, c["text"], args.temperature, args.max_tokens, seed=c["repeat"])
                    break
                except Exception as e:  # SDK errors vary; retry with backoff
                    if attempt == args.retries:
                        raise
                    log(f"retry {attempt + 1} for {c['key']}: {type(e).__name__}")
                    sleep(2 ** attempt)
            cost = actual_usd(price, out)
            spent += cost
            stop_after = args.max_usd is not None and spent >= args.max_usd
            p = c["prompt"]
            f.write(json.dumps({
                "run_id": run_id, "call_key": c["key"], "prompt_id": p["id"], "prompt_text": c["text"],
                "language": p["language"], "market": p["market"], "canonical_intent": p["canonical_intent"],
                "split": p["split"], "variant": c["variant"], "candidates": c["candidates"],
                "repeat": c["repeat"], "provider": c["provider"], "model": c["model"],
                "model_version": out["model_version"],
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "settings": settings, "response_text": out["text"], "raw_response": out["raw"],
                "usage": {"input_tokens": out["input_tokens"], "output_tokens": out["output_tokens"]},
                "cost_usd": round(cost, 6),
            }, ensure_ascii=False) + "\n")
            f.flush()
            made += 1
            if stop_after:
                log(f"spend cap ${args.max_usd} reached by actual usage (spent ${spent:.4f}); stopping.")
                break
            if args.min_interval and made < len(calls):
                sleep(args.min_interval)
    log(f"run {run_id}: {made} calls, ${spent:.4f} spent -> {args.out}")
    return {"calls": made, "spent": spent, "run_id": run_id}


def report(args, log=print):
    with open(args.results, encoding="utf-8") as f:
        records = [json.loads(l) for l in f if l.strip()]
    rep = build_report(records, load_catalog(args.catalog), k=args.k)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    log(f"wrote {out / 'report.json'} and {out / 'report.md'}")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="benchmark.harness")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--prompts", required=True)
    r.add_argument("--models", required=True, type=lambda s: [m.strip() for m in s.split(",") if m.strip()],
                   help="comma list of provider:model, e.g. mock:mock-1,openai:gpt-4o-mini,anthropic:claude-haiku-4-5,qwen:qwen2.5:7b")
    r.add_argument("--out", required=True, help="JSONL results (appended; resumable)")
    r.add_argument("--catalog", help="catalog JSONL (mock adapter uses it to fake answers)")
    r.add_argument("--prices", default=str(HERE / "prices.json"))
    r.add_argument("--splits", default={"dev", "val"}, type=lambda s: set(s.split(",")))
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--shuffle", action="store_true", help="add shuffled-candidate-order variant")
    r.add_argument("--system", default=DEFAULT_SYSTEM)
    r.add_argument("--temperature", type=float, default=0.7)
    r.add_argument("--max-tokens", type=int, default=600)
    r.add_argument("--max-usd", type=float)
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--min-interval", type=float, default=1.0, help="seconds between calls")
    r.add_argument("--retries", type=int, default=3)
    p = sub.add_parser("report")
    p.add_argument("--results", required=True)
    p.add_argument("--catalog", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--k", type=int, default=3)
    args = ap.parse_args(argv)
    return run(args) if args.cmd == "run" else report(args)


if __name__ == "__main__":
    main()
