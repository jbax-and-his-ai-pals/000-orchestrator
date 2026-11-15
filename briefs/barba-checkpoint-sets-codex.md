# Brief: Barba playthrough checkpoint sets (019-z2-barba, Codex)

Work ONLY in the worktree named in your dispatch message (branch `feat/checkpoint-sets`). Never touch the producer's
checkout `C:/jbax-and-his-ai-pals/019-z2-barba` or other worktrees. `roms/` and `.tools/` are junctions: read only.
Read `AGENTS.md` first (hard rules; Lua strings never contain a literal newline; run scenarios one at a time), then
`docs/TEST-PACK.md` (its "Planned: playthrough checkpoint sets" section is the producer's spec).

## Goal

Make a whole-game playtest quick. Today's F1-F10 stay as the **Core** set. Add four sets of up to ten Mesen save
states. The producer picks a set from the test launcher, and its states load into F1-F10:

1. **Palaces 1-5:** each palace's entrance and the room just before its boss (Horsehead, Helmethead, Rebonack,
   Carock, Gooma).
2. **Endgame:** Palace 6 entrance, Great Palace entrance, a Great Palace elevator and a low tunnel, Thunderbird,
   Dark Link, and the crystal-placement / ending moments that are practical to reach.
3. **Towns and world:** each town's street (Rauru, Ruto, Saria, Mido, Nabooru, Darunia, New Kasuto, Old Kasuto),
   the Death Mountain entrance, Maze Island.
4. **Tricky movement:** low ceilings, collapsing floors, water, bottomless pits, long elevator shafts, picked where the
   tall dragon (24x48 visual, native-height body) is most likely to snag.

**Progression-accurate stats (producer decision):** each checkpoint gets the levels, spells, items, techniques, keys,
crystals placed and quest flags a player would normally have at that point on the standard route. Not maxed.
Document the assumed route and each checkpoint's loadout in `docs/TEST-PACK.md`.

## How (follow the existing pattern)

- `tools/state_scenarios.lua` already builds checkpoints through normal room loading (`palace(...)`, `upgraded()`).
  Extend it per set. Only edit progression/stats/entry location; no persistent cheats.
- Keep the scene lists in sync across `tools/state_scenarios.lua`, `tools/create_test_pack.py` and
  `tests/state_pack.lua`. Every state must reload with a visible frame and survive 120 frames (as `state_pack` checks today).
- Launcher: the simplest thing for the producer, e.g. one `.cmd` per set in `play/` ("Test Barba - Palaces.cmd" ...),
  or a numbered menu in `tools/launch.ps1 -TestPack`. Core stays the default.
- Find rooms with the disassembly (`.tools/z2disassembly/src/`, `ram-map.txt`) and by emulator probes. Never commit ROM data.
- Each state's `docs/TEST-PACK.md` row says: where you are, the loadout, and what to look at (one line).

## Acceptance

- All sets generate with `python tools/create_test_pack.py --force`; `state_pack` validates every state.
- A screenshot per checkpoint in `build/` that you checked yourself: right room, Barba visible and controllable, HUD sane.
- The rest of AGENTS.md's suite still passes, run one at a time (except tests listed there as known stale).
- If a spot can't be reached reliably, leave it out and say why. Don't fake it.
- Commit on `feat/checkpoint-sets` (end the message with `Co-Authored-By: Codex <noreply@openai.com>`). Don't merge
  or push. Never advance gates. Write `build/CHECKPOINTS-REPORT.md` in the worktree (table of all checkpoints, plus
  the loadout source) as your final message. Then stop.
