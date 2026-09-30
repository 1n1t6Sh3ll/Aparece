# ProductLens

Evidence-driven view of how products are represented in search and AI answers. Vision: `docs/VISION.md`.

## Layout
- `dataset/` — shirt dataset schemas, examples, tests (spec: `docs/DATASET_SPEC.md`).
- `train/` — Qwen fine-tuning and evaluation pipeline (see `train/README.md`).
- `coordination/` — task board pointer (`BOARD.md`) and human decisions (`DECISIONS.md`).

## Chrome extension
`extension/` is a no-build MV3 popup that audits the current product page via `POST /v1/extract`. See `extension/README.md` to load it unpacked or preview it with mock data.

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
CI (`ci / check`) runs `python -m unittest discover -s dataset/tests` and compiles `train/`.

## Merging
PR only. `main` requires the `check` status and 1 approval (repo admins can bypass the approval on PR merge). Every merge also needs independent review, updated docs, and explicit human approval of the exact revision.
