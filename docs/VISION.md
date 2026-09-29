# PRODUCTLENS AI — MASTER VISION BOARD PLAN

## 1. NORTH STAR

Build an evidence-driven platform that helps small businesses understand, improve, and track how their products are represented and discovered across search engines, AI search systems, recommendation systems, and LLM-generated shopping answers.

ProductLens should answer five questions:

1. HOW DOES AI/SEARCH CURRENTLY SEE MY PRODUCT?
2. WHERE DOES MY PRODUCT APPEAR?
3. WHAT INFORMATION OR SEARCH INTENTS AM I MISSING?
4. WHAT TRUTHFUL CHANGES SHOULD I TEST?
5. DID THOSE CHANGES ACTUALLY IMPROVE VISIBILITY?

The product must evolve from an audit tool into a continuous experimentation and learning platform.

---

# 2. CORE VALUE PROPOSITION

Small businesses should not have to guess how AI systems understand their products.

ProductLens:

MEASURES
→ ANALYZES
→ COMPARES
→ RECOMMENDS
→ TRACKS
→ EXPERIMENTS
→ LEARNS

The platform connects:

REAL PRODUCT DATA

+

REAL WEB/SEO DATA

+

COMPETITOR DATA

+

CUSTOMER SEARCH INTENTS

+

MULTILINGUAL DATA

+

OBSERVED AI/SEARCH RESULTS

+

BEFORE/AFTER EXPERIMENTS

to produce evidence-backed recommendations.

---

# 3. PRIMARY USER

Initial target:

Small ecommerce businesses and independent product brands.

Possible categories:

- Coffee
- Skincare
- Soap
- Packaged food
- Handmade products
- Specialty consumer goods

MVP RULE:

Choose ONE category first.

Do not attempt to solve every ecommerce category during the hackathon.

---

# 4. PRIMARY PRODUCT EXPERIENCE

The merchant visits their product page.

They open the ProductLens browser extension.

They click:

AUDIT PRODUCT

ProductLens automatically:

1. Identifies the product.
2. Crawls the product page.
3. Extracts product facts.
4. Extracts SEO/product-data signals.
5. Builds a Product Truth Record.
6. Finds comparable products.
7. Analyzes competitors.
8. Finds relevant keywords.
9. Finds customer search intents.
10. Checks description completeness.
11. Checks structured data.
12. Checks multilingual representation.
13. Tests AI/search visibility.
14. Measures product mentions/rank.
15. Checks AI claims for accuracy.
16. Finds measurable gaps.
17. Recommends improvements.
18. Tracks the product.
19. Measures changes over time.

---

# 5. PRODUCT LOOP

REAL PRODUCT

↓

CRAWL

↓

PRODUCT TRUTH

↓

SEO / PRODUCT DATA ANALYSIS

↓

COMPETITOR ANALYSIS

↓

KEYWORDS + CUSTOMER INTENTS

↓

MULTILINGUAL REPRESENTATION

↓

AI / SEARCH EVALUATION

↓

VISIBILITY METRICS

↓

GAP ANALYSIS

↓

RECOMMENDATION

↓

MERCHANT APPROVAL

↓

INTERVENTION

↓

PUBLISH

↓

WAIT FOR DISCOVERY / RECRAWL

↓

RETEST

↓

COMPARE AGAINST BASELINE + CONTROLS

↓

MEASURE OUTCOME

↓

STORE EXPERIMENT

↓

LEARN

↓

RECOMMEND BETTER INTERVENTIONS

↓

REPEAT

---

# 6. SYSTEM MAP

```
PRODUCT URL
│
▼
PRODUCT INGESTION
│
├── Product crawler
├── Product extractor
├── SEO extractor
└── Structured-data parser
│
▼
PRODUCT TRUTH / EVIDENCE LAYER
│
├── Facts
├── Sources
├── Confidence
├── Conflicts
└── Provenance
│
├───────────────────────┐
▼                       ▼
COMPETITOR ENGINE       PRODUCT TRACKER
│                       │
▼                       ▼
COMPETITOR DATA         VERSION HISTORY
│
▼
KEYWORD + INTENT ENGINE
│
▼
MULTILINGUAL ENGINE
│
├── English
└── Spanish
│
▼
AI / SEARCH BENCHMARK
│
▼
RAW RESPONSES
│
▼
ENTITY RESOLUTION
│
▼
CLAIM VERIFICATION
│
▼
METRIC ENGINE
│
▼
GAP ANALYZER
│
▼
RECOMMENDATION ENGINE
│
▼
DESCRIPTION / PRODUCT DATA OPTIMIZER
│
▼
EXPERIMENT ENGINE
│
▼
TRACKING + OUTCOME MEASUREMENT
│
▼
INTERVENTION DATASET
│
▼
FUTURE LEARNING MODEL
```

