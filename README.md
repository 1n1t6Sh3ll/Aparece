# ProductLens

**See your product page the way AI shopping assistants do, and fix what they can't read.**

Paste a shirt's product URL. ProductLens reads the page, shows which facts machines can verify, ranks the listing against 20,000 similar shirts, and gives you the 3 fixes to make first, plus grounded text you can approve. English and Spanish.

> We asked gpt-4o-mini and Claude Haiku 384 real shopping questions. None of the 103 small shops we tested was named once; Everlane, Uniqlo and Patagonia were. ProductLens helps small shops close that gap without making up claims.

## Run it

**Docker**, no setup needed:

```sh
docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/powerlens:latest
```

**From source** (Python 3.12+, Node 22 for the web app):

```sh
git clone https://github.com/1n1t6Sh3ll/powerlens.git && cd powerlens
./run.sh          # macOS / Linux / Git Bash
.\run.ps1         # Windows PowerShell
```

Open **http://127.0.0.1:8000**, paste a product URL and click **Audit**. The API docs are at `/docs`.

`run.sh` creates a `.venv`, installs dependencies, builds the web app, runs the tests and starts the server (`--skip-tests` starts faster). Settings are optional: copy `.env.example` to `.env`. No API keys are needed. Paid AI calls happen only when you add a key and a spend cap.

### Add the comparison data

Ranking needs a dataset of comparable shirts. It isn't in git, because it holds third-party page text for research use. Without it, audits still show verified facts and fixes, but no rank. Build it from [Web Data Commons](https://webdatacommons.org/structureddata/) (schema.org Product, from Common Crawl), then point the app at it:

```sh
python dataset/collect/wdc.py --files part_1156.gz part_1274.gz part_1391.gz
python dataset/build/make_ground_truth.py --input wdc=dataset/output
PRODUCTLENS_DATA=dataset/output/final/train.jsonl ./run.sh
```

### Optional extras

| What | How |
|---|---|
| Chrome extension | `chrome://extensions`, then Developer mode, then **Load unpacked** and pick `extension/` |
| Fine-tuned extraction model | Download from [weights-v1](https://github.com/1n1t6Sh3ll/powerlens/releases/tag/weights-v1), then set `MODEL_BACKEND=qwen` and `QWEN_ADAPTER_PATH=<folder>` |
| AI text and chat backends | `OPTIMIZER_BACKEND` / `CHAT_LLM` = `openai`, `anthropic` or `qwen` (default `stub`, offline) |
| Monitoring schedule | `MONITOR_ENABLED=1` |

## What you get

| Feature | What it does |
|---|---|
| **Audit** | Verified facts, each with the page text that proves it; listing-quality rank vs similar shirts; the top 3 fixes |
| **Generate Fix** | Title and description written only from your facts; a guardrail rejects any unsupported sentence |
| **AI visibility** | Whether real AI assistants name your store for shopping questions, and who they name instead |
| **AI comparison** | Your text vs ProductLens vs AI models on title, tags and description |
| **Monitor** | Scheduled re-checks, snapshots, change diffs, trends, and a chat that cites only stored data |
| **Bulk and share** | Up to 20 URLs with CSV export; private report links |
| **Blocked stores** | Draft audit from pasted text, or the extension (Amazon is never fetched) |

## Results

| | |
|---|---|
| Fact extraction (200 test products, 63 stores) | Fine-tuned Qwen2.5-0.5B **85.8%** vs GPT-4.1 27.2% vs untuned 4.7% |
| AI comparison (5 products, EN/ES) | ProductLens best on title, tags and description with no unsupported claims (the AI models' own text had flagged parts); visibility a statistical tie |
| AI visibility (384 answers, 2 models) | 0% mention rate for the 103 small shops tested; big brands named instead |

The scoring and caveats are in [docs/REFERENCE.md](docs/REFERENCE.md).

## Project layout

```
web/         React app (audit site served at /)
api/         FastAPI server: audit, extraction, all /v1 routes
dataset/     Collectors and rules that turn pages into verified facts
analysis/    Peer matching and gap analysis
optimizer/   Generate Fix: grounded text + guardrail
benchmark/   AI-visibility benchmark and AI comparison (real results committed)
monitor/     Snapshots, change events, scheduler
chat/        Grounded merchant chat
train/       Qwen fine-tuning and evaluation (optional, GPU)
extension/   Chrome extension
docs/        How it works, reference, architecture, vision
```

Other folders: `signals/` (review and price signals), `governance/` (approvals and audit log), `webhooks/`, `profile/` (merchant accounts), `experiments/`, `tools/`, `coordination/` (team board).

## How it works

1. **Fetch** the page once, politely. robots.txt is respected and never bypassed, and Amazon is never fetched.
2. **Extract verified facts** with rules, in English and Spanish. Every value keeps the exact text that proves it; conflicts stay empty and are never guessed.
3. **Rank** against comparable shirts (same type, language and audience), using a formula shown on the page: key facts stated plus shopper questions answered.
4. **Recommend** the 3 fixes that the best-ranked similar shirts already have.
5. **Generate** grounded text. Several candidates are scored by a reward, and a guardrail throws out anything unsupported. You approve before anything is used.
6. **Measure AI visibility** by asking real models real shopping questions and recording who they name.
7. **Monitor** over time with snapshots, diffs and trends.

The full explanation, with who it helps, the models behind it and what it will not do, is in **[docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md)**.

| Doc | For |
|---|---|
| [How it works](docs/HOW_IT_WORKS.md) | The idea, each step, who it helps |
| [Reference](docs/REFERENCE.md) | Every setting, API route and module in detail |
| [Architecture](docs/ARCHITECTURE.md) | Code map per stage |
| [Vision](docs/VISION.md) | Where the product is going |
| [User stories](docs/USER_STORIES.md) | Customer personas and success measures |

## Tests

```sh
python -m unittest discover -s api/tests
cd web && npm test
```

The tests use local fixtures only: no network and no paid calls. All suites: [docs/REFERENCE.md](docs/REFERENCE.md#tests).

## Licence and data

The code is MIT. The model adapters are for research use (the base models are Apache-2.0). Collected data comes from Web Data Commons (Common Crawl) and Amazon Reviews 2023, for research use only, and is not redistributed here. Built by [1n1t6sh3ll](https://github.com/1n1t6Sh3ll) with AI coding agents working through a reviewed task board.
