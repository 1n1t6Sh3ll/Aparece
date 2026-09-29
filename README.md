# powerlens

## Team workflow
Humans, Claude Code, and Codex coordinate through the `project-team` skill. Start with `AGENTS.md` and `coordination/BOARD.md`.

- Skill: `.claude/skills/project-team/` and `.agents/skills/project-team/` (identical copies).
- Agents: `project-manager`, `project-worker`, `project-reviewer`, `project-researcher` in `.claude/agents/` and `.codex/agents/`.
- Check: `bash scripts/check-coordination.sh` (also runs in CI as `coordination / check`) fails if the skill copies or agent definitions drift.
- Merging: PR only, passing checks, independent review, updated docs, and explicit human approval of the exact revision.
