# ProductLens

Evidence-driven view of how products are represented in search and AI answers. Vision: `docs/VISION.md`.

## Layout
- `dataset/` — shirt dataset schemas, examples, tests (spec: `docs/DATASET_SPEC.md`).
- `train/` — Qwen fine-tuning and evaluation pipeline (see `train/README.md`).
- `coordination/` — task board pointer (`BOARD.md`) and human decisions (`DECISIONS.md`).

## API
FastAPI service in `api/` (reuses `dataset/collect` extract + normalize). OpenAPI docs at `/docs`.
- `GET /v1/health`
- `POST /v1/extract` with one of `url`, `html`, `text` (+ optional `language`) -> `{product_id, language, raw, normalized, evidence, conflicts, quality_status}`.
URL fetches: http(s) only, public IPs only (each redirect re-checked), robots.txt, 10 s timeout, 3 MB cap. CORS allows `chrome-extension://` origins. `MODEL_BACKEND=rules` (default); `qwen` returns 501 until implemented.
Run: `docker compose up --build` (port 8000 on localhost) or `pip install -r api/requirements.txt && uvicorn main:app --app-dir api`. Tests: `python -m unittest discover -s api/tests`.

## Checks
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests`, compiles `train/`, and runs `api/tests`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
