# Brief: fix weak spots in Barba checkpoint sets (019-z2-barba, Codex)

Continue in `C:/jbax-and-his-ai-pals/_orchestrator/worktrees/019-z2-barba/checkpoints` on branch `feat/checkpoint-sets`
(your previous commit `8e559be`). Same rules as `briefs/barba-checkpoint-sets-codex.md` and `AGENTS.md`. Never touch the
producer's checkout or other worktrees. Don't change game code (`src/`, `tools/build.py`, assets).

The conductor reviewed every screenshot (you couldn't). Fix these:

1. **Duplicates:** `endgame` "Great Palace low tunnel" (room 54), `endgame` "Before Dark Link" (room 54) and `movement`
   "Great Palace low ceiling" (room 54) are the same room. Keep "Before Dark Link". Replace the other two with
   **different** rooms that really have a low ceiling or tunnel: one in the Great Palace for endgame, and one anywhere
   (another palace is fine) for movement.
2. **No elevator visible:** `endgame` "Great Palace elevator" and `movement` "Palace 1 elevator shaft" show plain
   corridors. Each must start with Barba **standing on an elevator platform**, in a shaft where riding up/down is possible.
   Find elevator rooms from the area/room data in the disassembly and verify by emulator: the elevator object is
   present in RAM and Barba's Y sits on it.
3. **Bottomless pit:** add a `movement` state next to a bottomless pit (a pit that kills by falling off-screen, in a palace
   or the Great Palace), with Barba standing safely at its edge.
4. **Fill to 10 where real spots exist (optional, don't pad with near-duplicates):** endgame candidates: a second GP
   elevator or shaft, a GP mid-palace room, Thunderbird's room with the fight started. Movement candidates: a long
   elevator ride, a palace crumbling floor, another low tunnel, a palace water/lava pit. Report what you added or why not.
5. **Palette sanity:** `world` Darunia shows a purple sky and Old Kasuto a dark blue one. Load the same rooms with the
   **original ROM** (`roms/z2.nes`) through the same fixture and compare sky palette bytes. Report whether they match
   vanilla. If they don't, find out why (state/palette init) and fix the fixture, not the game.

Since you can't view PNGs, prove each new or changed state numerically: room/world bytes, the relevant object or tile
under or next to Barba (elevator object, pit columns with no floor down to the screen bottom, ceiling tiles above the
head), and Barba controllable. Keep `tools/checkpoint_sets.json`, `tests/state_pack.lua` and the docs in sync, regenerate
with `python tools/create_test_pack.py --force`, and keep all states validating. Re-run `tests/state_pack` and the unit
tests. You don't need to rerun the whole scenario suite (no game code changes), only `boot` and `gameplay` as a smoke check.

Commit on `feat/checkpoint-sets` (end with `Co-Authored-By: Codex <noreply@openai.com>`). Don't merge or push. Never
advance gates. Update `build/CHECKPOINTS-REPORT.md` (a "Fixes" section at the top: what changed per item, with the
numeric evidence) and use it as your final message. Then stop.
