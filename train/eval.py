"""JSON validity + per-field exact match on the test split: base model vs. base + LoRA adapter."""
import argparse
import json
import random
import sys
import time
from collections import defaultdict

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from common import FIELDS

NEW_FIELDS = ["materials.fabric_type", "materials.texture", "fit_and_style.collar_type",
              "fit_and_style.shirt_length", "fit_and_style.style", "variants.sizes", "care"]


def parse(text):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def summarize(preds, golds, fields=FIELDS):
    """preds: list of dict or None (invalid JSON). A key missing from pred is a miss."""
    n = max(len(golds), 1)
    hits = {f: 0 for f in fields}
    tot = {"non_null": [0, 0], "null": [0, 0]}  # [hits, count]
    for pred, gold in zip(preds, golds):
        for f in fields:
            ok = pred is not None and f in pred and pred[f] == gold.get(f)
            hits[f] += ok
            t = tot["null" if gold.get(f) is None else "non_null"]
            t[0] += ok
            t[1] += 1
    return {"n": len(golds), "json_valid": sum(p is not None for p in preds) / n,
            "field_exact": {f: h / n for f, h in hits.items()},
            "mean_field_exact": sum(hits.values()) / (n * len(fields)),
            "non_null_acc": tot["non_null"][0] / max(tot["non_null"][1], 1), "non_null_count": tot["non_null"][1],
            "null_acc": tot["null"][0] / max(tot["null"][1], 1), "null_count": tot["null"][1]}


def generate(model, tok, rows, max_new, batch):
    """Greedy decoding, left-padded batches. Returns one parsed dict (or None) per row."""
    tok.padding_side = "left"
    preds = []
    for i in range(0, len(rows), batch):
        texts = [tok.apply_chat_template(r["messages"][:-1], add_generation_prompt=True, tokenize=False)
                 for r in rows[i:i + batch]]
        enc = tok(texts, return_tensors="pt", padding=True).to(model.device)
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=max_new, do_sample=False, pad_token_id=tok.pad_token_id)
        preds += [parse(t) for t in tok.batch_decode(out[:, enc["input_ids"].shape[1]:], skip_special_tokens=True)]
    return preds


def stratified(rows, n, seed=0):
    """~n rows, proportional per (language, source) stratum, at least min(5, size) per stratum."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r.get("language"), r.get("source"))].append(r)
    rng = random.Random(seed)
    take = {k: max(min(5, len(g)), round(n * len(g) / len(rows))) for k, g in groups.items()}
    while sum(take.values()) > n:  # trim rounding overflow from the largest stratum
        take[max(take, key=take.get)] -= 1
    out = []
    for k, g in sorted(groups.items(), key=lambda kv: str(kv[0])):
        out += rng.sample(g, take[k])
    return out


def breakdown(preds, golds, rows):
    """Overall plus per language, per source, and cross_tld_split."""
    res = {"overall": summarize(preds, golds),
           # the 7 fields upstream labels left empty before final_v2; reported apart so they don't skew overall
           "overall_original_fields": summarize(preds, golds, [f for f in FIELDS if f not in NEW_FIELDS]),
           "overall_new_fields": summarize(preds, golds, NEW_FIELDS)}
    for key in ("language", "source", "cross_tld_split"):
        vals = sorted({str(r.get(key)) for r in rows})
        res[f"by_{key}"] = {v: summarize(*zip(*[(p, g) for p, g, r in zip(preds, golds, rows)
                                                if str(r.get(key)) == v])) for v in vals}
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--adapter", default="train/runs/qlora")
    ap.add_argument("--data", default="train/data/test.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="first N rows (0: all)")
    ap.add_argument("--ids", help="file of product_ids to evaluate on")
    ap.add_argument("--stratified", type=int, default=0, help="stratified N-row sample by language + source")
    ap.add_argument("--max_new", type=int, default=512)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--skip_base", action="store_true")
    ap.add_argument("--out", help="also write the results JSON here")
    args = ap.parse_args()

    rows = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
    if args.ids:  # reuse a saved subset (one product_id per line)
        keep = set(open(args.ids, encoding="utf-8").read().split())
        rows = [r for r in rows if r["product_id"] in keep]
    rows = stratified(rows, args.stratified) if args.stratified else rows[:args.limit] if args.limit else rows
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                               bnb_4bit_compute_dtype=torch.bfloat16))
    golds = [json.loads(r["messages"][-1]["content"]) for r in rows]
    results = {"data": args.data, "n": len(rows), "adapter": args.adapter, "max_new": args.max_new,
               "all_null_baseline": breakdown([{f: None for f in FIELDS} for _ in golds], golds, rows)}
    runs = ([] if args.skip_base else [("base_zero_shot", False)]) + [("finetuned", True)]
    for name, adapter in runs:
        if adapter:
            model.load_adapter(args.adapter)
        t0 = time.time()
        results[name] = breakdown(generate(model, tok, rows, args.max_new, args.batch), golds, rows)
        results[name]["time_s"] = round(time.time() - t0, 1)
    text = json.dumps(results, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
