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

## Reward (`reward.py`)

Deterministic, CPU-only score of one model output against its input text (`common.prompt_text`), with optional gold. No model or network calls.

| Part | Rule |
|---|---|
| format | +1 if the output is one JSON object and every value passes the field's schema in `dataset/schema/normalized_record.schema.json` (enums, types, percent ranges); otherwise −10 and scoring stops |
| grounding | each non-null value must be supported by the input: re-derived with the `dataset/collect/normalize.py` rules (lookup tables, `parse_composition`, `parse_weight`, colour table), or matched verbatim/by alias (free text, sizes, care, features). Unsupported = hallucination, −2 per field |
| correctness (gold given) | +1 per exact match on a non-null gold field; −0.5 for filling a field gold has as null only when the value is also unsupported. A supported value that gold lacks is neutral, since gold may be incomplete |

`"unknown"` and empty lists/objects count as null; missing keys count as null and are listed in `errors`. `reward()` returns `total`, a per-field breakdown (`value`, `grounding`, `unsupported`, `correctness`) and the `hallucinated` field list.

```sh
python train/reward.py PRED.jsonl train/data/test.jsonl --rows rewards.jsonl
python -m unittest discover -s train/tests -v
```

`PRED.jsonl` rows need `product_id` plus the output as `text` (the `api_eval.py` `*_responses.jsonl` format), `output` or `prediction`. `eval.py` does not save predictions yet, so write them in one of those forms first. Data rows are `build_examples.py` output (input = user message, gold = assistant message) or rows with `raw`. A data row with no prediction counts as a format failure. The summary gives mean reward, format rate, and hallucination rate and counts per field.

Known limits: grounding is lexical, so a value can be supported by an unrelated mention (for example `"other"` or a size letter that appears elsewhere in the text), and paraphrased care or feature lines count as unsupported. Colour and size lists are compared with order, the same way `eval.py` compares them.

### Use in best-of-N and DPO (not implemented)

- **Best-of-N / rejection sampling:** sample N outputs per training input, score each with `reward(text, input_text, gold)`, keep the highest (ties: the first sample, so the choice is reproducible). Drop the input if the best output is not `format_ok` or has hallucinations. The kept outputs can be used as extra SFT data or as the output at inference time.
- **DPO pairs:** from the same N samples, pair chosen = highest reward and rejected = lowest, and keep the pair only when the gap is large (for example ≥ 2, one hallucination) and the chosen output has no hallucinations. Without gold, grounding still ranks outputs, which makes pairs for unlabeled pages possible, but the only reward for filling a field is avoiding a penalty, so check for a drift toward all-null outputs. Keep the domain split from `build_examples.py` so no test store is used.
