# Shirt dataset spec (TEAM-11)

Decision record for the Aparece shirt dataset. Part A is the human's spec, kept verbatim (received 2026-09-29, including the human addendum). Part B records the decisions made while turning it into schemas. Items marked **pending human** are proposals, not approved decisions.

Human note (2026-09-29): scraped product descriptions must be the real, complete source text; they are the ground truth for later training and evaluation.

Schemas: [`dataset/schema/`](../dataset/schema/). Examples: [`dataset/examples/`](../dataset/examples/). How to validate: [`dataset/README.md`](../dataset/README.md).

## Part A: human spec (verbatim)

```text
You are building the training dataset for an AI model that will deeply understand shirt product listings.

Your only job right now is DATA COLLECTION + CLEAN STRUCTURING.

Do not build SEO recommendations.
Do not build GEO rankings.
Do not generate keywords.
Do not rewrite descriptions.
Do not train the model yet.

The immediate objective is:

COLLECT AT LEAST 1,000 HIGH-QUALITY SHIRT PRODUCT RECORDS FROM PUBLICLY ACCESSIBLE PRODUCT PAGES AND TURN THEM INTO A CLEAN TRAINING DATASET.

The future model will use this dataset to understand:

- what a shirt is
- shirt types
- materials
- fit
- styles
- colors
- sizes
- fabric properties
- product features
- pricing
- product descriptions
- marketing language
- product specifications
- product variants
- structured product data

The dataset must preserve the ORIGINAL PRODUCT DESCRIPTION exactly as found on the source page.

==================================================
1. MAIN DATA PRINCIPLE
==================================================

For every product store TWO layers:

1. RAW SOURCE DATA
2. NORMALIZED STRUCTURED DATA

Never destroy or overwrite the original source information.

Never guess missing values.

If a value is unavailable:

null

Do not infer unsupported facts.

Example:

If description says:

"Soft heavyweight tee with a relaxed silhouette."

Do NOT automatically label:

material = cotton

unless another source on the product page actually says cotton.

==================================================
2. PRODUCT SCOPE
==================================================

Only collect shirt-related products for this first dataset.

Examples allowed:

- T-shirts
- heavyweight T-shirts
- basic tees
- graphic T-shirts
- oversized T-shirts
- slim-fit T-shirts
- polos
- button-down shirts
- dress shirts
- casual shirts
- Oxford shirts
- flannel shirts
- athletic shirts
- performance shirts
- long-sleeve shirts
- short-sleeve shirts
- henleys
- overshirts
- work shirts

Avoid unrelated products such as:

- pants
- shoes
- jackets unless explicitly categorized as a shirt/overshirt
- dresses
- hats
- accessories

The initial dataset should contain diversity across:

- price ranges
- shirt types
- materials
- brands
- merchants
- fits
- colors
- styles
- target audiences

==================================================
3. REQUIRED RAW DATA
==================================================

For every product capture:

product_id
source_url
merchant_name
brand
scraped_at
page_language
raw_product_name
raw_title
raw_full_description
raw_short_description if separately available
raw_bullet_points
raw_specifications
raw_material_text
raw_fit_text
raw_size_text
raw_color_text
raw_care_text
raw_features_text
raw_shipping_text if available
raw_return_text if available
raw_variant_text/data
raw_price_text
raw_sale_price_text
raw_availability_text
raw_rating_text
raw_review_count_text
raw_category_text
raw_breadcrumbs
raw_meta_title
raw_meta_description
raw_h1
canonical_url
raw_json_ld
raw_product_schema
raw_offer_schema
raw_product_group_schema
raw_variant_schema
image_urls
image_alt_text
SKU if present
GTIN if present
MPN if present

Do not shorten the full description.

Store the COMPLETE visible product description.

If the product page has multiple description sections such as:

- overview
- details
- fabric
- fit
- features
- care
- sustainability
- shipping

store all relevant sections separately AND preserve a combined full-text version.

Example:

{
  "raw_description": {
    "overview": "...",
    "details": "...",
    "fabric": "...",
    "fit": "...",
    "care": "...",
    "combined_text": "..."
  }
}

==================================================
4. NORMALIZED PRODUCT SCHEMA
==================================================

After raw extraction, normalize the product into this schema:

{
  "product_id": "",
  "source": { "url": "", "merchant": "", "scraped_at": "", "language": "" },
  "identity": { "brand": null, "product_name": null, "product_type": null, "subcategory": null, "audience": null },
  "content": { "title": null, "full_description": null, "short_description": null, "bullet_points": [], "meta_title": null, "meta_description": null, "h1": null },
  "materials": { "primary_material": null, "material_percentages": {}, "fabric_type": null, "fabric_weight_gsm": null, "fabric_weight_raw": null, "stretch": null, "texture": null },
  "fit_and_style": { "fit": null, "neckline": null, "collar_type": null, "sleeve_length": null, "shirt_length": null, "pattern": null, "style": null },
  "variants": { "colors": [], "sizes": [], "variant_count": null },
  "features": [],
  "care": [],
  "commerce": { "price": null, "sale_price": null, "currency": null, "availability": null, "rating": null, "review_count": null, "sku": null, "gtin": null, "mpn": null },
  "structured_data": { "product_schema_present": false, "offer_schema_present": false, "product_group_present": false, "raw_json_ld": [] },
  "evidence": []
}

==================================================
5. CONTROLLED VALUES
==================================================

Normalize common fields when supported.

product_type: t_shirt, polo, button_down, dress_shirt, oxford, flannel, henley, athletic_shirt, performance_shirt, overshirt, long_sleeve_shirt, short_sleeve_shirt, work_shirt, other
fit: slim, regular, relaxed, oversized, athletic, tailored, unknown
neckline: crew, v_neck, scoop, henley, other
sleeve_length: sleeveless, short, three_quarter, long, unknown
pattern: solid, striped, plaid, graphic, printed, textured, color_block, other
audience: men, women, unisex, kids, unknown

Do not force an item into a category if the source is ambiguous. Use: unknown

==================================================
6. MATERIAL NORMALIZATION
==================================================

Normalize material synonyms.

"100% cotton" → primary_material = cotton, material_percentages = { "cotton": 100 }
"60% cotton / 40% polyester" → material_percentages = { "cotton": 60, "polyester": 40 }

Common materials: cotton, organic_cotton, polyester, recycled_polyester, linen, rayon, viscose, modal, lyocell, elastane, spandex, wool, merino_wool, nylon, hemp, silk, blend, other

IMPORTANT: cotton does NOT equal organic cotton. Do not normalize "cotton" to "organic cotton" without explicit evidence.

==================================================
7. FABRIC WEIGHT
==================================================

If GSM is explicitly stated: "240 GSM" → fabric_weight_gsm = 240
If another unit is given: "8 oz fabric" → store the raw value.
Only convert to GSM when the conversion is deterministic and clearly documented.
Always keep: fabric_weight_raw
Example: { "fabric_weight_raw": "8.5 oz", "fabric_weight_gsm": 288 }
Document the conversion method.
Never let an LLM silently guess fabric weight.

==================================================
8. COLORS
==================================================

Keep both raw and normalized color values where useful.
raw: "Midnight Navy" → normalized: "navy", but preserve original_color_name = "Midnight Navy"
Do not throw away brand-specific color names.

==================================================
9. SIZES
==================================================

Extract sizes exactly as shown (XS S M L XL XXL, or 14 15 15.5 16, or region-specific sizing).
Do not force all sizing systems into one representation unless mapping is reliable.
Store: raw_size, normalized_size if possible.

==================================================
10. FULL PRODUCT DESCRIPTION REQUIREMENT
==================================================

THIS IS CRITICAL. We are training a model that will later analyze and improve product descriptions. Therefore the complete original product description must be preserved.

For every product record store:
1. original title
2. complete original description
3. bullets
4. specifications
5. materials section
6. fit section
7. care section
8. features section
9. product schema description if different
10. meta description

Do not summarize these fields. Do not paraphrase them. Do not use an LLM to rewrite them during collection. We need the actual source text.

==================================================
11. EVIDENCE FOR EACH NORMALIZED FACT
==================================================

Every important normalized fact should ideally contain evidence.

{ "field": "fit", "value": "oversized", "source_text": "Cut with an oversized relaxed fit.", "source_location": "product_description", "source_url": "...", "confidence": 0.98 }
{ "field": "material_percentages", "value": { "cotton": 100 }, "source_text": "100% combed cotton", "source_location": "product_specs", "source_url": "...", "confidence": 1.0 }

==================================================
12. CONFLICT HANDLING
==================================================

Do not silently resolve contradictions.
Description: "100% cotton"; Specifications: "95% cotton, 5% elastane" → record the conflict:
{ "field": "material", "status": "conflicting", "observations": [ { "value": "100% cotton", "source": "description" }, { "value": "95% cotton, 5% elastane", "source": "specifications" } ] }
Do not guess which is correct unless there is a clearly higher-authority source and the decision rule is documented.

==================================================
13. QUALITY FILTERS
==================================================

Reject or flag products when: page failed to load; product is not actually a shirt; description is completely unavailable; page contains mostly inaccessible content; important extraction is corrupted; duplicate product already exists; URL redirects to category/home page; record is obviously malformed.
Create quality_status: high, medium, low, reject. Prioritize high-quality records for later training.

==================================================
14. DUPLICATES
==================================================

Detect duplicates based on combinations of: canonical URL, SKU, GTIN, brand, product name, variant identity.
Do not accidentally treat every color variant as a completely unrelated product. Preserve variant relationships.
PRODUCT: Classic Heavyweight Tee; VARIANTS: black/S, black/M, white/S, white/M. The parent product and variants should be related.

==================================================
15. DATASET OUTPUT
==================================================

Produce at minimum: shirts_raw.jsonl, shirts_normalized.jsonl, shirts_validation_report.csv, dataset_stats.json
JSONL: one product per line.
Summary statistics: total products; products by shirt type; by merchant; by material; by fit; products with descriptions; with fabric weight; with structured data; with sizes; with colors; with ratings; with missing major attributes; duplicate count; rejected count.

==================================================
16. HUMAN VALIDATION SET
==================================================

Select at least 200 diverse shirt products for manual review, covering different brands, merchants, shirt types, materials, price ranges, descriptions, and levels of product-data completeness.
Mark reviewed records: human_reviewed = true. Store corrections separately. Never overwrite the original scraped values.

==================================================
17. FUTURE TRAINING FORMAT
==================================================

Prepare the dataset so later we can create training examples like:
INPUT: Raw title: Heavyweight Oversized Tee; Raw description: Made from 100% combed cotton with a substantial 240 GSM fabric. Designed with an oversized silhouette and crew neck...; Specifications: ...
OUTPUT: { "product_type": "t_shirt", "primary_material": "cotton", "material_percentages": { "cotton": 100 }, "fabric_weight_gsm": 240, "fit": "oversized", "neckline": "crew" }
But DO NOT train the model yet. The immediate deliverable is a trustworthy dataset.

==================================================
18. IMPLEMENTATION PRIORITY
==================================================

PHASE 1 Define schema. PHASE 2 Build extraction pipeline. PHASE 3 Test on 20 shirts. PHASE 4 Manually inspect failures. PHASE 5 Improve extraction. PHASE 6 Collect first 100 high-quality shirts. PHASE 7 Validate schema and normalization. PHASE 8 Scale collection toward 1,000+.
Do not scale a broken extractor.

==================================================
19. SUCCESS CRITERIA
==================================================

First milestone: 100+ high-quality shirt records with full descriptions preserved, raw source fields preserved, normalized shirt attributes, source evidence, minimal hallucination, duplicate handling, conflict handling, structured JSON output. Then scale the same pipeline to 1,000+ shirts. The final dataset must be suitable for later Qwen fine-tuning and evaluation.

The most important rule:
RAW SOURCE TEXT IS NEVER REPLACED.
NORMALIZED FACTS MUST BE SOURCE-BACKED.
MISSING INFORMATION MUST REMAIN MISSING.
DO NOT INVENT PRODUCT DETAILS.

Human addendum (2026-09-29): "we need different stores places so that we can compare" — collect from many different stores across different places/regions for comparison.
```

