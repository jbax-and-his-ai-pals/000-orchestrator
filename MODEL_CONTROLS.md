# Dashboard model controls

Open **Models** on the dashboard, or `/#/tab/models`.

- The model's **Enabled / Disabled** switch changes its existing OpenClaw schedule. It does not launch a run immediately or stop a running process.
- **Allowed tasks** are independent switches. Changes save immediately and persist across restarts, even when the schedule is disabled.
- Turning off all task types leaves no eligible task work. Turn the model off as well to avoid scheduled idle checks.
- These controls apply to the scheduled agents. Personal sessions using `--as codex-cli` or `--as claude-desktop` remain available.
- Task controls retain existing model roles and subtask assignments; they do not move tasks to another model. Claims, focus sessions, dependencies, producer gates and Gemma's capability contract still apply.

| Model | Available task types |
| --- | --- |
| Gemma | Background maintenance, coding |
| Claude Sonnet | Planning (standard HLDs), coding, ideas, issue investigation |
| Claude Opus | Planning (high-complexity HLDs) |
| Codex | Planning (LLDs and execution plans), coding, reviews, ideas, issue investigation |
| Gemini | Read-only deep reviews |

Issue investigation also requires **issue autosolve** on the Triage Board. Proposals produced by issue investigation do not require the separate Ideas switch.

Gemma defaults to background maintenance on and coding off, preserving the producer's November 14 operating mode. Installing this feature never enables a schedule. With coding off, the scout queue skips pending implementation and continues selecting passive maintenance, avoiding a stalled scan queue.

The server validates supported task types and versions, records changes through `orch.model_tasks` / the `model-tasks` CLI, filters queues and forecasts with the same policy, and refuses new scheduled task starts/outputs when disabled. Already-started coding tasks can record completion. Model processes are not sandboxed by these switches; agents must still obey their playbooks.

Reads use cached scheduler observations. When observations are stale or unavailable, scheduler switches are disabled; task preferences remain editable. Failed/stale saves restore observed values and show an error.

## Deployment

After deploying the feature, install canonical playbooks using `python scripts/sync_playbooks.py --install`. Do not run the default export over edited canonical playbooks before that install.

Change Gemma's existing cron message to request one `orch.cmd queue scout` cycle, following its returned `task_permissions`. Remove the prior hard-coded passive-only message so the dashboard's Coding switch can take effect; the queue now enforces the passive default. Change Gemini's cron message to start with `orch.cmd queue reviewer` and deep-read only the returned project, stopping when null. Keep all existing enabled states and model IDs.

Rollback: revert the feature commit and restore Gemma's passive-only cron message. The additive `model_task_permissions` setting can remain inert in the database. Do not enable any timers as part of rollback.
