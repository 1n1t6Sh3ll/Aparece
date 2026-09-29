# Shirt dataset

Schemas and examples for the PowerLens shirt product dataset. The spec and all decisions are in [`docs/DATASET_SPEC.md`](../docs/DATASET_SPEC.md).

- `schema/raw_record.schema.json`: source text exactly as found on a product page.
- `schema/normalized_record.schema.json`: normalized attributes, each backed by evidence.
- `examples/`: one real raw record and its normalized record (Thinking MU, White hemp Jules shirt).
- `tests/test_schema.py`: validates the examples and rejects invalid records.
- Fine-tuning on this data: see [`train/README.md`](../train/README.md).

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

## Web Data Commons source (`collect/wdc.py`)

Builds the same outputs from the [WDC schema.org Product subset, 2024-12 release](https://data.dws.informatik.uni-mannheim.de/structureddata/2024-12/quads/classspecific/Product/) (Common Crawl, October 2024). No product pages are fetched.

```sh
python dataset/collect/wdc.py --workers 8 --per-domain 50 --files part_1156.gz part_1274.gz part_1391.gz   # parts in parallel
python dataset/collect/wdc.py --files part_1156.gz --local-dir /path/to/downloads   # use already-downloaded parts
python dataset/collect/wdc.py --renormalize   # re-apply filter + normalize to shirts_raw.jsonl, then report/clean; no download
```

- Part files are processed in parallel (`--workers`); those missing from `--local-dir` are streamed and filtered in memory (not saved). Only pages with a T-shirt word in a name/category quad are parsed. `Product_lookup.csv` on the WDC site maps domains to part files.
- N-Quads are grouped by page (the 4th element). Each top-level `Product` entity whose name/category names a T-shirt (`t-shirt`, `camiseta`, `playera`, `remera`; a bare `tee` only in the name, with an apparel word in the name/description/URL/size/colour text and no tea, German-name or pipe-fitting word; sweatshirts, lunch boxes, candles, mugs, golf tees, SVG/transfer designs, sets and packs excluded) becomes one raw record. `--types shirts` accepts any shirt type.
- Raw record: the product's schema.org tree as found (`raw_product_schema`, `raw_offer_schema`; `hasVariant` -> `raw_variants`), name, description (`raw_full_description` and one `overview` section), brand, price/currency/availability, colour/size/material text, SKU/GTIN/MPN, images. HTML-only fields (`raw_title`, `raw_h1`, meta tags, breadcrumbs, care text) are `null`. `scraped_at` is the crawl month (`2024-10-01T00:00:00Z`) because WDC does not publish per-page fetch times; `merchant_name` is the domain.
- Normalized record: the existing `normalize.py` rules. `source.language` is a stop-word guess (`en`/`es`/`other`; Portuguese counts as `other`). HTML entities and literal `\uXXXX` escapes are decoded in the normalized name, brand and description only. A price of 0 is `reject`. Every record has the flags `wdc_schema_org_only` and `source_wdc_2024_12` (the schemas have no source-dataset field).
- At most `--per-domain` records per domain. `clean` also dedupes by GTIN and product SKU and lists each dropped duplicate with the record it duplicates in `dataset_stats.json` (`duplicates`).

## Amazon Reviews 2023 source (`collect/amazon_source.py`)

Second offline source for training volume: item metadata from Amazon Reviews 2023 (McAuley Lab, https://amazon-reviews-2023.github.io/, HF `McAuley-Lab/Amazon-Reviews-2023`, `raw_meta_Clothing_Shoes_and_Jewelry`). The license is not declared, so this is for hackathon/research use only: every output line carries `provenance: {source: "amazon-reviews-2023", license: "undeclared-research-only"}` so it can be excluded later. `provenance` sits outside the schemas; validation runs on the record without it.

```sh
python dataset/collect/amazon_source.py --target 5000 --per-brand 50
```

Streams the ~18 GB file over HTTP (never stored), keeps T-shirts (title match, tops/shirts categories, other garments excluded), caps records per store, and stops at `--target` non-reject records. Raw values are copied as-is: title, features -> bullet points, description, details -> specifications (plus fabric/care sections), price, store -> brand, categories -> breadcrumbs, images, parent_asin -> sku; fields Amazon lacks are null. The full original line is kept in `shirts_raw.jsonl` under `provenance.original`. Normalization reuses `normalize.py`; `parent_asin` is the variant group, and clean dedupes by parent_asin and brand+name. The metadata has no currency or sizes, so records are at most `medium`. `scraped_at` is the run time, not the 2023 crawl date. Outputs in `dataset/output/amazon/`: `shirts_raw.jsonl`, `shirts_normalized.jsonl`, `shirts_clean.jsonl`, `dataset_stats.json`.
