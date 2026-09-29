# Shirt dataset

Schemas and examples for the PowerLens shirt product dataset. The spec and all decisions are in [`docs/DATASET_SPEC.md`](../docs/DATASET_SPEC.md).

- `schema/raw_record.schema.json`: source text exactly as found on a product page.
- `schema/normalized_record.schema.json`: normalized attributes, each backed by evidence.
- `examples/`: one real raw record and its normalized record (Thinking MU, White hemp Jules shirt).
- `tests/test_schema.py`: validates the examples and rejects invalid records.

## Run the checks

Requires Python 3.9+.

```sh
python -m pip install -r dataset/requirements.txt
python -m unittest discover -s dataset/tests -v
```

Run from the repo root. Generated data goes in `dataset/output/` and page caches in `dataset/.cache/`; both are git-ignored.

## Collector (`collect/`)

Collects shirt (default: T-shirt) records from Shopify stores listed with `use=yes` in [`collect/stores.csv`](collect/stores.csv). Each row records the store's Terms of Service URL and the result of checking it for scraping/crawling/robots clauses; stores whose terms forbid crawling are kept with `use=no`.

```sh
python dataset/collect/run.py collect --max-products 20 --per-store 4          # T-shirts (default --types tees)
python dataset/collect/run.py collect --stores huitzilli.myshopify.com --types shirts --max-products 20
python dataset/collect/run.py collect --max-products 1000 --per-store 400 --workers 4   # parallel across stores; resumes
python dataset/collect/run.py report    # validation CSV + stats only
python dataset/collect/run.py clean     # drop reject, dedupe, strip HTML -> shirts_clean.jsonl
```

- `fetch.py`: checks robots.txt (wildcard-aware), 1 request/second per host, User-Agent `ProductLens-research/0.1`, backs off on 429 or a bot-verification page and skips the URL after 3 tries (it never tries to get past a challenge). Responses are cached in `dataset/.cache/`.
- `extract.py`: `/products.json` (paged, 250 per page) + product page HTML -> raw record. Description text comes from the Shopify `body_html` plus product accordions on the page (`<details>`/accordion buttons with a recognised heading); JSON-LD is parsed with `json`; variants come from `products.json`, with GTIN/availability from matching JSON-LD offers.
- `normalize.py`: deterministic regex/lookup rules (English and Spanish) for materials %, GSM (oz conversion per the spec), fit, sleeve, neckline, collar, pattern, product type, audience, colours and sizes. Every value has an evidence item pointing at an exact substring of the raw record; disagreeing sources go to `conflicts` with the value left `null`.
- `run.py`: shirt filter on title + product_type (tags only as a fallback), dedupe by canonical URL and SKU, quality status (`high`/`medium`/`low`/`reject` + flags), schema and evidence validation. Rerunning `collect` skips products already in `shirts_raw.jsonl`; `--fresh` starts over.

Outputs in `dataset/output/` (git-ignored): `shirts_raw.jsonl`, `shirts_normalized.jsonl`, `shirts_clean.jsonl`, `shirts_validation_report.csv`, `dataset_stats.json`.

## Amazon Reviews 2023 source (`collect/amazon_source.py`)

Second offline source for training volume: item metadata from Amazon Reviews 2023 (McAuley Lab, https://amazon-reviews-2023.github.io/, HF `McAuley-Lab/Amazon-Reviews-2023`, `raw_meta_Clothing_Shoes_and_Jewelry`). The license is not declared, so this is for hackathon/research use only: every output line carries `provenance: {source: "amazon-reviews-2023", license: "undeclared-research-only"}` so it can be excluded later. `provenance` sits outside the schemas; validation runs on the record without it.

```sh
python dataset/collect/amazon_source.py --target 5000 --per-brand 50
```

Streams the ~18 GB file over HTTP (never stored), keeps T-shirts (title match, tops/shirts categories, other garments excluded), caps records per store, and stops at `--target` non-reject records. Raw values are copied as-is: title, features -> bullet points, description, details -> specifications (plus fabric/care sections), price, store -> brand, categories -> breadcrumbs, images, parent_asin -> sku; fields Amazon lacks are null. The full original line is kept in `shirts_raw.jsonl` under `provenance.original`. Normalization reuses `normalize.py`; `parent_asin` is the variant group, and clean dedupes by parent_asin and brand+name. The metadata has no currency or sizes, so records are at most `medium`. `scraped_at` is the run time, not the 2023 crawl date. Outputs in `dataset/output/amazon/`: `shirts_raw.jsonl`, `shirts_normalized.jsonl`, `shirts_clean.jsonl`, `dataset_stats.json`.
