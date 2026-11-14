# Conductor board: open threads between chats

Every chat with the conductor starts fresh. This file holds what a new chat needs that the orchestrator DB doesn't:
background runs, environment quirks, unfinished conversations. Keep it under ~40 lines. Delete threads when they close.
Card state lives in `orch.py inbox --md`; do not copy it here.

_Last updated: 2026-11-13 20:45 PT_

**Chat start:** read this file and `inbox --md`, nothing more, until the producer asks for something.

## Running now
- #6 sent back to lld_draft at 19:59 to rebase on #8 (scope in its REVISIONS.md); planner-codex's hourly cron picks it
  up. It must rebase on main (priority view 4f10483, dispatch visibility 40be8be touched overview.js/app.js).
- **Seeding:** Codex deep dossiers done for all 19 game repos; Claude judgment pass done for 002 (pilot, excellent).
  `logs/seed_finish.sh` is running in the background (log `logs/seed_finish.log`, per repo `logs/judge-claude-<repo>.log`).
  It waits for 22:33 PT, runs the Claude pass on the other 18 in waves of 4, waits for 23:47 PT, then runs Codex and
  Claude on 000-orchestrator. If the chat that started it closed, check the logs; the script dies with its session.
  Then: spot-check the judged dossiers, check `ORCH issues`, and ask the producer about `issues-autosolve on`.
  Gemma backlog (11 docs tasks, 6 ready) is in `designs/0011-*/GEMMA_BACKLOG.md` for spark #11.
- **Bottleneck issues** merged 21:05 (aaa6cb4); the orchestrator's issue is dismissed. Autosolve is ON (producer,
  21:15). `logs/solve_tonight.sh` runs in the background: after the Claude judgment waves, Claude solves 002, 005,
  014, 017, 019; after 000's dossier (~midnight), Codex solves 001, 003, 004, 006, then 007, 008, 012, 015, 018.
  Waves are skipped if Codex is under 30%. 009, 010, 011, 013, 016 are left for the producer (playtest or
  hardware). Logs: `logs/solve_issues.log`, `logs/solve-<lane>-<repo>.log`. Next chat: check the resulting sparks on
  the Triage Board (`ORCH issues --status proposed`). Known gap: forecast doesn't show issue work.
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

- Antigravity is parked as a route for now (producer, 2026-11-13): send its work to Codex/Claude instead.

## Waiting on the producer
- Back seat (game work): #2 playtest, #4 HLD review, spark #3. Orchestrator sparks: #9 (chat inside the orchestrator), #10 (seeding), #11 (Gemma stabs).
- Tailscale: the producer enables Serve in the admin console, then run `tailscale serve --bg 8420`.

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
