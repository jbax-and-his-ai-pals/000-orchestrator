# Conductor board: open threads between chats

Every chat with the conductor starts fresh. This file holds what a new chat needs that the orchestrator DB doesn't:
background runs, environment quirks, unfinished conversations. Keep it under ~40 lines. Delete threads when they close.
Card state lives in `orch.py inbox --md`; do not copy it here.

_Last updated: 2026-11-13 21:40 PT_

**Chat start:** read this file and `inbox --md`, nothing more, until the producer asks for something.

## Running now
- **Overnight, hands-free (all detached; they survive chat close):** 22:33 Claude judgment pass on 11 repos (low
  skipped) → ~23:00 Claude solves 002, 014, 017, 019 + Opus HLD for #11 → 23:47 Codex and Claude on 000's dossier →
  ~00:00 Codex solves 007, 008, 012, 015 → Codex builds strain fixes (if 35% or more left). Scheduled: Claude Sonnet
  01:00, Codex 04:00, Gemma every 30 min. `logs/overnight_watchdog.sh` restarts the gateway or :8420 if they go down,
  and writes **`logs/OVERNIGHT_SUMMARY.md` at 07:00**.
- **Morning chat opener:** "Read logs/OVERNIGHT_SUMMARY.md, then walk me through what needs me." In that chat:
  check the issue sparks on the Triage Board, present the #11 HLD for review, and review `feat/strain-fixes` against
  its brief (tests, then show the producer before merging).
- #6 sent back to lld_draft at 19:59 to rebase on #8 (scope in its REVISIONS.md); planner-codex's hourly cron picks it
  up. It must rebase on main (priority view 4f10483, dispatch visibility 40be8be touched overview.js/app.js).
- **Seeding:** Codex deep dossiers done for all 19 game repos; Claude judgment pass done for 002 (pilot, excellent).
  Low-priority repos skip the Claude pass (Codex dossier only). `logs/seed_finish.sh` is running in the background (log `logs/seed_finish.log`, per repo `logs/judge-claude-<repo>.log`).
  It waits for 22:33 PT, runs the Claude pass on the other 18 in waves of 4, waits for 23:47 PT, then runs Codex and
  Claude on 000-orchestrator. If the chat that started it closed, check the logs; the script dies with its session.
  Then: spot-check the judged dossiers, check `ORCH issues`, and ask the producer about `issues-autosolve on`.
  Gemma backlog (11 docs tasks, 6 ready) is in `designs/0011-*/GEMMA_BACKLOG.md` for spark #11.
- **Bottleneck issues** merged 21:05 (aaa6cb4); the orchestrator's issue is dismissed. Autosolve is ON (producer,
  21:15). `logs/solve_tonight.sh` runs in the background: after the Claude judgment waves, Claude solves 002, 014,
  017, 019; after 000's dossier (~midnight), Codex solves 007, 008, 012, 015 (the launcher skips the low repos listed).
  Waves are skipped if Codex is under 30%. 009, 010, 011, 013, 016 are left for the producer (playtest or
  hardware). Logs: `logs/solve_issues.log`, `logs/solve-<lane>-<repo>.log`. Next chat: check the resulting sparks on
  the Triage Board (`ORCH issues --status proposed`). Known gap: forecast doesn't show issue work.
- **Strain fixes:** all of tonight's scripts now run DETACHED (they survive the chat): `seed_finish`, `solve_tonight`,
  and `strain_build`, which starts Codex on `briefs/strain-fixes-codex.md` in `worktrees/000-orchestrator/strain-fixes`
  after the issue batches, if Codex has 35% or more left. It covers: no Godot smoke false greens, PLAYTEST.md format
  enforced at review pass, issue work shown in the forecast, stale-dossier refresh, Claude quota age, and (item 6)
  planned Codex/Claude runs visible on the dashboard before they start. Next chat:
  review that branch against the brief, run the tests, and show the producer before merging. Claude's scheduled
  Sonnet runs are ON (01:00, 09:00, 17:00) as of 21:35.
