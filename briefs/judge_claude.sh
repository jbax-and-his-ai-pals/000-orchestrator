#!/usr/bin/env bash
# Seeding: judgment pass by architect-claude, one fresh session per repo, in parallel. Usage: judge_claude.sh <wave> <repo>...
# Low/skip-priority repos are skipped (producer 2026-11-13: low = ideas only).
# Each run is recorded with `orch.py dispatch` so the dashboard's Agents Now shows it.
cd /c/jbax-and-his-ai-pals/_orchestrator
ORCH=".venv/Scripts/python.exe scripts/orch.py --as claude-desktop"
wave=$1; shift
for r in "$@"; do
  prio=$(.venv/Scripts/python.exe -c "import sys;sys.path.insert(0,'scripts');import orch
with orch.db() as c: print(orch.get_project(c,'$r')['priority'])")
  if [ "$prio" = low ] || [ "$prio" = skip ]; then echo "$(date) $r skipped: priority $prio (ideas only)" >> logs/priority_skips.log; continue; fi
  ( $ORCH dispatch start --lane claude --run judge-$r --label "judge $r dossier" --project $r >/dev/null
    echo "$(date) start $r"
    openclaw.cmd agent --agent architect-claude --model anthropic/claude-sonnet-5-5 --timeout 3600 \
      --session-key "agent:architect-claude:judge-$r-$(date +%s)" \
      --message "Read C:/jbax-and-his-ai-pals/_orchestrator/briefs/seed-claude.md and follow it for project $r only. Never advance gates. Then stop."
    echo "$(date) end $r rc=$?"
    $ORCH dispatch end --lane claude --run judge-$r >/dev/null ) > logs/judge-claude-$r.log 2>&1 &
done
wait; echo "$(date) wave $wave done" >> logs/judge_claude.log
