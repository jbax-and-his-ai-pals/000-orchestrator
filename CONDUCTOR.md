# Conductor board: open threads between chats

Every chat with the conductor starts fresh. This file holds what a new chat needs that the orchestrator DB doesn't:
background runs, environment quirks, unfinished conversations. Keep it under ~40 lines. Delete threads when they close.
Card state lives in `orch.py inbox --md`; do not copy it here.

_Last updated: 2026-11-13 17:10 PT_

## Running now
- **#8 Dashboard MVP pipeline**: `logs/mvp_pipeline.sh`, run detached; log at `logs/mvp_pipeline.log`, Codex output at `logs/codex-mvp.log`.
  It runs Codex phases HLD, LLD and BUILD, advances the two gates on the producer's 2026-11-13 directive, and stops at playtest.
  Brief: `logs/codex-mvp-msg.txt` (scope also covers #7 and the pacing part of #6).
- **Spotlight**: 000-orchestrator, forced, indefinite. End it with `spotlight --end` once #8 ships.

## Waiting on the producer
- #8 playtest signoff (when it lands). Before signoff, the conductor checks the real running app: mocked tests missed a bug in #5.
- #5 playtest: approve on :8420 (ships via merge-on-approve). #8 merges #5's branch into its own, so approve #5 first.
- #2 playtest (`designs/0002-*/playtest.cmd`). #4 HLD review. Sparks #3 and #6 (#7 is folded into #8).
- Tailscale: the producer enables Serve in the admin console, then run `tailscale serve --bg 8420`.

## Quirks
- The OpenClaw gateway crashed once on 2026-11-13; both agents and crons stop when it does. Check with
  `openclaw gateway status`, fix with `openclaw daemon restart`.
- Launch `openclaw` detached through `openclaw.cmd` with a file-based brief; inline multi-line messages break on quoting.
- `_orchestrator` commits b501e01 and 98ce6f7 (the VR testing rule) are local only, not pushed.
- Codex refuses to advance gates (its playbook says so): the conductor or the producer advances them.