---

# 7. DATA PHILOSOPHY

Use REAL DATA wherever possible.

Do not build the main benchmark from invented products.

The initial dataset should contain:

REAL PRODUCTS

REAL PRODUCT PAGES

REAL PRODUCT DESCRIPTIONS

REAL PRICES

REAL ATTRIBUTES

REAL STRUCTURED DATA

REAL COMPETITORS

REAL PUBLIC WEB EVIDENCE

REAL SEARCH/SEO DATA WHEN AUTHORIZED

REAL AI/SEARCH OBSERVATIONS

REAL CHANGES OVER TIME

The platform does NOT claim to know the complete private training corpus of proprietary LLMs.

Instead, it measures publicly observable information and current black-box system behavior.

---

# 8. PRODUCT TRUTH RULE

Product Truth is the foundation.

Every important product fact should include:

VALUE

SOURCE

SOURCE URL

SOURCE TYPE

TIMESTAMP

EXTRACTION METHOD

CONFIDENCE

VERIFICATION STATUS

Possible statuses:

MERCHANT CONFIRMED

INDEPENDENTLY VERIFIED

THIRD-PARTY CLAIM

INFERRED

CONFLICTING

UNKNOWN

Never treat marketing language automatically as independently verified truth.

Never allow one LLM response to become ground truth.

---

# 9. PROVENANCE RULE

Maintain:

FACT
→ EVIDENCE
→ SOURCE
→ TIMESTAMP
→ EXTRACTION METHOD
→ CONFIDENCE

Do not silently overwrite conflicting information.

Keep historical observations.

---

# 10. SEO / WEB ANALYSIS

Analyze real measurable signals.

Examples:

- Title
- Meta description
- H1/H2/H3
- Canonical URL
- Robots directives
- Product JSON-LD
- Offer markup
- AggregateRating markup
- Breadcrumbs
- Hreflang
- Language
- Product attributes
- Internal linking
- Image metadata
- Page text
- Crawlability
- Indexability indicators

Where authorized, ingest first-party search-performance information such as:

- Search queries
- Impressions
- Clicks
- CTR
- Average position
- Country
- Device
- Page
- Date

Do not replace real measurements with arbitrary SEO scores.

---

# 11. KEYWORD STRATEGY

ProductLens should NOT only generate traditional keywords.

Maintain four concepts:

SEARCH KEYWORDS

LONG-TAIL QUERIES

PRODUCT ATTRIBUTES

CUSTOMER INTENTS

Example:

Product:

Colombian medium-roast coffee

Keyword:

Colombian coffee

Long tail:

medium roast Colombian coffee under $25

Attribute:

washed process

Customer intent:

coffee suitable for espresso

Every recommendation must be checked against Product Truth.

If the product does not support a term or claim, do NOT recommend inserting it.

---

# 12. DESCRIPTION ANALYSIS

Analyze descriptions for:

FACTUAL COMPLETENESS

ATTRIBUTE COVERAGE

CATEGORY CLARITY

CUSTOMER-INTENT COVERAGE

DIFFERENTIATION

ENTITY CONSISTENCY

AMBIGUITY

UNSUPPORTED CLAIMS

LANGUAGE COVERAGE

STRUCTURED INFORMATION

The analyzer should identify missing verified information.

It should NOT simply say:

"Your description is bad."

It should say:

"7 verified attributes are missing."

"4 relevant customer intents are not represented."

"Spanish representation contains only 8 of 17 verified product attributes."

"One claim cannot currently be supported by available evidence."

---

# 13. DESCRIPTION OPTIMIZATION RULE

Generated descriptions must come from:

PRODUCT TRUTH

+

TARGET MARKET

+

TARGET LANGUAGE

+

CUSTOMER INTENTS

NOT from copying competitors.

Never fabricate:

