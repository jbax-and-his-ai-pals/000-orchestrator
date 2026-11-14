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

## 3. Issue work shows in the forecast
`overview.py` and `forecast.py` don't know about `issues_to_solve` (the live `orch.queue` adds it after
`queue_from_snapshot`). When a lane's next scheduled run would reach issues (nothing higher in its queue, and
autosolve on), add a forecast timeline entry, `work_type: "issue"`, e.g. "Codex solves issue 7 for
007-twitch-chatbot-coordinator", at that run's start, so "Next expected update" and Agents Now show it.
`describe()` in `overview.js` needs the label. Keep `queue_from_snapshot` pure: pass the open issues in as data.

## 4. Stale deep dossiers get refreshed
A frontier dossier (`_Author:` line, `orch.frontier_author`) goes stale as the project moves on.
- Stale means: the project is `high` or `medium` priority, and the repo has >= 10 commits since the dossier was
  written (use the DOSSIER.md mtime), or >= 1 commit and the dossier is older than 21 days.
- Add `dossiers_to_refresh` (at most 1 entry) to the planner queue, and a Run order step after Issues in the Codex
  playbook: re-run `briefs/seed-codex.md` for that repo. Pulse badge on stale projects: `dossier stale (12 commits since)`.

## 5. Claude quota says how old it is
Claude's 5h and weekly numbers come only from chat snapshots (`quota-snapshot`). Wherever the dashboard shows them,
append the age, e.g. `49% left · recorded 2 h ago from chat`. Past 3 hours, mark it stale: `(stale: open a chat to refresh)`.

## Finish
Run every test, then write `BUILD_NOTES.md` in the worktree root listing per item: what changed, tests added, and
anything you could not verify. Then `ORCH log "strain-fixes ready for conductor review on feat/strain-fixes"`. Stop.
