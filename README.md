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

## Merchant dashboard
`dashboard/` is plain HTML/CSS/JS served by the API at `/dashboard/`: product search with facts + evidence, completeness and price vs peers, gap issues by label (reuses `analysis/`); dataset counts; model eval tables. No composite score.
Pages: Product (plus price & reviews from signals, recommendations labelled Observed fact / Supported hypothesis / Unknown), Competitors, AI visibility, Languages, Dataset, Models. Assumed values (e.g. assumed currency) are labelled; no causal ranking claims.
Read-only routes: `GET /v1/products?q=`, `/v1/products/{id}`, `/v1/products/{id}/gaps`, `/v1/products/{id}/signals`, `/v1/products/{id}/competitors`, `/v1/stats`, `/v1/languages`, `/v1/visibility`, `/v1/eval`. Data from env: `PRODUCTLENS_DATA` (normalized `*_clean.jsonl` or ground-truth rows, default `dataset/output/final/train.jsonl`), `PRODUCTLENS_SIGNALS` (`signals/build.py` output, default `dataset/output/signals/signals.jsonl`), `PRODUCTLENS_VISIBILITY` (benchmark `report.json`, default `benchmark/reports/report.json`), `PRODUCTLENS_EVAL` (`train/eval.py` JSON, default `train/runs/eval.json`). Missing files give empty states, not errors.
Try with fixtures: `cd api && PRODUCTLENS_DATA=tests/fixtures/dashboard_records.jsonl PRODUCTLENS_EVAL=tests/fixtures/dashboard_eval.json PRODUCTLENS_SIGNALS=tests/fixtures/dashboard_signals.jsonl PRODUCTLENS_VISIBILITY=tests/fixtures/dashboard_visibility.json uvicorn main:app`, then open `http://127.0.0.1:8000/dashboard/`. The extension popup links an audited product to `/dashboard/?product=<id>`.

## Chrome extension
`extension/` is a no-build MV3 popup that audits the current product page via `POST /v1/extract`. See `extension/README.md` to load it unpacked or preview it with mock data.

## AI-visibility benchmark
`benchmark/` sends the same prompts + system instructions to `mock`, `anthropic`, `openai`, `gemini` (official SDKs; keys only from `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY`) and `qwen` (a local OpenAI-compatible server such as Ollama/vLLM at `QWEN_BASE_URL`, default `http://localhost:11434/v1`; free, no key), stores raw responses in resumable JSONL, then matches mentions to catalog products (URL, alias, brand+name; country-TLD sites distinct) and reports mention rate, top-k, MRR, citation rate, stability per model/language/site. Hidden split is excluded unless `--splits` names it. Always `--dry-run` first; paid runs need `--max-usd` and a price in `benchmark/prices.json` (reviewer-verified; re-check sources).
```
python -m benchmark.harness run --prompts benchmark/examples/prompts.example.jsonl --models mock:mock-1 --catalog benchmark/examples/catalog.example.jsonl --out runs.jsonl [--repeats 3 --shuffle --dry-run --max-usd 5]
python -m benchmark.harness report --results runs.jsonl --catalog benchmark/examples/catalog.example.jsonl --out-dir reports/
python -m unittest discover -s benchmark/tests -t .
```

## Review and price signals (`signals/`)
Deterministic per-product signals keyed by `product_id`, written to `dataset/output/signals/` (git-ignored).
```sh
python signals/reviews.py --products <amazon>/shirts_raw.jsonl   # streams ~28 GB Amazon Reviews 2023 (research-only)
python signals/build.py --amazon-dir <amazon output dir> --wdc-dir <wdc output dir>
python -m unittest discover -s signals/tests -t .
```
- Reviews: Amazon rating mean/count/histogram + up to 3 verbatim excerpts (<=280 chars, most helpful) per `parent_asin`; WDC `aggregateRating`/`review` from schema.org.
- Prices: discount % from explicit list price; `suspicious_discount` if >=50% off or list > peer p90 while price <= peer p75. Peer percentile/p25-p75 guidance within `product_type|language|currency|observed-or-assumed currency` (n>=5); guidance is evidence, not a promise.
- USD 2026: ECB reference rates (2024-10-01) then US CPI-U (BLS CUUR0000SA0) to 2026-08; null when currency, date, or rate is unknown. Amazon (amazon.com) prices are assumed USD, period 2023. Tables and sources: `signals/reference.py`.
- Flags: `missing_currency`, `nonpositive_price`, `price_outlier` (log price beyond 3 IQR of peers, n>=10), `rating_out_of_range`, `rating_conflict`, `sale_above_list`, `conflicting_prices`, `suspicious_discount`.
- TODO: price over time from Common Crawl snapshots.

## Checks
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests`, compiles `train/`, and runs `api/tests`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
