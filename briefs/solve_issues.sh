#!/usr/bin/env bash
# Solve bottleneck issues into proposed-fix sparks, one fresh agent session per repo, in parallel waves.
# Usage: solve_issues.sh <codex|claude> <wave> <repo>...
# Per repo: regenerate the evidence pack (model-free), record the run with `orch.py dispatch`, run the agent's
# Issues playbook step on that repo's open issue only. Codex waves stop if its 5h window drops below 30% left.
cd /c/jbax-and-his-ai-pals/_orchestrator
PY=.venv/Scripts/python.exe
ORCH="$PY scripts/orch.py --as claude-desktop"
lane=$1; wave=$2; shift 2
case $lane in
  codex)  agent=planner-codex;    model=openai/gpt-6.1-sol ;;
  claude) agent=architect-claude; model=anthropic/claude-sonnet-5-5 ;;
  *) echo "lane must be codex|claude"; exit 2 ;;
esac
log() { echo "$(date) [$lane $wave] $*" >> logs/solve_issues.log; }
codex_left() { curl -s http://127.0.0.1:8420/api/overview | $PY -c "import json,sys;d=json.load(sys.stdin);print(int([l for l in d['lanes'] if l['key']=='codex'][0]['quota']['windows']['5h']['value']))" 2>/dev/null || echo 0; }
if [ "$lane" = codex ]; then left=$(codex_left); if [ "$left" -lt 30 ]; then log "skipped wave: Codex 5h at ${left}% left"; exit 0; fi; fi
for r in "$@"; do
  id=$($ORCH issues --project "$r" --status triage | $PY -c "import json,sys;d=json.load(sys.stdin);print(d[0]['id'] if d else '')")
  if [ -z "$id" ]; then log "$r: no issue in triage, skipped"; continue; fi
  $PY briefs/evidence_packs.py "$r" > /dev/null
  ( $ORCH dispatch start --lane $lane --run solve-$r --label "solve $r issue $id" --project $r >/dev/null
    echo "$(date) start $r issue $id"
    openclaw.cmd agent --agent $agent --model $model --timeout 3600 \
      --session-key "agent:$agent:solve-$r-$(date +%s)" \
      --message "Do ONLY the Issues step of your playbook, for issue $id (project $r). Read C:/jbax-and-his-ai-pals/_orchestrator/dossiers/$r/EVIDENCE.md first, then DOSSIER.md, then only the code you need. End with issue-propose or issue-release. Never advance gates. Then stop."
    echo "$(date) end $r rc=$?"
    $ORCH dispatch end --lane $lane --run solve-$r >/dev/null ) > logs/solve-$lane-$r.log 2>&1 &
  log "$r: dispatched issue $id"
done
wait; log "wave done"