## Part B: decisions (schema v0.1.0)

### Records and missing values
- Two records per product, linked by `product_id`: a **raw** record (`raw_record.schema.json`, spec sections 3 and 10) and a **normalized** record (`normalized_record.schema.json`, sections 4-9 and 11-16).
- Every property is required. A value not found on the page is `null`; the schema rejects omitted keys and empty strings. Normalized lists (`features`, `care`, `bullet_points`, `colors`, `sizes`, `evidence`, `conflicts`) are `[]` when nothing is supported; `material_percentages` is `{}` when no percentages are stated.
- The raw description is ground truth. Text is copied from the page, never rewritten. Extraction rule for visible text: block elements (`p`, `br`, `li`, `div`, `td`, headings) become line breaks, inline tags are removed, HTML entities are decoded, whitespace inside a line is collapsed, and empty lines are dropped. No other character changes.
- `raw_description.sections` lists each product-specific section in page order with its exact heading and a `section_type` label; `combined_text` joins them (heading line, then text; blank line between sections). Site-wide pop-ups that are the same on every product (size charts, generic certificate modals) are not product sections. Reason: on the example page a shared certificate modal says "100% organic cotton" although the product is hemp and Tencel.
- JSON-LD is stored parsed (`raw_json_ld`), plus the Product, ProductGroup, Offer, and variant nodes as separate fields. The JSON-LD description stays inside those nodes when it differs from the visible description.
- Normalized `content` fields are copies of raw fields. The only change: leading list markers (for example `→ `) are removed from `bullet_points`.

