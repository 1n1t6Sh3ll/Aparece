# Aparece

**See your product page the way AI shopping assistants do, and fix what they can't read.**

## In plain words

- **The problem.** Shoppers now ask AI assistants what to buy. We asked gpt-4o-mini and Claude Haiku 384 real shopping questions, in English and Spanish. None of the 103 small shirt shops we tested was named once. Big brands (Everlane, Uniqlo, Patagonia) were.
- **What Aparece does.** You paste a link to your product page. Aparece shows what machines can and cannot read on it, compares it with similar shirts from real stores, and tells you the 3 things to fix first.
- **What you get.** A rank, the fixes with the evidence for each, and a new title and description that only say what your page can prove. You approve everything; nothing changes on your store by itself.
- **What it won't do.** Invent facts, get around a website's blocks, or promise that a fix will raise your ranking.

## Try it

```sh
docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/powerlens:latest
```

Then open http://127.0.0.1:8000 and paste a product link. To run from source instead, use `git clone https://github.com/1n1t6Sh3ll/powerlens.git && cd powerlens && ./run.sh` (on Windows, `.\run.ps1`). That needs Python 3.12+ and Node 22. No API keys are needed.

To rank against real shirts, set `PRODUCTLENS_DATA=dataset/output/final/train.jsonl`. The dataset isn't in git because it contains other stores' page text; build it with `dataset/collect/wdc.py` and then `dataset/build/make_ground_truth.py`. The model weights are in the [weights-v1 release](https://github.com/1n1t6Sh3ll/powerlens/releases/tag/weights-v1).

## What we built, and where the code is

| Part | What it does | Code |
|---|---|---|
| Dataset | 20,037 shirts from Common Crawl and Amazon Reviews 2023; every fact keeps the text that proves it | `dataset/collect/`, `dataset/build/make_ground_truth.py` |
| Fetch | Downloads a page politely: respects robots.txt, never fetches Amazon | `api/safe_fetch.py` |
| Verified facts | Rules read the page into facts with evidence (EN/ES) | `dataset/collect/normalize.py`, `api/main.py` |
| Fine-tuned model | Qwen2.5-0.5B fills facts the rules missed, labelled "predicted" | `train/train.py`, `train/eval.py` |
| Matching | Finds comparable shirts: same type, language, audience, sleeve, price band | `analysis/peers.py` |
| Score and rank | Scores every shirt with one visible formula (below) | `api/audit_api.py` → `quality`, `rank` |
| Top 3 fixes | Missing facts the best similar shirts state, then description, markup, price, language | `api/audit_api.py` → `build_actions` |
| Fact-check | Rejects any sentence with a word or number the facts don't back | `optimizer/guard.py` |
| Generate Fix | Writes several candidates from facts only; the reward picks the best one that passes | `optimizer/fix.py`, `train/reward.py` |
| AI comparison | Shop's text vs Aparece vs AI models on title, tags and description | `benchmark/shootout/` (`live.py` for any product) |
| AI visibility | Asks real AI assistants shopping questions; measures who gets named | `benchmark/harness.py`, `benchmark/match.py` |
| Monitoring and chat | Re-checks products over time and shows what changed; the chat cites only stored data | `monitor/`, `chat/` |
| Web app and extension | The site, and a Chrome extension for pages we can't fetch | `web/src/`, `extension/` |

## How it works (the key formulas)

```
listing score = 60 × (key facts stated ÷ 22) + 20 × (shopper questions answered ÷ 9) + 20 × (markup found ÷ 2)
rank          = 1 + number of comparable shirts with a higher score
reward        = 1 + share of sentences that pass the fact-check − 2 × flagged sentences + 2 × share of facts covered
```

In the AI comparison, a title, tag set or description can only win if it passes the fact-check. The winners are:
- **title:** the best title score;
- **tags:** the best tag score;
- **description:** the most AI mentions, or the most facts covered when mentions weren't measured.

In the visibility test, a shop counts as "named" when an AI answer shows its link, or its brand and product name together.

Full explanation, every formula with its code location, and the vision mapping: the site's **How it works** page, or [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md).

## Model comparisons

| What's compared | Result |
|---|---|
| Reading product pages (200 products, 63 stores) | Aparece Qwen2.5-0.5B **85.8%** · GPT-4.1 27.2% · untuned Qwen 4.7% |
| Writing product copy (same facts for all) | Aparece best on title, tags and description with no unsupported claims; visibility a statistical tie |
| Which shops AI names (384 questions, 2 models) | 0% for the 103 small shops; big brands named instead |

The extraction test uses our own label format, which favours our model. The judges in the copy test are also AI models.

## Human in the loop

People review dataset labels and must confirm the model's guesses before they count as facts. They accept or dismiss every suggested fix. Each winning vs losing text pair is saved as future training data (`optimizer/data/pairs.jsonl`). The model has been trained on verified labels only so far; retraining on this feedback is designed but not run yet.

## Learn more

[How it works](docs/HOW_IT_WORKS.md) · [Reference: settings and API](docs/REFERENCE.md) · [Vision](docs/VISION.md) · [User stories](docs/USER_STORIES.md). Tests: `python -m unittest discover -s api/tests` and `cd web && npm test`; they run offline. The code is MIT-licensed; the data and model adapters are for research use.
