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

## API
FastAPI service in `api/` (reuses `dataset/collect` extract + normalize). OpenAPI docs at `/docs`.
- `GET /v1/health`
- `POST /v1/extract` with one of `url`, `html`, `text` (+ optional `language`) -> `{product_id, language, raw, normalized, evidence, conflicts, quality_status}`.
URL fetches: http(s) only, public IPs only (each redirect re-checked), robots.txt, 10 s total deadline, 3 MB cap. CORS allows `chrome-extension://` origins. `MODEL_BACKEND=rules` (default); `qwen` returns 501 until implemented.
Run: `docker compose up --build` (port 8000 on localhost) or `pip install -r api/requirements.txt && uvicorn main:app --app-dir api`. Tests: `python -m unittest discover -s api/tests`.

## Chrome extension
`extension/` is a no-build MV3 popup that audits the current product page via `POST /v1/extract`. See `extension/README.md` to load it unpacked or preview it with mock data.

## AI-visibility benchmark
`benchmark/` sends the same prompts + system instructions to `mock`, `anthropic`, `openai` (official SDKs; keys only from `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`), stores raw responses in resumable JSONL, then matches mentions to catalog products (URL, alias, brand+name; country-TLD sites distinct) and reports mention rate, top-k, MRR, citation rate, stability per model/language/site. Hidden split is excluded unless `--splits` names it. Always `--dry-run` first; paid runs need `--max-usd` and a price in `benchmark/prices.json` (reviewer-verified; re-check sources).
```
python -m benchmark.harness run --prompts benchmark/examples/prompts.example.jsonl --models mock:mock-1 --catalog benchmark/examples/catalog.example.jsonl --out runs.jsonl [--repeats 3 --shuffle --dry-run --max-usd 5]
python -m benchmark.harness report --results runs.jsonl --catalog benchmark/examples/catalog.example.jsonl --out-dir reports/
python -m unittest discover -s benchmark/tests -t .
```

## Checks
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests`, compiles `train/`, and runs `api/tests`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
