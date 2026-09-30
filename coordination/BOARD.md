# ProductLens board (repo: powerlens)

Current status (2026-09-30, main `578dfa0`): on main: the audit loop, rank formula, Generate Fix, AI comparison (with keyword boost), Check now live visibility, description panel, 4-model visibility card, dark default, compact README, Docker/Fly deploy config; the production app is https://aparece.fly.dev. Open: peer data and persistence on prod, fetch fallback for blocked shops, fixes without peers (issues #118, #112, #104, #95). TEAM-INTEGRATION (#132) is in progress until this consolidation merges. Model results: README "Model results". Live task status is in GitHub Issues, not here.

Authoritative board: GitHub Issues in this repo, shown on the project https://github.com/users/1n1t6Sh3ll/projects/2. Each task has an issue titled `TEAM-<n> ...` with a `status:*` label (ready, in-progress, review, blocked).
Project manager: Claude Code PM session (human-designated 2026-09-29). The human can change the owner.
Decisions: `DECISIONS.md`. Vision: `docs/VISION.md`. Dataset spec: `docs/DATASET_SPEC.md`. Training: `train/README.md`.
Claim mode: until TEAM-3 (atomic `refs/claims/<TASK>` claims) is verified, propose a claim as an issue comment and wait for PM confirmation before editing. Issue assignment is not an atomic claim.

Claim format: ID, owner/session, parent if any, files/scope, workspace, expected result.
Handoff format: ID, revision/artifact, checks/results, blocker, next owner.
Done requires independent review and integration evidence. Important decisions go to the human; routine work within a claim proceeds.

`main` is protected by the ruleset "main protection": PR required, 1 approval (repo admins may bypass on PR merge only), required check `check` on an up-to-date branch, no force-push or deletion. Merging also needs explicit human approval of the exact revision.
