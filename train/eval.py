"""JSON validity + per-field exact match on the test split: base model vs. base + LoRA adapter."""
import argparse
import json
import sys
import time

from common import FIELDS


def parse(text):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def summarize(preds, golds):
    """preds: list of dict or None (invalid JSON). A key missing from pred is a miss."""
    n = max(len(golds), 1)
    hits = {f: 0 for f in FIELDS}
    tot = {"non_null": [0, 0], "null": [0, 0]}  # [hits, count]
    for pred, gold in zip(preds, golds):
        for f in FIELDS:
            ok = pred is not None and f in pred and pred[f] == gold.get(f)
            hits[f] += ok
            t = tot["null" if gold.get(f) is None else "non_null"]
            t[0] += ok
            t[1] += 1
    return {"n": len(golds), "json_valid": sum(p is not None for p in preds) / n,
            "field_exact": {f: h / n for f, h in hits.items()},
            "mean_field_exact": sum(hits.values()) / (n * len(FIELDS)),
            "non_null_acc": tot["non_null"][0] / max(tot["non_null"][1], 1), "non_null_count": tot["non_null"][1],
            "null_acc": tot["null"][0] / max(tot["null"][1], 1), "null_count": tot["null"][1]}


def score(model, tok, rows, max_new):
    import torch  # lazy: parse/summarize stay importable without torch (api_eval.py, CI)

    preds = []
    for r in rows:
        ids = tok.apply_chat_template(r["messages"][:-1], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True).to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
        preds.append(parse(tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)))
    return summarize(preds, [json.loads(r["messages"][-1]["content"]) for r in rows])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default="train/runs/qlora")
    ap.add_argument("--data", default="train/data/test.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max_new", type=int, default=512)
    ap.add_argument("--skip_base", action="store_true")
    args = ap.parse_args()
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
    rows = rows[:args.limit] if args.limit else rows
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.bfloat16))
    golds = [json.loads(r["messages"][-1]["content"]) for r in rows]
    results = {"all_null_baseline": summarize([{f: None for f in FIELDS} for _ in golds], golds)}
    if not args.skip_base:
        t0 = time.time()
        results["base_zero_shot"] = score(model, tok, rows, args.max_new)
        results["base_zero_shot"]["time_s"] = round(time.time() - t0, 1)
    model.load_adapter(args.adapter)
    t0 = time.time()
    results["finetuned"] = score(model, tok, rows, args.max_new)
    results["finetuned"]["time_s"] = round(time.time() - t0, 1)
    json.dump(results, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
