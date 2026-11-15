# Brief: Barba fixed-bank headroom (019-z2-barba, Codex)

Work ONLY in `C:/jbax-and-his-ai-pals/_orchestrator/worktrees/019-z2-barba/fixed-bank`
(branch `feat/fixed-bank-headroom`). Never touch `C:/jbax-and-his-ai-pals/019-z2-barba` (the producer's
checkout). `roms/` and `.tools/` there are junctions to the main checkout: read them, never write into them.
Read `AGENTS.md` in the worktree first; its hard rules apply (guarded `overlay.prg/put` writes with expected
original bytes, never commit ROMs/build, edit `tools/build.py` with targeted edits only).

## Problem

Fixed bank 7 is essentially full: `GATE` `$FEAA` (~8 bytes left), `TERRAIN` `$FF4C` (~3 left), `LAVA`
`$D39A` (~5 left). See `src/barba.cfg`, `build/barba.map`. Every upcoming feature (upstab fire, Lava Link
fight patterns, town consequences) needs new hooks callable from fixed-bank code or from banks other than 0.
Bank 0 (`$AA40-$BF6F`) and bank 3 (`$B803-$BF6F`) still have room.

## Goal

Make adding a new bank-0 hook cost a few fixed-bank bytes each, and reclaim fixed-bank space, without
changing game behavior.

1. Survey: list every Barba-owned fixed-bank byte (segments plus guarded patches in bank 7 in `build.py`) and
   what it does. Then find genuinely unused fixed-bank bytes in the original ROM, using the disassembly
   (`.tools/z2disassembly/src/prg7*.asm`, grep by address) to prove they are never executed or read
   (unreferenced padding/data). Report the candidates with evidence. Use only those you can prove.
2. Build a reusable far-call mechanism, e.g. a single `FarCall0` trampoline that switches to bank 0, calls the
   target from a small index/table or inline operand, restores the caller's bank (the fixed-bank caller may
   run while bank 0, 3 or others are mapped, so check how `$FFC5`/`$FFC9` and the current-bank variable work),
   and preserves flags/registers where existing gateways rely on that (`php/plp` patterns).
3. Migrate existing gateways onto it where that saves bytes, EXCEPT hot paths: `EnemyFireGateway`'s
   `EXTRA_LIVE` fast path and `TerrainBatch`'s single round-trip exist for performance. Do not add cycles to them.
4. Update `src/barba.cfg`/segments, `AGENTS.md` (free-space section), and `docs/BUILD.md` with an "adding a hook"
   recipe (cost in bytes and cycles).

## Acceptance (all required, report the numbers)

- `python tools/build.py` succeeds; `python -m unittest discover -s tests` passes.
- Every scenario in AGENTS.md's full-suite list PASSes, plus `link_boss` and `shield_enemies`, run one at a
  time. Note: some scenarios write hyphenated result files (e.g. `build/projectile-only.txt`); `boot` writes a
  state dump without a RESULT line, and an empty `build/boot-error.txt` means it passed.
- `tests/perf_volley.lua`: report idle/volley avg and peak cycles and lag frames before (baseline build of the
  branch's starting commit) and after. No increase in lag frames; peak within +100 cycles.
- Report fixed-bank free bytes before vs after, and the byte/cycle cost of one new hook.
- If you cannot prove a "free" region is unused, do not use it. Partial headroom is fine; say what's left.

Commit on `feat/fixed-bank-headroom` in the worktree with a clear message (end with
`Co-Authored-By: Codex <noreply@openai.com>`). Do not merge, push, or touch other branches. Never advance
gates. Write a short summary of results to `build/FIXED-BANK-REPORT.md` in the worktree (gitignored is fine)
and as your final message. Then stop.
