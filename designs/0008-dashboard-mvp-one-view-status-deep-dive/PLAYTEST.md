# Dashboard revision 1 — producer playtest
1. Start with active tasks: routed owner, task age, n/m progress and ETA appear on every row.
2. Check ETAs: duration says history median or labeled default; overdue work never slides its deadline.
3. Top rollups show open/in-flight/waiting/blocked/queued counts and project next-checkpoint ETAs; filter a project.
4. Next hours shows observed scheduled work; paused, stale, spotlight and chat ownership remain explicit blockers.
5. Open project/initiative priority controls → If prioritized? Compare current ETA, alternative and delayed cards (GET-only).
6. Pending producer gates show waiting time and conditional if-approved-now ETAs; no gates are auto-approved.
7. Quota pace reads under/on/over pace, reset day + local time, 60-minute staleness and Claude snapshot hint.
Evidence: full Python/Node suites, five real read-only probes and ten live GETs on owned :8423 passed; server stopped.
Unverified: browser policy blocks loopback navigation, so visual layout, keyboard/back/reload and draft persistence need producer checks.
