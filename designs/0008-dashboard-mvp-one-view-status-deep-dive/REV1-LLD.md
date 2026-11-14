# Revision 1 implementation contract

- Preserve subtasks 1–9 byte-equivalent as parsed JSON, append 10–13; verified after attach-plan.
- scripts/orch.py queue_from_snapshot is the shared pure dispatch boundary: actual priorities, exclusions, stage precedence, Gemma fit and dependency rules. queue retains filesystem enrichment only outside it.
- scripts/forecast.py copies inputs, injects UTC clock, simulates defined work to the next producer checkpoint, never invents future plans or approves gates. A separate conditional model assumes currently waiting gates approved now.
- Observed next runs seed lanes; retained every/cron schedules supply future checks; missing/stale/paused/exhausted observations remain blockers. One run drains eligible work as worker playbooks permit.
- Duration tiers require >=3 valid samples: actor/type, actor/all types, all actors/type, fixed labeled priors. Priors in minutes: build 20, LLD 25, HLD 30, review 10, dossier 1, spark rework 10. Never treat gate dwell as execution.
- Bounds: 24h, 2000 simulation events, 5000 subtasks, 16 cached models/30s. Explicit truncation. Rollups remain deduplicated, computed before pagination.
- GET what-if priority is cloned/read-only; existing guarded priority writes, lanes and gates remain unchanged. Forecast ETAs label next checkpoint, not final shipment.
- Overview derives owners, formats local day + relative time, maps raw labels, and uses under/on/over pace with 60min freshness and Claude snapshot hint.
- Tests cover pure forecasts/rollups, read-only APIs, HTML escaping/rendering and existing regressions. Live GETs on owned :8423 only; no main/push/gate operations.
- Rollback: revert feature commits; no persisted forecast schema or live scheduler changes to undo.
