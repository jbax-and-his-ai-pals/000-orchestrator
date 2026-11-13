# Utilization tab — delivery / producer playtest

Automated implementation checks are recorded by initiative #5. **Manual checks below are PENDING.** No dashboard, hardware sampler, real OpenClaw command, or live quota snapshot was run by this build. The running :8420 dashboard and main checkout code were not changed.

## Producer-only launch (Git Bash, feature worktree)

**Warning: this command deliberately uses LIVE orchestrator state.** Startup initializes additive metrics schema and starts local GPU/Ollama/OpenAI sampling. It writes metrics plus the utilization_sampler_lease_v1 setting to the shared DB. It does not update the live code or restart :8420. Only run after reviewing this branch. OpenAI status is attempted at most once per 600 seconds across lease-aware instances. Never seed fake readings in live state.

```bash
cd C:/jbax-and-his-ai-pals/_orchestrator/worktrees/000-orchestrator/utilization-tab-gpu-vram-and-quota-over
ORCH_HOME=C:/jbax-and-his-ai-pals/_orchestrator C:/jbax-and-his-ai-pals/_orchestrator/.venv/Scripts/python.exe -m uvicorn app:app --app-dir dashboard --host 127.0.0.1 --port 8421
```

Browse http://127.0.0.1:8421 and select Utilization. Do not start/stop/restart :8420. Close this foreground :8421 process with Ctrl-C when finished.

## Pending manual checks

- [ ] Five source cards: GPU/VRAM/temperature/power, loaded Ollama model names/expiry, OpenAI windows, explicitly manual Claude snapshots, Gemini logged actions/error proxy. Missing tools/unknown/stale data must not imply zero usage or full quota.
- [ ] Four SVG charts only; GPU left axis % and right axis GiB; OpenAI remaining windows; Claude unconnected original dots; hourly agent event proxy with lane legend. Verify gaps, singletons and empty state visually.
- [ ] 24h / 7d / 14d; rapid range changes; offline/network failure preserves last-good range with stale warning. Reconnect recovers. No NaN/Infinity SVG coordinates.
- [ ] Enter/leave Utilization and background/foreground browser: independent 60s network poll only while visible. Local 1Hz age/reset text must not redraw charts. Inspect developer-tools network/timers.
- [ ] Responsive at 360 / 768 / 1440 px; chart axis/legend readability, keyboard range selection and source strings wrapping. Check screen-reader chart names and summaries.
- [ ] Console and CSP show no new errors. No CDN/inline script/eval needed. Existing Pulse, Triage, Activity, Taste, drawers, review controls and ordinary refresh retain behavior.
- [ ] Lease: inspect utilization_sampler_lease_v1 in settings read-only. With a second intentionally launched lease-aware feature instance on a spare port, verify one owner and persistent attempts; OpenAI attempts >=600s apart after timeout/restart/takeover. Stop only your feature instances. Old :8420 code has no sampler until deployment.

## Automated budget evidence

Temporary 14-day fixture: 120,960 resource rows plus 3,000 Claude dots. Observed response 101,865 bytes, query ~82ms, SQLite DB 19,070,976 bytes on this machine (informational, not a timing gate). Functional tests enforce regular series <=336, Claude <=1000 original dots/window and payload <500KiB. Full resource mean aggregation and last quota buckets do not materialize raw samples into response RAM. Retention deletes <=5000 expired metrics per hourly attempt only. Ollama response capped at 1MiB. No additional production dependency.

UI redraw <16ms and transient RAM <8MiB / sampler RAM <16MiB are **not profiled yet**; producer browser/process profile remains pending. Static deterministic tests cover chart transforms, gaps/zero/empty/singleton cases, hostile strings, range races, timers and visibility teardown; Python tests use only temporary DBs and mocked tools/HTTP/lifespans.

## Rollback

Stop only feature processes you launched. Producer controls deployment/revert; executor never modifies main. Leave additive metrics table/indexes and lease settings in place: older code ignores them. Do not delete/restore the live DB, prune events, change WAL mode, or restart :8420 for rollback.