- Features
- Certifications
- Reviews
- Awards
- Origins
- Materials
- Ingredients
- Performance claims
- Health claims
- Sustainability claims

Truthfulness is a hard constraint.

---

# 14. COMPETITOR STRATEGY

Compare products with genuinely comparable products.

Similarity may include:

CATEGORY

SUBCATEGORY

PRICE BAND

ATTRIBUTES

USE CASE

MARKET

LANGUAGE

SEMANTIC SIMILARITY

Run the same extraction pipeline against competitors.

Compare measurable signals such as:

- Attribute completeness
- Description completeness
- Structured data
- Evidence
- Language coverage
- Intent coverage
- Entity consistency
- Observed AI visibility

Do NOT say:

"Competitor X ranks higher because it has better schema."

Instead say:

"Competitor X has more complete structured product information and also has higher observed visibility in this benchmark."

Correlation is not automatically causation.

---

# 15. MULTILINGUAL STRATEGY

MVP:

ENGLISH + SPANISH

Do NOT simply translate English keywords.

Create CANONICAL CUSTOMER INTENTS.

Example:

INTENT_017

"Find affordable Colombian medium-roast coffee from a small independent company."

Then generate natural localized expressions:

```
INTENT_017
├── English expression
└── Spanish expression
```

Compare equivalent customer needs across languages.

---

# 16. LANGUAGE ANALYSIS

Measure separately:

ENGLISH VISIBILITY

SPANISH VISIBILITY

ENGLISH ATTRIBUTE COVERAGE

SPANISH ATTRIBUTE COVERAGE

ENGLISH CLAIM ACCURACY

SPANISH CLAIM ACCURACY

ENGLISH INTENT COVERAGE

SPANISH INTENT COVERAGE

This allows ProductLens to identify language-specific gaps.

---

# 17. AI / SEARCH EVALUATION

Treat external systems as BLACK BOXES.

ProductLens can observe:

INPUT

↓

OUTPUT

But must not claim access to hidden:

TRAINING DATA

RANKING WEIGHTS

INTERNAL REASONING

SYSTEM PROMPTS

PROPRIETARY ALGORITHMS

Record each evaluation:

RUN ID

QUERY

CANONICAL INTENT

LANGUAGE

MARKET

SYSTEM

MODEL/VERSION WHEN AVAILABLE

TIMESTAMP

SETTINGS WHEN AVAILABLE

RAW RESPONSE

PRODUCTS MENTIONED

OBSERVED POSITIONS

CITATIONS

CLAIMS

---

# 18. REPEAT TESTS

Generative systems can vary.

Therefore do not treat one response as a permanent ranking.

Repeat important tests.

Measure stability.

---

# 19. CORE VISIBILITY METRICS

Use transparent metrics.

MENTION RATE

How often the product appears.

TOP-K RATE

How often the product appears within the first K observed recommendations.

MRR

Mean Reciprocal Rank.

PAIRWISE COMPETITOR WIN RATE

How frequently Product A appears above Product B in comparable runs.

CITATION RATE

How often the product/source is cited.

CLAIM ACCURACY

How many verifiable AI claims match Product Truth.

EVIDENCE COVERAGE

How many important claims have evidence.

ATTRIBUTE COMPLETENESS

How much verified product information is represented.

ENTITY CONSISTENCY

How consistently the product is represented across sources.

STABILITY

How much results vary across repeated runs.

---

# 20. NO MAGIC SCORE RULE

Do NOT initially create:

AI SCORE = 87/100

SEO AI SCORE = 72/100

RANKABILITY SCORE = 91

Instead show a transparent scorecard:

```
AI VISIBILITY

Mention Rate       31%
Top-3 Rate         12%
MRR                 .19

ACCURACY

Claim Accuracy      94%
Evidence Coverage   67%

PRODUCT DATA

Attribute Coverage  61%
Entity Consistency  84%

LANGUAGE

English Visibility  38%
Spanish Visibility  17%
```

Users should understand what every number means.

---

# 21. DIAGNOSIS RULE

Every diagnostic statement must be classified as:

OBSERVED FACT

SUPPORTED HYPOTHESIS

WEAK HYPOTHESIS

UNKNOWN

Example:

OBSERVED FACT:

Spanish product page contains 8/17 verified attributes.

OBSERVED FACT:

Spanish AI visibility is lower in the current benchmark.

SUPPORTED HYPOTHESIS:

