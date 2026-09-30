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
Read-only routes: `GET /v1/products?q=`, `/v1/products/{id}`, `/v1/products/{id}/gaps`, `/v1/stats`, `/v1/eval`. Data from `PRODUCTLENS_DATA` (normalized JSONL, default `dataset/output/final/train.jsonl`) and `PRODUCTLENS_EVAL` (`train/eval.py` JSON, default `train/runs/eval.json`); missing files give empty results.
Try with fixtures: `cd api && PRODUCTLENS_DATA=tests/fixtures/dashboard_records.jsonl PRODUCTLENS_EVAL=tests/fixtures/dashboard_eval.json uvicorn main:app`, then open `http://127.0.0.1:8000/dashboard/`.

## Chrome extension
`extension/` is a no-build MV3 popup that audits the current product page via `POST /v1/extract`. See `extension/README.md` to load it unpacked or preview it with mock data.

## Checks
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests`, compiles `train/`, and runs `api/tests`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
