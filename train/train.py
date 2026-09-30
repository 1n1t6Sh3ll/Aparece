"""QLoRA fine-tune of a small Qwen on train/data/*.jsonl (HF TRL + PEFT + bitsandbytes)."""
import argparse
import time

import torch
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer


def to_prompt_completion(row):
    # Loss only on the assistant JSON (TRL's completion-only loss).
    return {"prompt": row["messages"][:-1], "completion": row["messages"][-1:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--data", default="train/data")
    ap.add_argument("--out", default="train/runs/qlora")
    ap.add_argument("--max_steps", type=int, default=-1)
    ap.add_argument("--epochs", type=float, default=3)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad_accum", type=int, default=8)
    ap.add_argument("--max_len", type=int, default=2048)
    ap.add_argument("--lora_r", type=int, default=16)
    ap.add_argument("--save_steps", type=int, default=0, help="checkpoint + val loss every N steps (0: end only)")
    ap.add_argument("--val_limit", type=int, default=0, help="use only the first N val rows (0: all)")
    args = ap.parse_args()

    ds = load_dataset("json", data_files={s: f"{args.data}/{s}.jsonl" for s in ("train", "val")})
    ds = ds.map(to_prompt_completion, remove_columns=ds["train"].column_names)
    if args.val_limit:
        ds["val"] = ds["val"].shuffle(seed=0).select(range(min(args.val_limit, len(ds["val"]))))

    tok = AutoTokenizer.from_pretrained(args.model)
    # Drop rows longer than max_len instead of letting truncation cut the target JSON.
    def fits(r):
        text = tok.apply_chat_template(r["prompt"] + r["completion"], tokenize=False)
        return len(tok(text)["input_ids"]) <= args.max_len
    for s in ("train", "val"):
        n = len(ds[s])
        ds[s] = ds[s].filter(fits)
        print(f"{s}: kept {len(ds[s])}/{n} rows <= {args.max_len} tokens")
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map={"": 0},
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16, bnb_4bit_use_double_quant=True))

    cfg = SFTConfig(
        output_dir=args.out, max_steps=args.max_steps, num_train_epochs=args.epochs,
        learning_rate=args.lr, per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum, max_length=args.max_len,
        gradient_checkpointing=True, bf16=True, logging_steps=10,
        eval_strategy="steps" if args.save_steps else "epoch", eval_steps=args.save_steps or None,
        save_strategy="steps" if args.save_steps else "no", save_steps=args.save_steps or 500,
        per_device_eval_batch_size=4, report_to="none", lr_scheduler_type="cosine")
    peft_cfg = LoraConfig(r=args.lora_r, lora_alpha=2 * args.lora_r, lora_dropout=0.05,
                          target_modules="all-linear", task_type="CAUSAL_LM")
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=ds["train"], eval_dataset=ds["val"],
                         processing_class=tok, peft_config=peft_cfg)

    torch.cuda.reset_peak_memory_stats()
    t0 = time.time()
    trainer.train()
    print(f"train_time_s={time.time() - t0:.1f} peak_vram_gb={torch.cuda.max_memory_allocated() / 1e9:.2f}")
    print("final_eval", trainer.evaluate())
    trainer.save_model(args.out)  # LoRA adapter only
    tok.save_pretrained(args.out)


if __name__ == "__main__":
    main()
