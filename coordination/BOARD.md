# PowerLens bootstrap board
Project manager: Claude Code PM session (human-designated 2026-09-29; previously a Codex chat, now worker/reviewer). The human can change the owner.
Claim mode: proposed claims confirmed by the PM until TEAM-3 (atomic ref claims) is verified. This file is a bootstrap board, not a synchronized claim service; it moves to GitHub Issues + Project once TEAM-6 is done.

| Task | Owner | Status | Result / next step |
|---|---|---|---|
| TEAM-1 Shared skill | Claude PM | Review (in TEAM-5 PR) | Repo copies synced to the current global skill (adds human merge gate + attribution); CI checks copies match. Codex runtime discovery unverified (codex CLI not on PATH) |
| TEAM-2 Product brief | Human + PM | Blocked | Human describes what PowerLens does and the first useful feature |
| TEAM-3 Live shared claims | Unclaimed | Blocked on TEAM-6 | Decided: claim = create `refs/claims/<TASK>` via GitHub API (fails if it exists). Accept: script to claim/release/list, simultaneous-claim race test showing exactly one winner, docs |
| TEAM-4 First feature | Unclaimed | Blocked | Depends on TEAM-2 |
| TEAM-5 Coordination setup PR | Claude PM | Review | Branch `setup/coordination`: skill sync, `scripts/check-coordination.sh`, `coordination` CI workflow, README. Needs independent review + human merge approval |
| TEAM-6 GitHub board + protection | Claude PM | Blocked | `gh` 2.101.0 installed; awaiting human `gh auth login`. Then: Issues + Project board; ruleset on `main` (PR, 1 approval, `check` status required, up to date, no force-push/deletion) |

Claim format: ID, owner/session, parent if any, files/scope, workspace, expected result.
Handoff format: ID, revision/artifact, checks/results, blocker, next owner.
Done requires independent review and integration evidence. Important decisions go to the human; routine work within a claim proceeds.