Spanish product completeness is a reasonable intervention to test.

UNKNOWN:

How much weight a proprietary AI system internally assigns to this information.

---

# 22. RECOMMENDATION ENGINE

Possible recommendations:

ADD MISSING VERIFIED ATTRIBUTES

CORRECT CONTRADICTORY INFORMATION

IMPROVE PRODUCT TITLE

IMPROVE FACTUAL DESCRIPTION

IMPROVE STRUCTURED PRODUCT DATA

IMPROVE CUSTOMER-INTENT COVERAGE

CREATE LOCALIZED PRODUCT INFORMATION

CORRECT LANGUAGE INCONSISTENCIES

ADD LEGITIMATE EVIDENCE

Recommendations should be specific and actionable.

---

# 23. ATOMIC INTERVENTION RULE

Where possible, change ONE meaningful thing at a time.

Example experiments:

E1 — Improve product title.

E2 — Add missing verified attributes.

E3 — Improve Product structured data.

E4 — Add localized Spanish attributes.

E5 — Improve description around verified customer use cases.

E6 — Resolve contradictory product information.

This makes results easier to interpret.

---

# 24. PRODUCT TRACKING

ProductLens must track products continuously.

Create immutable/versioned snapshots.

```
PRODUCT
│
├── Snapshot 001
├── Snapshot 002
├── Snapshot 003
└── Snapshot N
```

Track changes in:

PRICE

AVAILABILITY

TITLE

DESCRIPTION

ATTRIBUTES

STRUCTURED DATA

RATINGS/REVIEW COUNTS WHERE PERMITTED

LANGUAGE PAGES

KEYWORD COVERAGE

INTENT COVERAGE

COMPETITORS

SEARCH PERFORMANCE

AI VISIBILITY

CLAIM ACCURACY

---

# 25. CHANGE EVENTS

Examples:

DESCRIPTION_CHANGED

PRICE_CHANGED

ATTRIBUTE_ADDED

ATTRIBUTE_REMOVED

SCHEMA_CHANGED

LANGUAGE_PAGE_ADDED

COMPETITOR_CHANGED

VISIBILITY_CHANGED

Every important event receives a timestamp.

---

# 26. EXPERIMENT FRAMEWORK

Every implemented recommendation becomes an experiment.

Store:

EXPERIMENT ID

PRODUCT

CATEGORY

LANGUAGE

MARKET

PROBLEM

INTERVENTION

BEFORE VERSION

AFTER VERSION

BASELINE METRICS

POST METRICS

CONTROL METRICS

HIDDEN-TEST METRICS

HOLDOUT-SYSTEM METRICS

ACCURACY BEFORE

ACCURACY AFTER

TIMESTAMPS

---

# 27. BENCHMARK PROTECTION

Split customer-intent queries:

60% DEVELOPMENT

20% VALIDATION

20% HIDDEN TEST

The optimizer must NEVER see the hidden test queries.

This helps detect benchmark overfitting.

---

# 28. CROSS-SYSTEM TESTING

Where possible:

OPTIMIZATION SYSTEMS

A
B

HOLDOUT SYSTEMS

C
D

If an intervention improves only the systems used during optimization but fails on unseen systems, treat that result cautiously.

Generalization is more valuable than model-specific exploitation.

---

# 29. CONTROL PRODUCTS

Track similar products that are not changed.

Example:

TARGET

Before: 18%
After: 34%

CONTROL

Before: 22%
After: 25%

Adjusted change estimate:

(34 - 18) - (25 - 22)

= +13 percentage points

Report:

"Estimated adjusted visibility lift: +13 percentage points."

Do NOT report:

"We proved the external LLM ranking algorithm gives this factor +13%."

---

# 30. ACCURACY GUARDRAIL

Visibility must NEVER be optimized by sacrificing truth.

Conceptual objective:

MAXIMIZE:

MEASURED VISIBILITY

SUBJECT TO:

FACTUAL ACCURACY >= REQUIRED THRESHOLD

UNSUPPORTED CLAIMS = 0

PRODUCT IDENTITY PRESERVED

EVIDENCE REQUIREMENTS SATISFIED

If visibility improves while factual accuracy becomes worse, treat the intervention as unsuccessful.

---

# 31. BROWSER EXTENSION

The extension is the merchant-facing interface.

Primary screens:

