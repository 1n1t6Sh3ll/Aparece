"""JSON validity + per-field exact match on the test split: base model vs. base + LoRA adapter."""
import argparse
import json
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from common import FIELDS


def parse(text):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def score(model, tok, rows, max_new):
    valid, hits = 0, {f: 0 for f in FIELDS}
    for r in rows:
        ids = tok.apply_chat_template(r["messages"][:-1], add_generation_prompt=True,
                                      return_tensors="pt", return_dict=True).to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new, do_sample=False)
        pred = parse(tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True))
        gold = json.loads(r["messages"][-1]["content"])
        if pred is not None:
            valid += 1
            for f in FIELDS:
                hits[f] += pred.get(f) == gold.get(f)
    n = max(len(rows), 1)
    return {"n": len(rows), "json_valid": valid / n, "field_exact": {f: h / n for f, h in hits.items()},
            "mean_field_exact": sum(hits.values()) / (n * len(FIELDS))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default="train/runs/qlora")
    ap.add_argument("--data", default="train/data/test.jsonl")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max_new", type=int, default=512)
    ap.add_argument("--skip_base", action="store_true")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
    rows = rows[:args.limit] if args.limit else rows
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.bfloat16))
    results = {}
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
