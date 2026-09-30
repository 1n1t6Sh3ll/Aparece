# Governance

The policy is enforced in `governance/policy.py` (`POLICY`, `require()`) and served at `GET /v1/governance/policy`. This page describes the same rules for people to read. If this page and the code disagree, the code is what runs; fix whichever one is wrong.

The business plan's governance table is not in this repo; `docs/VISION.md` §43 is still pending from the human. The matrix below follows the pipeline in VISION.md (…RECOMMENDATION → MERCHANT APPROVAL → INTERVENTION → PUBLISH…) and the principle "automated experiments with merchant approval". Once the plan's table is available, check this matrix against it.

## Roles
| Role | Accountable for |
|---|---|
| **Account owner** | Budget and spend, plan/billing, who can see account data, alerts. |
| **Merchant** | Their listings: which predictions become facts, what gets published, which experiments run. |
| **ProductLens operator** | Running the service: crawls, extraction, benchmarks within budget, data licensing, audit integrity. |

## Action matrix
Mode `auto` runs and is logged. `approve` means a named person with the owner role must approve that exact request, and the requester cannot approve it. `forbidden` is never automatic. Any action not listed is denied.

| Action | Mode | Owner |
|---|---|---|
| extract_product: extract or normalize a page the user submitted | auto | ProductLens operator |
| monitor_crawl: recrawl an enrolled product and record changes | auto | ProductLens operator |
| benchmark_free_run: mock or local models, no spend | auto | ProductLens operator |
| benchmark_paid_run: `--max-usd` <= `BENCHMARK_MAX_USD` (the standing budget) | auto | Account owner |
| generate_suggestions: drafts only, not published | auto | ProductLens operator |
| change_alert: notify an enrolled owner | auto | Account owner |
| benchmark_paid_run_over_cap: above the standing budget, or no budget set | approve | Account owner |
| confirm_model_prediction: a predicted attribute becomes a fact | approve | Merchant |
| publish_suggestions: mark publish-ready or apply | approve | Merchant |
| run_experiment: start a listing experiment | approve | Merchant |
| change_plan_or_billing | approve | Account owner |
| auto_publish_to_storefront without per-change approval | forbidden | Merchant |
| optimize_on_hidden_split | forbidden | ProductLens operator |
| share_merchant_data: sell or share with third parties | forbidden | Account owner |
| train_on_restricted_data: license or consent does not allow it | forbidden | ProductLens operator |
| fabricate_claims: attributes, reviews or metrics without evidence | forbidden | Merchant |
| alter_audit_log | forbidden | ProductLens operator |

## Approval flow
1. The caller runs `require(action, actor, target, details)`. For an `approve` action with no valid approval, it raises `ApprovalRequired` and records a pending request (`GET /v1/approvals`).
2. The owner calls `POST /v1/approvals` with `{approval_id, approver, role, approve}` and the header `X-Governance-Token`. This endpoint is disabled (503) until `GOVERNANCE_TOKEN` is set, because the API has no user accounts yet.
3. The caller retries with `approval_id`. The approval applies only to the same action, target and details (matched by a SHA-256 of the details), and it can be used once.

Current hooks:
- `governance.hooks.gate_benchmark_run(args)` for paid benchmark runs.
- `POST /v1/predictions/confirm`, which calls `hooks.confirm_prediction`.

When a request is allowed, the hooks do not change the action's behavior.

## Audit log
The log is stored in its own SQLite file, `GOVERNANCE_DB` (default `governance/data/governance.db`, git-ignored). Each row records who, action, target, mode, outcome (allowed/denied/pending/approved/rejected), approved_by, approval_id, a UTC timestamp and `details_hash` (SHA-256; raw details are not stored). SQLite triggers abort any UPDATE or DELETE. Read it with `GET /v1/audit-log?limit=` (1–1000, newest first).

## Data, licensing and privacy
- Only collect product pages that a user submitted or enrolled. Fetches go through `api/safe_fetch.py` (SSRF guard, size limit). Merchant or shopper data is never sold or shared.
- Research-only datasets, such as Amazon Reviews 2023, are used for research signals only. They are not shipped in product outputs as licensed content. Record the source and license with every dataset, and record any copied code in THIRD_PARTY_NOTICES.md.
- Store the minimum: an email only when enrolling for alerts. The audit log stores hashes, not payloads. API keys are read only from the environment, never logged, and never written to the board.
- Model predictions stay under `predicted` with a confidence score. They are never written into the normalized record until a Merchant confirms them.

## Evaluation integrity
- Hidden-split prompts and results never reach an optimizer (`optimize_on_hidden_split` is forbidden, and the harness warns).
- Record the model, model version, settings, seed and timestamp for every call. Report cost and caps.
- Compare outcomes against a baseline and controls before claiming an effect, and never publish metrics without evidence.
- Paid runs need `--max-usd`. Going above the standing budget needs Account owner approval.

## Pending
- `benchmark/harness.py` and `monitor/crawl.py` do not call `gate_benchmark_run` yet. Adding that edit needs explicit permission.
- Dockerfile/.dockerignore do not yet ship `governance/` (TEAM-36). Until they do, `api/main.py` skips the governance routes when the package is missing.
- There are no real user identities: `approver`/`role` are self-declared by the holder of `GOVERNANCE_TOKEN`. The self-approval check compares ids after trimming spaces and ignoring case, but that does not stop someone using a different name.
