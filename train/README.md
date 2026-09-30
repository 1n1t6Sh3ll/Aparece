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
$PY train/build_examples.py --final dataset/output/final_v2_2k_fixed --max_chars 1800 --out train/data_fixed
```

`--final DIR` reads a ground-truth dir (`train.jsonl`, `val.jsonl`, `test_gold.jsonl`, each record with `raw` + `gold`; missing files are skipped) and keeps its splits. `--min_values N` keeps only train rows with N+ stated attributes (plus `--sparse_frac` of the rest). Product text is HTML-unescaped.

Writes `train/data/{train,val,test}.jsonl` with chat `messages`. Raw and normalized records are joined on `product_id`. Splits use a hash of `merchant_domain`, so no store appears in two splits (asserted). Prints record and domain counts.

## 2. Train

```sh
$PY train/train.py --max_steps 5 --grad_accum 1   # smoke test
$PY train/train.py --epochs 3                      # real run; --help lists lr, lora_r, max_len, batch
$PY train/train.py --model Qwen/Qwen2.5-0.5B-Instruct --data train/data_fixed --out train/runs/team20fixed --epochs 2 --batch 4 --grad_accum 4 --max_len 1024 --val_limit 200
```

Rows longer than `--max_len` tokens are dropped (not truncated). `--save_steps N` checkpoints and logs val loss every N steps.

Saves the LoRA adapter to `train/runs/qlora` and prints `train_time_s` and `peak_vram_gb`.

## 3. Evaluate

```sh
$PY train/eval.py                         # base zero-shot vs. base + adapter on train/data/test.jsonl
$PY train/eval.py --limit 50 --skip_base
$PY train/eval.py --model Qwen/Qwen2.5-0.5B-Instruct --adapter train/runs/team20fixed --data train/data_fixed/test.jsonl --out train/runs/team20fixed/eval.json
```

`--stratified N` samples N rows by language + source; `--ids FILE` restricts to listed product_ids; `--out` writes the JSON. Results are broken down overall, for the original 13 fields vs. the 7 fields added in final_v2, and by language, source and cross_tld_split. Generation is batched (`--batch`).

Prints, for an all-null baseline, the base model and the fine-tuned model (greedy decoding): JSON validity rate, per-field exact match, mean field exact match, accuracy on non-null gold fields and accuracy on null gold fields. A key missing from the output counts as a miss.
