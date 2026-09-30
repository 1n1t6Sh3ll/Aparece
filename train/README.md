# Attribute-extraction fine-tune (QLoRA)

Fine-tunes `Qwen/Qwen2.5-1.5B-Instruct` (Apache-2.0, per its Hugging Face model card) to turn raw shirt page text into one JSON object of normalized attributes. Target fields are listed in `common.py` (`FIELDS`). A field keeps its value only when the normalized record has an `evidence` entry for it; otherwise it is `null`.

Stack: HF Transformers + TRL `SFTTrainer` + PEFT LoRA + bitsandbytes 4-bit NF4. Loss is on the assistant JSON only.

## Setup (Windows, NVIDIA GPU)

There are no CUDA torch wheels for Python 3.14 here, so use a separate Python 3.12 venv (git-ignored). Run everything from the repo root.

```sh
uv venv train/.venv --python 3.12
uv pip install -p train/.venv/Scripts/python.exe torch --index-url https://download.pytorch.org/whl/cu128
uv pip install -p train/.venv/Scripts/python.exe -r train/requirements.txt
PY=train/.venv/Scripts/python.exe
```

## 1. Build examples

```sh
$PY train/build_examples.py             # dataset/output/shirts_clean.jsonl (else shirts_normalized.jsonl) + shirts_raw.jsonl
$PY train/build_examples.py --raw dataset/output/<raw>.jsonl --val 0.1 --test 0.1
$PY train/build_examples.py --examples  # smoke test: the one dataset/examples pair, copied into every split
```

Writes `train/data/{train,val,test}.jsonl` with chat `messages`. Raw and normalized records are joined on `product_id`. Splits use a hash of `merchant_domain`, so no store appears in two splits (asserted). Prints record and domain counts.

## 2. Train

```sh
$PY train/train.py --max_steps 5 --grad_accum 1   # smoke test
$PY train/train.py --epochs 3                      # real run; --help lists lr, lora_r, max_len, batch
```

Saves the LoRA adapter to `train/runs/qlora` and prints `train_time_s` and `peak_vram_gb`.

## 3. Evaluate

```sh
$PY train/eval.py                         # base zero-shot vs. base + adapter on train/data/test.jsonl
$PY train/eval.py --limit 50 --skip_base
```

Prints, for an all-null baseline, the base model and the fine-tuned model (greedy decoding): JSON validity rate, per-field exact match, mean field exact match, accuracy on non-null gold fields and accuracy on null gold fields. A key missing from the output counts as a miss.

## 4. Compare with API models

```sh
DATA=dataset/output/final_v2_2k_fixed/test_gold.jsonl
M="openai:gpt-4.1 anthropic:claude-sonnet-5-5 openai:gpt-4o-mini anthropic:claude-haiku-4-5-20251001"
$PY train/api_eval.py --data $DATA --models $M --max-usd 5 --dry-run          # calls + upper-bound cost, no spend
$PY train/api_eval.py --data $DATA --models $M --max-usd 5 --comparison train/runs/comparison.json
$PY train/api_eval.py --data $DATA --models $M --report-only --comparison train/runs/comparison.json  # re-score, read-only; safe mid-run
```

Sends each record's stored system + user prompt (what `eval.py` gives Qwen; rebuilt with `common.messages` only if absent) at temperature 0, except `claude-sonnet-5-5`, which rejects `temperature`; it runs with thinking off (`between_tools`). Scores with `eval.py`'s `parse`/`summarize`, plus `by_language` and `by_source`. Needs `anthropic` and `openai`; keys come from `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` only.

Raw responses (model version, timestamp, usage, latency, cost) go to `train/runs/api_compare/{model}_responses.jsonl`; results to `{model}_eval.json` in `eval.py`'s schema.  Metrics cover only rows with a stored response (`answered`/`total`, `partial: true` mid-run); models with none are left out of `comparison.json`. Reruns resume and only re-call rows whose prompt changed. Cost is actual usage × `benchmark/prices.json`; a call is skipped when its upper-bound estimate would push the total across `--out-dir` over `--max-usd`. `--sample N` takes a stratified (language × source) subset.