1. OVERVIEW
2. DESCRIPTION ANALYSIS
3. KEYWORDS & INTENTS
4. COMPETITORS
5. LANGUAGES
6. AI VISIBILITY
7. RECOMMENDATIONS
8. TRACKING / HISTORY

Primary actions:

AUDIT PRODUCT

ANALYZE DESCRIPTION

FIND OPPORTUNITIES

COMPARE COMPETITORS

IMPROVE DESCRIPTION

IMPROVE SPANISH

GENERATE PRODUCT DATA SUGGESTIONS

TRACK PRODUCT

START EXPERIMENT

---

# 32. BACKEND IS THE PRODUCT ENGINE

The browser extension should NOT contain sensitive or expensive business logic.

Backend owns:

CRAWLING

PRODUCT TRUTH

DATABASE

COMPETITOR ANALYSIS

AI EVALUATION

METRICS

DESCRIPTION ANALYSIS

RECOMMENDATIONS

EXPERIMENTS

TRACKING

API KEYS

The extension is primarily the interface.

---

# 33. WHAT SHOULD BE DETERMINISTIC

Use normal software for:

PRICES

URLs

HTTP STATUS

JSON-LD PARSING

SCHEMA FIELDS

TIMESTAMPS

RANK/POSITION CALCULATIONS

MENTION RATE

TOP-K

MRR

BEFORE/AFTER STATISTICS

VERSIONING

HASHING

CHANGE DETECTION

Do not ask an LLM to calculate things deterministic code can calculate reliably.

---

# 34. WHAT SHOULD USE AI

Use LLMs selectively for:

SEMANTIC PRODUCT EXTRACTION

AMBIGUOUS ENTITY RESOLUTION

CLAIM EXTRACTION

INTENT GENERATION

QUERY LOCALIZATION

DESCRIPTION ANALYSIS

DESCRIPTION GENERATION

SEMANTIC COMPETITOR ANALYSIS

RECOMMENDATION EXPLANATION

AI-generated factual statements must be checked against Product Truth.

---

# 35. IMPORTANT ARCHITECTURAL RULE

Never allow:

ONE LLM
→ GENERATES TRUTH
→ JUDGES ITS OWN TRUTH
→ SCORES ITSELF

Separate:

EVIDENCE

MEASUREMENT

OPTIMIZATION

EVALUATION

---

# 36. DATA MODEL

Core entities:

BUSINESS

PRODUCT

PRODUCT FACT

PRODUCT SNAPSHOT

SOURCE

WEB OBSERVATION

SEO SNAPSHOT

COMPETITOR RELATIONSHIP

KEYWORD

CANONICAL INTENT

LOCALIZED QUERY

EVALUATION RUN

MODEL RESPONSE

PRODUCT MENTION

CLAIM

CITATION

METRIC SNAPSHOT

ISSUE

RECOMMENDATION

INTERVENTION

EXPERIMENT

CONTROL PRODUCT

EXPERIMENT RESULT

CHANGE EVENT

---

# 37. MVP DATASET

Start with:

30–50 REAL PRODUCTS

ONE PRODUCT CATEGORY

3–5 COMPARABLE PRODUCTS PER TARGET PRODUCT

30–50 CANONICAL CUSTOMER INTENTS

ENGLISH + SPANISH

2–3 PERMITTED AI/SEARCH SYSTEMS

REPEATED EVALUATIONS WHERE PRACTICAL

REAL PRODUCT PAGES

REAL SEO/STRUCTURED PRODUCT DATA

REAL COMPETITOR DATA

REAL AI OBSERVATIONS

---

# 38. HACKATHON BUILD PHASES

## PHASE 1 — FOUNDATION

Build:

DATABASE

PRODUCT INGESTION

CRAWLER

PRODUCT EXTRACTOR

SEO EXTRACTOR

JSON-LD PARSER

PRODUCT TRUTH RECORD

SNAPSHOT SYSTEM

Goal:

REAL URL
→ RELIABLE STRUCTURED PRODUCT RECORD

---

## PHASE 2 — INTELLIGENCE

Build:

COMPETITOR ENGINE

KEYWORD ENGINE

CUSTOMER INTENT ENGINE

DESCRIPTION ANALYZER

Goal:

PRODUCT
→ MEASURABLE GAPS

---

## PHASE 3 — MULTILINGUAL

Build:

