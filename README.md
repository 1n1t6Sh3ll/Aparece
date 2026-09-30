# Aparece

**See your product page the way AI shopping assistants do, and fix what they can't read.**

We asked gpt-4o-mini and Claude Haiku 384 real shopping questions (English and Spanish). None of the 103 small shirt shops we tested was named once; Everlane, Uniqlo and Patagonia were. Aparece shows a shop which facts machines can verify on its product page, ranks the page against similar shirts, and writes fixes that only state what the page proves.

## Install and run

```sh
docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/powerlens:latest      # or, from source:
git clone https://github.com/1n1t6Sh3ll/powerlens.git && cd powerlens && ./run.sh   # Windows: .\run.ps1
```

Open http://127.0.0.1:8000, paste a product URL and click **Audit**. You need Python 3.12+ and Node 22 to run from source. No API keys are needed; AI calls run only when you add a key.

To rank against real shirts, point the app at the dataset: `PRODUCTLENS_DATA=dataset/output/final/train.jsonl ./run.sh`. The dataset isn't in git because it contains third-party page text; build it with `dataset/collect/wdc.py` and then `dataset/build/make_ground_truth.py`. Model weights are on [weights-v1](https://github.com/1n1t6Sh3ll/powerlens/releases/tag/weights-v1).

## What we built

1. **A dataset of 20,037 shirts** from Common Crawl (Web Data Commons) and Amazon Reviews 2023. Every fact is stored with the exact text that proves it.
2. **A fine-tuned extraction model**: Qwen2.5-0.5B with QLoRA gets 85.8% of facts right, versus 27.2% for GPT-4.1 and 4.7% for untuned Qwen.
3. **The audit**: verified facts, a rank against comparable shirts, and the top 3 fixes.
4. **Generate Fix**: grounded text. Every sentence is fact-checked, and a reward picks the best candidate.
5. **The AI comparison**: the shop's text vs Aparece vs AI models, live for any audited product.
6. **The AI-visibility benchmark**: real model answers to realistic shopping questions.
7. **Monitoring, chat, webhooks, approvals**, plus a Chrome extension for pages we can't fetch, such as Amazon.

## How it works

**1. Matching (which shirts count as comparable).** `analysis/peers.py` keeps a candidate only if it has:
- the same product type, language and audience (adult or kids),
- the same pack size and sleeve length,
- a live link,
- a price in the same band when the currency is known.

Candidates are ordered by how many soft facts match (audience, price band, subcategory, fit, pattern, main material), then by closeness in price. With fewer than 10 matches, `api/audit_api.py` widens the match step by step: first without the price band, then without the sleeve, then any shirt type. The page says which step was used. The product itself is never its own peer.

**2. Scoring (the rank).** Every shirt in one ranking is scored with the same formula:

```
score = 60 × (key facts stated ÷ 22) + 20 × (shopper questions answered ÷ 9) + 20 × (Product/Offer markup ÷ 2)
rank  = 1 + number of comparable shirts with a higher score        (markup unknown → weights 75 / 25)
```

A shopper question counts only if a description sentence answers it and matches a verified fact. Keyword lists don't count. This is a listing-quality rank, not a Google or AI rank.

**3. Fixes.** The fixes list the facts you don't state, most-stated first among the 10 best-ranked similar shirts, then description, markup, price and language. Each fix shows its evidence.

**4. Generate Fix and the fact-check.** Candidates are written only from verified facts. `optimizer/guard.py` rejects a sentence if any word isn't backed by the facts, or if any number isn't that field's verified value. `train/reward.py` scores each candidate:

```
reward = 1 + share of sentences that pass − 2 × flagged sentences + 2 × share of verified facts covered
```

A flagged candidate can never win.

**5. Matching AI answers.** For the visibility benchmark, `benchmark/match.py` counts a product as mentioned when its exact URL appears, one of its aliases appears, or its brand and name appear on the same line. The metrics are mention rate, top-3 rate and MRR (average of 1 ÷ position of the first mention).

**6. The AI comparison.** `benchmark/shootout/` gives the same facts to each writer:
- **Aparece (no AI model)**: text built from templates;
- **Aparece + gpt-4o-mini**: the model writes inside Aparece's fact-check and reward;
- **gpt-4o-mini alone** and **claude-haiku-4-5 alone**;
- **the shop's original text**.

Each title, tag set and description is fact-checked and audited, and only passing parts can win.

