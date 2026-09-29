---
name: project-team
description: Coordinate project work between humans, Claude, Codex, and subagents using shared task claims and short evidence-based handoffs.
---

Read the project instructions and the authoritative task board. Use three rules:
1. Claim before editing. One active owner per task, with a task ID, allowed files, workspace, and expected result.
2. Stay within the claim. Use separate workspaces for concurrent writers. Ask the human or orchestrator when scopes overlap, requirements conflict, or a decision materially changes the project.
3. Show evidence before Done. Submit the revision/artifact and checks actually performed. An independent reviewer checks the result; the orchestrator checks integration.

Have one named project manager per project. The manager maintains priorities, acceptance criteria, dependencies, and the board; resolves competing claims; and asks the human about unresolved product decisions. Workers claim ready tasks rather than waiting for approval of every routine step. The project manager may also act as orchestrator; do not create another management layer unless needed. Implementation still needs independent review.

Keep updates short: task, owner, status, evidence, blocker/next step. Prefer simple code and reuse existing project components.

Use the connected claim tool if available. Do not pretend an issue assignment or Markdown edit is an atomic claim. If there is no claim service, propose a claim and have the human or single coordinating session confirm it before editing; independent read-only work can continue.

Subagents get child tasks within the parent's claimed scope and budget. The parent owns their handoff. Delegate only when useful and authorized; use available tools rather than assuming Claude and Codex can launch each other.

Ask humans for unresolved product choices, scope conflicts, and unapproved spending or consequential external actions. Do not repeatedly ask about routine work already authorized. Keep credentials out of the board.

State what is verified, assumed, or blocked. Never invent tests, sources, metrics, board updates, or agent activity. Skills do not themselves provide a live board, atomic claims, or cloud execution.
## Context, documentation, and human gates
Read the task and relevant files first; avoid loading entire histories or repeating shared instructions. Handoffs contain only decisions, revision/artifact links, checks, blockers, and next action. Delegate only when it saves meaningful work; give each child the minimum sufficient context. Never omit required verification to save tokens.

Update affected README, API/setup documentation, and task status with behavior changes. If no documentation change is needed, explain that briefly in the review. Keep one authoritative decision record and link it rather than copying it.

Before every merge: verify acceptance criteria; run applicable tests, build/lint/type checks and integration checks; inspect the complete diff for unintended files, credentials, interface changes, and regressions; obtain independent review of the exact revision; update affected documentation. Record commands, actual results, and any unverified items. Missing, failed, or stale required checks block merging; do not claim comprehensive verification when coverage is limited.

Present a short approval packet to the human: PR/revision, outcome, checks, review, documentation, remaining risks. Require explicit human approval for that exact revision before every merge. Changed revisions require renewed review/checks as applicable and renewed human approval. Approval of a plan, task, or review is not merge approval. Do not auto-merge, push directly to main, force-push shared branches, or bypass protections. Ask humans about scope conflicts, material product/architecture choices, spending, deployment, and destructive actions; proceed with routine authorized work within the claim.

These are agent instructions, not enforced GitHub controls. Report branch protection and required checks as pending until actually configured and verified.

# Source attribution and simple implementation

When copying or adapting external code, record the source URL, author/project, version or commit when available, license, affected files, and modifications in THIRD_PARTY_NOTICES.md. Keep any required copyright and license notices with the code or distribution. Attribution alone does not grant permission: if reuse terms are missing or incompatible, do not copy; find a compatible alternative or ask the human. Cite research and documentation in the relevant task or design decision. Distinguish dependencies, copied code, and conceptual references.

Choose the simplest maintainable solution that meets acceptance criteria. Reuse suitable existing components, avoid duplicate logic and speculative abstractions, and add dependencies only when their benefit justifies their cost. Do not claim a solution is optimal without evidence; measure performance when it matters. Never sacrifice correctness, necessary security, or meaningful checks for fewer lines or tokens.