ENGLISH INTENTS

SPANISH INTENTS

LANGUAGE COVERAGE ANALYSIS

LOCALIZED DESCRIPTION GENERATION

Goal:

PRODUCT
→ LANGUAGE-SPECIFIC ANALYSIS

---

## PHASE 4 — AI VISIBILITY

Build:

EXTERNAL SYSTEM ADAPTERS

QUERY RUNNER

RAW RESPONSE STORAGE

ENTITY RESOLUTION

CLAIM EXTRACTION

CLAIM VERIFICATION

METRIC ENGINE

Goal:

PRODUCT
→ OBSERVED AI VISIBILITY

---

## PHASE 5 — RECOMMENDATIONS

Build:

GAP ANALYZER

RECOMMENDATION ENGINE

DESCRIPTION OPTIMIZER

STRUCTURED-DATA RECOMMENDATIONS

Goal:

MEASUREMENT
→ ACTION

---

## PHASE 6 — TRACKING

Build:

PRODUCT TRACKING

CHANGE DETECTION

TIMELINE

METRIC HISTORY

Goal:

ONE-TIME AUDIT
→ CONTINUOUS PRODUCT

---

## PHASE 7 — EXPERIMENTATION

Build:

EXPERIMENT IDs

BEFORE/AFTER SNAPSHOTS

HIDDEN QUERY SET

CONTROL PRODUCTS

ADJUSTED LIFT

Goal:

RECOMMENDATION
→ MEASURABLE OUTCOME

---

# 39. HACKATHON DEMO STORY

Use ONE real product for the primary demonstration.

STEP 1

Open the real small-business product page.

STEP 2

Open ProductLens.

STEP 3

Click:

AUDIT PRODUCT

STEP 4

Show extracted real product facts.

STEP 5

Show Product Truth and sources.

STEP 6

Show SEO/product-data gaps.

STEP 7

Show real competitor comparison.

STEP 8

Show keywords and customer intents.

STEP 9

Show English vs Spanish representation.

STEP 10

Show observed AI visibility.

STEP 11

Show factual inaccuracies or missing representation.

STEP 12

Show recommended intervention.

STEP 13

Generate an improved factual description/product representation.

STEP 14

Evaluate the proposed representation using hidden benchmark queries.

Clearly label this as an offline/controlled evaluation, not proof of production ranking improvement.

STEP 15

Show the real tracking loop:

PUBLISH
→ WAIT FOR DISCOVERY
→ RECRAWL
→ RETEST
→ COMPARE WITH CONTROLS
→ MEASURE OUTCOME

STEP 16

Show how the experiment becomes future training data.

---

# 40. LONG-TERM DATA MOAT

Public product data alone is not the moat.

The long-term proprietary dataset is:

PRODUCT STATE

+

CATEGORY

+

MARKET

+

LANGUAGE

+

SEO STATE

+

COMPETITOR STATE

+

AI VISIBILITY

+

PROBLEM DETECTED

+

INTERVENTION

+

BEFORE/AFTER OUTCOME

+

CONTROL MOVEMENT

+

GENERALIZATION RESULTS

This answers:

WHAT WAS WRONG?

WHAT DID WE CHANGE?

WHAT HAPPENED?

---

# 41. FUTURE LEARNING SYSTEM

Do NOT train a custom foundation model initially.

After enough experiments, train models to estimate:

```
P(
VISIBILITY IMPROVEMENT
|
PRODUCT,
CATEGORY,
MARKET,
LANGUAGE,
PROBLEM,
INTERVENTION
)
```

Eventually ProductLens should predict which intervention is most promising to test first.

Example:

"Spanish attribute completeness is the highest-priority experiment."

NOT:

"This guarantees your product will rank higher."

---

# 42. FUTURE PLATFORM

Long-term ProductLens can support:

BROWSER EXTENSION

WEB DASHBOARD

SHOPIFY INTEGRATION

WOOCOMMERCE INTEGRATION

MERCHANT API

AGENCY DASHBOARD

MULTILINGUAL OPTIMIZATION

PRODUCT FEED ANALYSIS

AI VISIBILITY MONITORING

COMPETITOR MONITORING

AUTOMATED EXPERIMENTS WITH MERCHANT APPROVAL

---

# 43. THINGS WE MUST NOT BUILD

_(Section content not yet provided — pending from human.)_