All formulas, in plain words: the site's **How it works** page (`#/docs`) and [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Human in the loop (fine-tuning)

People stay in control at every step, and their decisions are recorded as training signal:

| Step | What the human does | Where it's stored | Code |
|---|---|---|---|
| Label check | Reviews a diverse sample of dataset labels | `dataset/output/final/human_review.csv` | `dataset/build/make_ground_truth.py` |
| Model predictions | The model's guesses are shown as "predicted", never "verified"; a merchant confirms a value, which needs approval, before it counts as a fact | Append-only audit log | `governance/hooks.py`, `POST /v1/predictions/confirm` |
| Generate Fix | The merchant accepts or dismisses each suggestion; nothing is published without approval | Merchant profile | `api/profile_api.py` |
| Preference pairs | Each winning candidate vs a lower-scoring one, facts only | `optimizer/data/pairs.jsonl` | `optimizer/fix.py` |

Training so far is supervised fine-tuning on the verified labels (`train/train.py`). Retraining on the pairs and confirmations (best-of-N and DPO, scored with `train/reward.py`) is designed but not yet run; see [train/README.md](train/README.md).

## Main files to read

| Problem | File |
|---|---|
| Read a page into verified facts | `dataset/collect/normalize.py`, `api/main.py` |
| Fetch politely (robots.txt, SSRF guard, no Amazon) | `api/safe_fetch.py` |
| Match comparable shirts | `analysis/peers.py` |
| Score, rank and pick the fixes | `api/audit_api.py` |
| Fact-check (guardrail) | `optimizer/guard.py`, `benchmark/claims.py` |
| Write grounded fixes | `optimizer/fix.py`, `optimizer/truth.py` |
| Reward | `train/reward.py` |
| Fine-tune and evaluate the model | `train/build_examples.py`, `train/train.py`, `train/eval.py`, `train/api_eval.py` |
| AI comparison | `benchmark/shootout/run.py`, `score.py`, `report.py`, `live.py` |
| AI visibility benchmark | `benchmark/harness.py`, `benchmark/match.py`, `benchmark/metrics.py` |
| Build the dataset | `dataset/collect/wdc.py`, `dataset/build/make_ground_truth.py` |
| Monitoring and chat | `monitor/`, `chat/` |
| Web app and extension | `web/src/`, `extension/` |

## How we compare models (and results)

We compare models in three ways. Each test gives every model the same input and scores it the same way.

| What's compared | Models | Same test for all | Result | Report |
|---|---|---|---|---|
| **Reading product pages** (fact extraction) | Aparece Qwen2.5-0.5B / 1.5B (fine-tuned), untuned Qwen, GPT-4.1, Claude Sonnet | The same 200 test products from 63 stores, scored against the answer key | Aparece 0.5B 85.8% · GPT-4.1 27.2% · untuned 4.7% | Models page `#/models`; `train/eval.py`, `train/api_eval.py` |
| **Writing product copy** (AI comparison) | Aparece (no AI model), Aparece + gpt-4o-mini, gpt-4o-mini alone, Claude Haiku alone, the shop's original | The same verified facts; every part goes through the same fact-check and scores | Aparece best on title, tags and description with no unsupported claims; visibility a statistical tie | Compare page `#/compare`; `benchmark/shootout/` |
| **Which shops AI assistants recommend** (AI visibility) | gpt-4o-mini, Claude Haiku | The same 384 shopping questions (192 EN, 192 ES) | 0% mention rate for the 103 small shops with both models; big brands named instead | Audit page panel; `benchmark/harness.py`, `benchmark/results/visibility-2026-09-30/` |

Caveats:
- The extraction scores are exact matches on our own label format, which favours the model trained on it. Claude Sonnet ran on only 87 of the 200 products.
- In the saved copy comparison, gpt-4o-mini and Claude Haiku also act as the judges in the simulated shopping test, with one held out as a check. That held-out judge disagreed on the visibility winner.
- The live comparison on the Compare page doesn't run the shopping test, so it has no visibility numbers.
- In the visibility test, both models gave 0% for small shops. It shows small shops versus big brands, not one model beating the other.

Every setting, API route and caveat: [docs/REFERENCE.md](docs/REFERENCE.md). Tests: `python -m unittest discover -s api/tests` and `cd web && npm test`. They are offline, with no paid calls.

The code is MIT-licensed. The data and model adapters are for research use; the data is not redistributed here.
