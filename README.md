# ProductLens

Evidence-driven view of how products are represented in search and AI answers. Vision: `docs/VISION.md`.

## Layout
- `dataset/` — shirt dataset schemas, examples, tests (spec: `docs/DATASET_SPEC.md`).
- `train/` — Qwen fine-tuning and evaluation pipeline (see `train/README.md`).
- `coordination/` — task board pointer (`BOARD.md`) and human decisions (`DECISIONS.md`).

## Gap analyzer
`analysis/` compares one normalized product with up to k comparable products (same type and language; price within ±30% when both prices share a known currency; same audience when known) and reports metrics plus issues typed OBSERVED_FACT / SUPPORTED_HYPOTHESIS / UNKNOWN. No LLM, no composite score, no ranking claims.
```
python -m analysis.gaps --data records.jsonl --product-id p_123 [--k 10]
python -m unittest discover -s analysis/tests -t .
```

## Checks
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests` and compiles `train/`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
