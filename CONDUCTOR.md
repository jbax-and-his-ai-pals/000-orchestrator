# Conductor board: open threads between chats

Every chat with the conductor starts fresh. This file holds what a new chat needs that the orchestrator DB doesn't:
background runs, environment quirks, unfinished conversations. Keep it under ~40 lines. Delete threads when they close.
Card state lives in `orch.py inbox --md`; do not copy it here.

_Last updated: 2026-11-13 20:00 PT_

**Chat start:** read this file and `inbox --md`, nothing more, until the producer asks for something.

## Running now
- #6 sent back to lld_draft at 19:59 to rebase on #8 (scope in its REVISIONS.md); planner-codex's hourly cron picks it
  up, so expect it at lld_review in roughly an hour. Then the producer reviews the LLD. #7 closed as absorbed into #8.
- #5 and #8 (dashboard MVP) shipped at 19:58 (main d5f4ffb, pushed). Playbooks are
  installed (Gemma's never-idle fallback is live), the spotlight is ended, and the dashboard on :8420 runs the new build.

## Roadmap (producer, 2026-11-13)
1. ~~#8 dashboard MVP~~ (shipped). 2. Harden the orchestrator to use every resource fully, on every project.
3. AI-analyzed per-project metadata, kept current (spark #10). End state: the producer steers from a forward-looking view.
- **Next chat: project seeding.** Codex writes deep dossiers (reads the repo, runs it headless); Claude Sonnet writes player
  experience, scores, bottleneck and next milestone from the dossier; Gemma keeps facts fresh. Pilot 002-wasteball,
  003-big-city and 015-mmc6-nes first to calibrate prompts and cost. Coverage now: 11/20 dossiers, 5/20 player experience.

## Producer decisions in force
- Dispatch within the 5h windows; weekly quota is information only ("if we hit weekly quota, that's unfortunate").
  Revisit now that the MVP shipped. Gemma should always have work.
- Working mode: Codex for logic and volume; visual polish in chat ("if you'd judge it by looking, iterate here").
- Non-orchestrator (game) work takes a back seat until the orchestrator milestones are done (producer, 2026-11-13).
  Don't dispatch frontier agents at game cards; Gemma's background dossier and smoke work continues.

## Waiting on the producer
- Back seat (game work): #2 playtest, #4 HLD review, spark #3. Orchestrator sparks: #9 (chat inside the orchestrator), #10 (seeding).
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
- Static assets carry `?v=` cache-busters in `dashboard/static/index.html`; bump them when editing JS or CSS.