### Evidence and conflicts
- Every normalized fact has at least one `evidence` item. `source_location` is a path into the raw record (for example `raw_material_text` or `raw_bullet_points[1]`), and `source_text` must be an exact substring of that field; the test suite checks this for the examples. `method` is `direct`, `rule`, `conversion`, `human`, or `model`, so model-produced values are never silent.
- A contradiction is recorded in `conflicts` with `status: conflicting` and `resolution: null`. `resolution` may be set only with `status: resolved` and a named rule. No authority ranking has been approved yet (**pending human**).

### Materials
- Keys of `material_percentages` must be in the section 6 enum. `cotton` never becomes `organic_cotton` without an explicit "organic" claim in product-specific text.
- A trademark that covers more than one fibre is mapped to `other` unless the fibre is named. Example: "Tencel" is used for both lyocell and modal, so "45% Tencel" becomes `other: 45`, and the evidence note says why.
- `primary_material` is the material with the largest stated percentage, or `null` if there is no single largest.

### Fabric weight (oz to GSM)
- GSM, g/m², or g/m2 stated: copy the number to `fabric_weight_gsm` (method `direct`).
- Conversion factor: 1 oz/yd² = 28.349523125 g / 0.83612736 m² = 33.906 g/m². `fabric_weight_gsm = round(oz × 33.906)`, an integer. Example: 8.5 oz/yd² → 288.
- Convert (method `conversion`) only when:
  1. the unit is explicitly oz/yd², oz/sq yd, or ounces per square yard (confidence 1.0); or
  2. a bare "oz" is stated as the **fabric** weight ("8 oz fabric", "6.5 oz cotton jersey", "8.5 oz. heavyweight"). US apparel convention states fabric weight in oz/yd², so this is converted with confidence 0.9 and the note "bare oz read as oz/yd² by US apparel convention" (**pending human** confirmation).
