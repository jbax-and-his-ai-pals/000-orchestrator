#!/usr/bin/env bash
# Seeding: deep dossiers by planner-codex, one fresh session per repo, in parallel. Usage: seed_codex.sh <wave> <repo>...
# Each run is recorded with `orch.py dispatch` so the dashboard's Agents Now shows it.
cd /c/jbax-and-his-ai-pals/_orchestrator
ORCH=".venv/Scripts/python.exe scripts/orch.py --as claude-desktop"
wave=$1; shift
for r in "$@"; do
  ( $ORCH dispatch start --lane codex --run seed-$r --label "seed $r dossier" --project $r >/dev/null
    echo "$(date) start $r"
    openclaw.cmd agent --agent planner-codex --model openai/gpt-6.1-sol --timeout 3600 \
      --session-key "agent:planner-codex:seed-$r-$(date +%s)" \
      --message "Read C:/jbax-and-his-ai-pals/_orchestrator/briefs/seed-codex.md and follow it for project $r only. Never advance gates. Then stop."
    echo "$(date) end $r rc=$?"
    $ORCH dispatch end --lane codex --run seed-$r >/dev/null ) > logs/seed-codex-$r.log 2>&1 &
done
wait; echo "$(date) wave $wave done" >> logs/seed_codex.log
