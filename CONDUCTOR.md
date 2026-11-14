# Conductor board: open threads between chats

Every chat with the conductor starts fresh. This file holds what a new chat needs that the orchestrator DB doesn't:
background runs, environment quirks, unfinished conversations. Keep it under ~40 lines. Delete threads when they close.
Card state lives in `orch.py inbox --md`; do not copy it here.

_Last updated: 2026-11-13 17:40 PT_

**Chat start:** read this file and `inbox --md`, nothing more, until the producer asks for something.

## Running now
- **#8 focus session** (claimed by claude-desktop): revision 1 landed at 19:04 (13/13 subtasks, review passed). The
  rev1b items are done in chat (commit 1e2e214): the next-update panel shows duration plus plain words, and Gemma is
  never idle (falls back to the stalest dossier outside the spotlight). Polish round 2 (832cd83): one-page Overview,
  Work and Ideas tabs, Activity ETAs and a styled feed, a Pulse column slider, Utilization emphasis. Rounds 3-6 (through
  1e300fd): Attention tab, a Work tab grouped by when, a project modal with a Roadmap tab, quota pace in the Utilization cards.
  The producer said "we're in really good shape". Next: playtest signoff and merge, then project seeding (see spark #10).
  Preview: launch config `playtest-8` (:8422).
  Live Gemma keeps the old behavior until #8 merges and `sync_playbooks.py --install` runs.
  Mode: Codex for logic and volume, polish in chat ("if you'd judge it by looking, iterate here").

## Roadmap (producer, 2026-11-13)
1. #8 dashboard MVP that meets all the producer's criteria. 2. Harden the orchestrator to use every resource fully, on
every project. 3. AI-analyzed per-project metadata, kept current. End state: the producer steers from a forward-looking view.

## Producer decisions in force
- Until the MVP ships: dispatch within the 5h windows only and ignore weekly quota pacing ("if we hit weekly quota,
  that's unfortunate"). Gemma should always have work.

## Waiting on the producer
- #8 playtest signoff after revision 1. The producer's priorities: active tasks, task and rollup ETAs, rollups, the overview, quota pace.
- Spark #9 (conductor chat inside the orchestrator, per-chat model routing): the producer's long-term goal, to come after #8.
- #5 playtest: approve on :8420 (ships via merge-on-approve). #8 merges #5's branch into its own, so approve #5 first.
  The inbox still shows an old "revision remains unmet" note, but commit e9f570a fixed that revision (real .cmd test).
- #2 playtest (`designs/0002-*/playtest.cmd`). #4 HLD review. Sparks #3 and #6 (#7 is folded into #8).
- Tailscale: the producer enables Serve in the admin console, then run `tailscale serve --bg 8420`.

## Quirks
- The OpenClaw gateway crashed once on 2026-11-13; both agents and crons stop when it does. Check with
  `openclaw gateway status`, fix with `openclaw daemon restart`.
- Launch `openclaw` detached through `openclaw.cmd` with a file-based brief; inline multi-line messages break on quoting.
- `_orchestrator` commits b501e01 and 98ce6f7 (the VR testing rule) are local only, not pushed.
- Don't `tail` `logs/mvp_pipeline.log`: it dumps the card's whole plan JSON. Use `inbox --md` or `codex-mvp.log`.
- Every chat is `--as claude-desktop`, so claims can't keep two simultaneous chats apart. Run one chat at a time.
- Codex refuses to advance gates (its playbook says so): the conductor or the producer advances them.