- Do not convert (keep `fabric_weight_raw`, set `fabric_weight_gsm: null`): oz per linear yard ("oz/yd", "oz/lin yd"), the weight of the whole garment ("weighs 8 oz"), or any other ambiguous case.
- `fabric_weight_raw` always keeps the stated weight text.

### Colors and sizes
- `original_color_name` keeps the merchant name exactly ("Snow White"); `normalized` is a lowercase basic colour ("white") or `null` if unclear. There is no closed colour list yet.
- Sizes keep `raw_size` exactly as shown. `normalized_size` is set only when the mapping is reliable (letter sizes copied as-is); otherwise `null`.

### Controlled values
- Section 5 enums are used as written, plus `null` for "not stated on the page". `unknown` means the page mentions the attribute but it is ambiguous.
- `product_type` mixes style (polo, oxford) and sleeve length (short_sleeve_shirt). Current rule: prefer the style type when stated; use a sleeve type for a generic collared shirt. `button_down` is used only when a buttoned-down collar is stated (**pending human**).

### IDs, parents, and variants
- Canonical URL for IDs: `canonical_url` if present, else `final_url`; lowercase scheme and host; drop query string and fragment; drop trailing slash. The locale path (for example `/en/`) is kept, so each language version is a separate record; duplicates across locales are found later by SKU/GTIN.
- `product_id = "p_" + first 16 hex chars of SHA-256(canonical URL)`.
- `variant_id = "v_" + first 16 hex chars of SHA-256(canonical URL + "#" + key)`, where the key is the merchant variant id, else SKU, else GTIN, else the option values sorted by name and joined as `name=value|...`.
- One record per parent product. Variants are embedded in `variants.items` and linked to the parent by the record's `product_id`; the merchant's own group id is kept in `variants.product_group_id`. Colour and size variants are never separate products.
- Duplicate detection (section 14) uses canonical URL, SKU, GTIN, brand + product name, and variant identity. It belongs to the pipeline phase, not Phase 1.

### Quality
- `quality_status` is `high`, `medium`, `low`, or `reject` (section 13). `quality_flags` are short snake_case reasons (for example `all_variants_out_of_stock`). Exact grading rules are set in the pipeline phase.
- `human_reviewed` marks records checked by a person. Corrections go in a separate file keyed by `product_id` and field; scraped values are never overwritten. The corrections file format is not defined yet.

### Benchmark and training split (**pending human**)
- Split by `merchant_domain`, so no store appears in both sets and the benchmark measures generalisation to unseen stores.
- Proposed rule: a domain goes to the benchmark set when `int(sha256(merchant_domain)[:8], 16) % 10 == 0` (about 10% of stores), otherwise to training. The 200-record human validation set (section 16) is drawn from both sets and marked by `human_reviewed`.
- Collection should span stores in several countries and languages (human addendum), so a split by domain also spreads regions across both sets.

### Collection etiquette
- Check robots.txt before fetching and skip disallowed paths. One request per page, an identifying user agent, no parallel requests to one store. Raw HTML caches stay local and are not committed (`dataset/output/` and `dataset/.cache/` are git-ignored).

### Example
- `dataset/examples/` holds one raw and one normalized record for https://thinkingmu.com/en/products/white-hemp-jules-shirt, fetched once at 2026-09-29T22:36:35Z (robots.txt allows `/en/products/`). Text was copied from the page with the extraction rule above.
