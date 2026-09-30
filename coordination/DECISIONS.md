# Decisions (authoritative record)
Human decisions, newest last. Link here instead of copying.

| Date | Decision | Where |
|---|---|---|
| 2026-09-29 | Project manager = Claude Code PM session | BOARD.md |
| 2026-09-29 | Board = GitHub Issues + project 2; `main` ruleset (PR, check, 1 approval, admin bypass on PR merge only) | BOARD.md |
| 2026-09-29 | Claims = `refs/claims/<TASK>` via GitHub API (TEAM-3, not built yet) | #3 |
| 2026-09-29 | Product name: ProductLens (repo rename undecided) | #2, #9 |
| 2026-09-29 | Vision: docs/VISION.md (§43 pending) | #7 |
| 2026-09-29 | First dataset: T-shirts first (other shirts if cheap); spec docs/DATASET_SPEC.md | #12 |
| 2026-09-29 | Data source for scale: Web Data Commons schema.org Product 2024-12 (Common Crawl); not Shopify; hackathon/research use | #16 |
| 2026-09-29 | Skip stores whose ToS forbid scraping | #14 |
| 2026-09-29 | Model: Qwen2.5-1.5B-Instruct QLoRA for attribute extraction; split by store domain | #19 |
| 2026-09-29 | No training until real dataset exists and is reviewed | #19 |
| 2026-09-29 | Benchmark: fine-tuned Qwen vs base Qwen, Claude, OpenAI, Gemini, same prompt, scored vs source-backed ground truth; no external API calls until spend approved | #21 |
| 2026-09-29 | Hackathon mode: move fast, minimal tokens, short reports | — |
| 2026-09-29 | Keep main clean: AI/agent tooling (.claude, .agents, .codex, CLAUDE.md, AGENTS.md, scripts/) is local-only and gitignored; CI `check` runs dataset tests | this PR |

Open: 200-record human reviewer; repo rename; §43 content; bare "oz" GSM rule; conflict authority rule.

## Since 2026-09-29 (recorded 2026-09-30)

| Date | Decision | Where |
|---|---|---|
| 2026-09-30 | Product name ProductLens (supersedes PowerLens in docs; repo name unchanged) | README |
| 2026-09-30 | Vertical: shirts, T-shirts first; EN/ES | README, DATASET_SPEC |
| 2026-09-30 | Data: WDC schema.org Product 2024-12 + Amazon Reviews 2023 (offline dump, research-only); Amazon pages never fetched | dataset/README |
| 2026-09-30 | No Gemini; API comparison uses OpenAI + Anthropic only, $5 spend cap (supersedes Gemini in #21) | README Model results |
| 2026-09-30 | Models: Qwen2.5-0.5B and 1.5B QLoRA | train/README |
| 2026-09-30 | Standing merge rule: PR + `check` + independent review + explicit human approval of the exact revision | BOARD.md |
| 2026-09-30 | Agent tooling stays local (gitignored), reaffirmed | this file |
| 2026-09-30 | No robots.txt or bot-wall bypass; blocked pages use draft audit | README |
| 2026-09-30 | AI visibility first; Google Search Console and SERP APIs deferred | README Known limitations |
| 2026-09-30 | No billing in the pilot | README Known limitations |
| 2026-09-30 | New visual theme for web app and extension | TEAM-48 |
