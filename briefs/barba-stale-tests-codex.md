# Brief: fix Barba's four stale town/shout/dialogue tests (019-z2-barba, Codex)

Work ONLY in `C:/jbax-and-his-ai-pals/_orchestrator/worktrees/019-z2-barba/stale-tests` (branch `fix/stale-town-tests`,
based on `9793c6c`). Never touch the producer's checkout `C:/jbax-and-his-ai-pals/019-z2-barba` or other worktrees
(another Codex run is working in `.../upstab`). `roms/` and `.tools/` are junctions: read only.
Read `AGENTS.md` first (hard rules; Lua strings never contain a literal newline; run scenarios one at a time).

## Problem

These scenarios fail on the current build and also failed identically before recent changes. They assert behavior
from earlier designs (the retired top-HUD subtitle shouts, old dialogue delay values, older protection cases):

| Scenario | Failing assertions now |
| --- | ---: |
| `tests/town_safety.lua` | 8 (dialogue protection cases) |
| `tests/shouts.lua` | 2 (subtitle/PPU and movement) |
| `tests/shout_queue.lua` | 7 (old subtitle queue/erasure) |
| `tests/dialogue_speed.lua` | 3 (delay/accumulator) |

Current intended behavior is documented in `docs/TOWNS.md` and `docs/STATUS.md` (shouts are floating sprite words that
follow the villager, `SHOUT_COOLDOWN = $78`; top-HUD subtitle text removed; held-Up dialogue speed; all outdoor `$13..$20`
villagers can panic/burn; indoor rooms and `$0B..$12` wise men/healers are protected).

## Task

For each failing assertion, decide from the docs and the source (`src/town*.inc`, `src/shouts.inc`,
`src/shout_layout.inc`) whether the test is stale or the game is wrong:

- **Stale test:** rewrite the assertion to check the current intended behavior (don't just delete it). If a whole
  scenario only covers a retired feature (e.g. the HUD subtitle queue) and `shout_follow.lua` already covers its
  replacement, retire it (delete, and remove it from AGENTS.md's suite list), and say so.
- **Real game bug:** do NOT change game code. List it in the report with evidence (scenario, frame, RAM values).

Don't change `src/`, `tools/build.py` or assets. Test files and docs only.

## Acceptance

- All four scenarios pass (or are retired with a reason), run one at a time; `python -m unittest discover -s tests` passes.
- Re-run the rest of AGENTS.md's suite list one at a time: still all PASS.
- Update AGENTS.md: remove the "Known stale" note for whatever is fixed.
- Commit on `fix/stale-town-tests` (end the message with `Co-Authored-By: Codex <noreply@openai.com>`). Don't merge or
  push. Never advance gates. Write `build/STALE-TESTS-REPORT.md` in the worktree, with a per-assertion table
  (old check → new check, or "game bug"), and use it as your final message. Then stop.
