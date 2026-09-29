#!/usr/bin/env bash
# Verifies shared coordination files are present and in sync.
set -euo pipefail
fail=0
cmp -s .agents/skills/project-team/SKILL.md .claude/skills/project-team/SKILL.md \
  || { echo "project-team skill copies differ"; fail=1; }
for a in project-manager project-researcher project-reviewer project-worker; do
  c=.claude/agents/$a.md; x=.codex/agents/$a.toml
  [[ -f $c && -f $x ]] || { echo "missing agent $a"; fail=1; continue; }
  grep -q "^name: $a$" "$c" && grep -q "^name = \"$a\"$" "$x" \
    || { echo "agent name mismatch: $a"; fail=1; }
  dc=$(sed -n 's/^description: //p' "$c"); dx=$(sed -n 's/^description = "\(.*\)"$/\1/p' "$x")
  [[ $dc == "$dx" ]] || { echo "agent description mismatch: $a"; fail=1; }
done
for f in AGENTS.md CLAUDE.md coordination/BOARD.md; do [[ -f $f ]] || { echo "missing $f"; fail=1; }; done
[[ $fail -eq 0 ]] && echo "coordination check passed"
exit $fail
