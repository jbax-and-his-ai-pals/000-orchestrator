# _orchestrator

Local-first portfolio orchestrator. Three OpenClaw agents (local Gemma, Claude, and Codex, all on subscriptions
with zero API spend) feed a 4-gate pipeline. You drive it from a dashboard at http://localhost:8420.

```
spark ─► hld_draft ─► hld_review ─► lld_draft ─► lld_review ─► building ─► playtest ─► done
 (Claude pitches)  (Claude HLD)   YOU ✓      (Codex LLD+plan)   YOU ✓    (Gemma/Codex/Claude   YOU ✓
   YOU ✓                                                                  on feat/<slug>,
                                                                          Codex reviews)
```

Any card, any stage: **Approve / Advance**, **Request Revision** (feedback goes to the agents), or
**Reject / Kill** (logs to `state/TASTE_PROFILE.md` and deletes the feat branch and worktree).

## Layout

| Path | What |
| :-- | :-- |
| `scripts/orch.py` | The only writer of state. Agents and the dashboard both call it. Holds the main-branch guard and the Gemma contract. |
| `state/orchestrator.db` | SQLite (`projects`, `initiatives`, `events`). `PORTFOLIO_STATE.json` is rewritten after every change. |
| `state/TASTE_PROFILE.md` | Your creative philosophy, plus an auto-appended rejection log. Every agent reads it. |
| `GEMMA_CAPABILITIES.md` | What local Gemma may and may not do, and when work escalates to a frontier model. |
| `dossiers/<repo>/` | `SCAN.json` and `SMOKE.json` (deterministic), `DOSSIER.md` (Gemma), `AUDIT_NOTES.md` (migrated) |
| `designs/<id>-<slug>/` | `PITCH.md`, `HLD.md`, `LLD.md`, `REVISIONS.md`, `IDE_HANDOFF.md` |
| `worktrees/<repo>/<slug>/` | `feat/<slug>` checkouts. Your own checkouts are never switched or edited. |
| `agents/<name>/` | OpenClaw workspaces: `AGENTS.md` playbook, plus an `orch.cmd` pre-tagged with the agent's identity |
| `dashboard/` | FastAPI + vanilla JS. `serve.cmd` starts it. |
| `config.json` | Dashboard metrics, webhooks (off by default), model ids |
| `archive/`, `research/` | Loose folders moved out of the container root (nothing deleted) |

## Start the dashboard

```
C:\jbax-and-his-ai-pals\_orchestrator\dashboard\serve.cmd
```

Then open http://localhost:8420. It binds to 127.0.0.1 only.

**Autostart:** a shortcut named `Portfolio Orchestrator Dashboard` in your Windows Startup folder (`shell:startup`) runs
`dashboard\serve-hidden.vbs` at login. It has no console window and logs to `logs\dashboard.log`. To stop autostart,
delete that shortcut. To stop the running server, end the `python.exe` process listening on port 8420.

## Schedules (all created DISABLED, all `--session isolated`)

| Job | Agent / model | Schedule (local time) |
| :-- | :-- | :-- |
| `orch:scout-gemma` | scout-gemma / `ollama/gemma4:12b` | every 30m |
| `orch:architect-claude` | architect-claude / `anthropic/claude-sonnet-5-5` | 01:00, 09:00, 17:00 |
| `orch:architect-claude-opus` | architect-claude / `anthropic/claude-opus-5-5` | 09:30, high-complexity HLDs only; exits at once if none |
| `orch:planner-codex` | planner-codex / `openai/gpt-6.1-sol` | 04:00, 12:00, 20:00 |

```
openclaw cron list --all
openclaw cron enable <id>     # go live, one job at a time
openclaw cron disable <id>
```

OpenClaw has no `cron pause`. "Paused" here means created with `--disabled`.

## Working cards from chat (Claude desktop, Codex)

Open a chat in `C:\jbax-and-his-ai-pals`. Claude reads `CLAUDE.md` and Codex reads `AGENTS.md`; both explain the
workflow. In Claude, `/desk` shows the inbox. The loop:

1. `orch.py --as claude-desktop inbox --md` lists what awaits you, what's in flight, and what's claimed.
2. `orch.py --as claude-desktop claim <id>`: scheduled agents skip the card and their writes to it are refused.
   The claim lasts 24h; claim again to renew.
3. Work it in chat. Results go back through `attach-hld`, `attach-lld`, `commit`, and so on.
4. `orch.py --as claude-desktop release <id>` hands the card back to the agents. `reject` also clears the claim.

The dashboard shows claims (💬) and has **Claim for chat** and **Release** buttons on every card.

## Dry-run before enabling schedules (single repo)

Each command uses a fresh session key, so no context carries over between runs.

```
openclaw agent --agent scout-gemma --session-key agent:scout-gemma:dryrun-1 --message "Dry run: do Job A from AGENTS.md for project 002-wasteball only (skip Step 1), then stop."
openclaw agent --agent architect-claude --model anthropic/claude-sonnet-5-5 --session-key agent:architect-claude:dryrun-1 --message "Dry run, single repo: read TASTE_PROFILE.md and dossiers/002-wasteball/DOSSIER.md, pitch at most 2 sparks for 002-wasteball via orch.cmd add-spark, no HLDs, no other projects, then stop."
```

Approve one spark on the dashboard; it moves to `hld_draft`. Then:

```
openclaw agent --agent architect-claude --model anthropic/claude-sonnet-5-5 --session-key agent:architect-claude:dryrun-2 --message "Dry run: draft and attach the HLD for initiative #<id> only (AGENTS.md step 1), then stop."
```

Approve the HLD; it moves to `lld_draft`. Then:

```
openclaw agent --agent planner-codex --model openai/gpt-6.1-sol --session-key agent:planner-codex:dryrun-1 --message "Dry run: write LLD.md and plan.json for initiative #<id> only, attach both, then stop."
```

Approve the LLD; it moves to `building`, and a `feat/` worktree is created. Then run one real scout cycle to execute any
Gemma subtasks: `openclaw cron run <scout-job-id> --wait`.

## Handy CLI

```
_orchestrator\.venv\Scripts\python.exe _orchestrator\scripts\orch.py --help
orch.py projects | initiatives | show <id> | queue scout|architect|planner
orch.py scan <repo> | smoke <repo>
orch.py sync-repos [--dry-run]      # clone org repos missing locally; never touches existing ones
```