- **#11 Gemma stabs** is in hld_draft (producer: "included in the next wave"). `logs/hld11.sh` (detached) runs the
  Opus HLD after the judgment waves. Next: producer reviews the HLD; on approval, Codex's next run writes the LLD.
- Codex 5h at ~10% left at 20:35 (resets 23:44 PT): no Codex dispatches until then.

## Roadmap (producer, 2026-11-13)
1. ~~#8 dashboard MVP~~ (shipped). 2. Harden the orchestrator to use every resource fully, on every project.
3. AI-analyzed per-project metadata, kept current (spark #10). End state: the producer steers from a forward-looking view.
- Milestone 3 groundwork: seeding gave every repo a deep dossier (see Running now). Spark #11 (Gemma stabs) filed.

## Producer decisions in force
- Dispatch within the 5h windows; weekly is information only. Gemma should always have work.
- Working mode: Codex for logic and volume; visual polish in chat ("if you'd judge it by looking, iterate here").
- Non-orchestrator (game) work takes a back seat until the orchestrator milestones are done (producer, 2026-11-13).
  Don't dispatch frontier agents at game cards; Gemma's background dossier and smoke work continues.

- Project priority (producer, 2026-11-13; they adjust it on the Pulse): high = 000 (until the producer agrees it's in a good place), 007, 009, 014, 017, 019; medium =
  002, 008, 010, 011, 012, 013, 015; low = 001, 003, 004, 005, 006, 016, 018. **Low = ideas only:** sparks and
  Gemma facts are fine, but no frontier spend (issues parked, no hunts or judgment passes; the launchers skip them).
  A low card moves only if the producer advances it. Check priority before any chat dispatch.
- Antigravity is parked as a route for now (producer, 2026-11-13): send its work to Codex/Claude instead.

## Waiting on the producer
- Back seat (game work): #2 playtest, #4 HLD review, spark #3. Orchestrator sparks: #9 (chat inside the orchestrator), #10 (seeding), #11 (Gemma stabs).
- (done 22:07) Tailscale Serve: dashboard at https://cpu.tail369b7c.ts.net (tailnet only). Off: `tailscale serve --https=443 off`.

## Quirks
- The OpenClaw gateway crashed once on 2026-11-13; both agents and crons stop when it does. Check with
  `openclaw gateway status`, fix with `openclaw daemon restart`.
- Launch `openclaw` detached through `openclaw.cmd` with a file-based brief; inline multi-line messages break on quoting.
- `orch.py advance` on a 000-orchestrator card restarts :8420 in a detached process that dies when run from Claude's Bash
  tool. After shipping from chat, restart it by hand: stop the :8420 listener, then run `wscript dashboard/serve-hidden.vbs`.
- Shipping requires a clean `_orchestrator` main checkout: commit CONDUCTOR.md and MODEL_NOTES.md edits first.
- Every chat is `--as claude-desktop`, so claims can't keep two simultaneous chats apart. Run one chat at a time.
- Codex refuses to advance gates (its playbook says so): the conductor or the producer advances them.
- Worktree commits: the pre-commit hook runs `.venv/Scripts/python`, so junction the main `.venv` into the worktree first.
- Static assets carry `?v=` cache-busters in `dashboard/static/index.html`; bump them when editing JS or CSS.
- Worktree `.venv` junction: `mklink` fails from Git Bash; use PowerShell `New-Item -ItemType Junction`.
- Dashboard playtest copies: an old copy may hold :8421. Serve a worktree build on a free port with `ORCH_HOME` pointed at
  a scratch copy of `state/`, `dossiers/` and `config.json`, so testing never writes live state.
- `ORCH smoke` false-greens on Godot: exit 0 despite parse errors in a fresh checkout that never ran the editor import
  (found by Codex on 003). Treat a Godot smoke PASS as unproven until fixed; the fix is a candidate card.
- `logs/` is gitignored: reusable briefs and launchers go in `briefs/`, never only in `logs/`.
- Bash `run_in_background` jobs die with the chat, and TaskStop can leave orphaned child bash processes running.
  Launch long work with `briefs/detach.vbs`, and check `Get-CimInstance Win32_Process` for duplicates.
