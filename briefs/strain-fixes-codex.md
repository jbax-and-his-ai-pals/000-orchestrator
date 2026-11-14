# Build brief: orchestrator strain fixes (planner-codex)

Producer directive 2026-11-13: "we need to fix the obvious strains, and then when giving me playtest tasks, i need
expert clarity and a crisp bullet list of actions and expectations". The conductor (Claude in chat) reviews your
branch; the producer merges. Never merge, push, switch branches, or touch `main` or the live `state/` DB.

- **Worktree:** `C:/jbax-and-his-ai-pals/_orchestrator/worktrees/000-orchestrator/strain-fixes`
  (branch `feat/strain-fixes`, `.venv` is already junctioned in). Commit there with plain `git commit`, one commit per item.
- **Tests:** `.venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"`, plus `node tests/<each>.cjs`.
  All must pass; add tests for every item. Tests use temp DBs (see `tests/test_issues.py` for the patch pattern).
- **Lesson from #5 (read it):** mocked subprocess tests passed while the real Windows call failed. Item 1 needs at least
  one test that runs a REAL `godot` subprocess on a tiny temp project (skip it with a clear message if `godot` is not
  on PATH), not only mocks.
- **Lesson from #8:** follow the producer's intent, and use the example strings below. Where data is missing, show a
  labeled fallback, never a bare "unknown".

## 1. Godot smoke must not false-green
Today `orch.py smoke` on a Godot repo runs `godot --headless --path . --quit` in a fresh `_smoke` worktree and passes
on exit code 0, even when scripts fail to parse. That happens because a fresh checkout never ran the editor import, so
`class_name` globals are missing (Codex found this on 003-big-city).
- For Godot projects, run the import first, `godot --headless --editor --path . --quit` (or `--import` if supported),
  then the run command. Respect the existing VR rule: headless or XR-disabled only.
- FAIL when the output contains `SCRIPT ERROR`, `Parse Error`, `Failed to load script` or `ERROR: ` lines that
  reference `res://`, even with exit code 0. Put the first 3 such lines in SMOKE.json `output_tail`, and set
  `"false_green_guard": true`.
- Example SMOKE.json note: `"note": "exit 0 but 3 script errors after import (first: res://scripts/x.gd:12 Parse Error ...)"`.

## 2. Playtests are crisp, enforced
The producer needs every playtest as a short, expert, plain-language checklist. The template is
`C:/jbax-and-his-ai-pals/_orchestrator/briefs/PLAYTEST_TEMPLATE.md` (read it).
- `review_build(iid, "pass", ...)` must refuse unless `designs/<id>-<slug>/PLAYTEST.md` exists and:
  - has the headings `## What changed`, `## Setup`, `## Do this, and expect`, `## Pass if`, `## Fail if` and
    `## Tell me`, plus a `**Time:**` line;
  - has 3-8 numbered steps under "Do this", each containing `**Expect:**`;
  - is at most 3,500 characters.
  The refusal names exactly what is missing, e.g. `"PLAYTEST.md missing: '## Fail if'; step 2 has no **Expect:**"`.
- Update `playbooks/planner-codex/AGENTS.md`, Run order step 1 (review pass): before `ORCH review <id> pass`, write
  `PLAYTEST.md` from the template for the producer: plain words, observable expectations, no internal names. Put
  rollback and budgets in `BUILD_NOTES.md` instead.
- Dashboard initiative drawer: when the stage is `playtest`, render PLAYTEST.md first, above everything else, under
  the heading "Your playtest (~N min)", where N comes from the `**Time:**` line.

## 3. (Done by the conductor, merged to main as feat/forecast-issues.) Don't redo it.
Issues now flow through `queue_from_snapshot(..., issues=...)`, the forecast has an `issue` work type (max 1 per
run), and `overview.js` labels it. Item 6's planned runs should interleave with these entries in the same timeline.

## 4. Stale deep dossiers get refreshed
A frontier dossier (`_Author:` line, `orch.frontier_author`) goes stale as the project moves on.
- Stale means: the project is `high` or `medium` priority, and the repo has >= 10 commits since the dossier was
  written (use the DOSSIER.md mtime), or >= 1 commit and the dossier is older than 21 days.
- Add `dossiers_to_refresh` (at most 1 entry) to the planner queue, and a Run order step after Issues in the Codex
  playbook: re-run `briefs/seed-codex.md` for that repo. Pulse badge on stale projects: `dossier stale (12 commits since)`.

## 5. Claude quota says how old it is
Claude's 5h and weekly numbers come only from chat snapshots (`quota-snapshot`). Wherever the dashboard shows them,
append the age, e.g. `49% left · recorded 2 h ago from chat`. Past 3 hours, mark it stale: `(stale: open a chat to refresh)`.

## 6. Planned Codex/Claude work is visible before it starts
Producer: "the dashboard still makes it seem like gemma is doing all of the upcoming work, so i do need a better way
to visualize our planned work we've defined for codex and claude". Today the timeline knows only cron timers, plus
`dispatch start/end` records once a chat-launched run begins. The conductor schedules runs hours ahead (see
`logs/*.sh`), and none of them show until they start.
- Add `orch.py dispatch plan --lane <lane> --run <id> --label "..." [--project p] [--not-before <iso>] [--after "<text>"]`
  (event `dispatch_plan`) and `dispatch cancel --lane --run`. A later `dispatch start` or `end` with the same run id
  replaces the plan. Plans older than 24h without a start are dropped from the view.
- `overview.py`: `lane['planned']` (sorted by not-before), and merge planned runs into the forecast timeline as
  `work_type: "planned"`, so "Next expected update" and its THEN list interleave them with cron runs by time.
  A plan with only `--after` shows without a clock time: "queued after the Claude judgment pass".
- `overview.js`:
  - Agents Now for an idle lane with plans: `Codex: next: solve 007 issue (planned from chat) in 2 hrs 10 min`.
  - Upcoming entries: `Claude: judgment pass on 11 repos, planned from chat, ~22:33`.
  - Give planned rows a "planned" pill, so they read differently from cron estimates.
- Update `briefs/seed_codex.sh`, `judge_claude.sh` and `solve_issues.sh` so each repo's run is registered with
  `dispatch plan` when a wave is queued (same run id as its later `dispatch start`), and add a line to the README's Handy CLI.
- Tests: plan → start replaces it; cancel removes it; expiry; ordering against cron entries; `--after` without a time.

## Finish
Run every test, then write `BUILD_NOTES.md` in the worktree root listing per item: what changed, tests added, and
anything you could not verify. Then `ORCH log "strain-fixes ready for conductor review on feat/strain-fixes"`. Stop.
