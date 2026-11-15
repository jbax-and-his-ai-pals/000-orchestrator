# Brief: Barba upward fire + rising head-butt (019-z2-barba, Codex)

Work ONLY in `C:/jbax-and-his-ai-pals/_orchestrator/worktrees/019-z2-barba/upstab` (branch `feat/upstab-fire`, based
on `262501a`). Never touch `C:/jbax-and-his-ai-pals/019-z2-barba` (the producer's checkout) or other worktrees.
`roms/` and `.tools/` are junctions to the main checkout: read them, never write into them.

Read first, in this order: `AGENTS.md` (hard rules: guarded `overlay.prg/put` writes with expected original bytes;
never commit ROMs/build; targeted edits to `tools/build.py`), then **`docs/UPSTAB-FIRE-PLAN.md` — the approved
design; implement it as written**, then `docs/BUILD.md` "adding a hook" (FarCall0) only if you need a fixed-bank hook.
The plan says everything should fit in bank 0 with no new fixed-bank hook; prefer that.

## Producer decisions (settled, do not reopen)

- Build both parts: **A** upward breath (Up+B while airborne fires the five-shot volley upward as a **column** with a
  slight forward drift) and **B** rising head-butt (melee hitbox above the head while vanilla's Up Stab pose `$80 == $08`
  is active).
- Up+B upward fire is **airborne only**. Grounded Up+B stays vanilla (elevators, doors, talking).
- Both are **gated on the Upward Thrust tech** (`$0796 & $04`). Without it, Up+B in the air gives the normal volley.
- Ceiling bricks: keep the existing glove gate (`BarbaBlocks` already samples fireball centers).

## Technical notes from the design review

- Vanilla airborne pose logic: `prg0.asm` `$9561-$959B`. `$80 = $08` only while ascending with Up held and the tech.
- `VOLLEY_SLOT` (`$05FC/$05FD`): bit 7 = crouched shallow drift, bits 0-5 lifetime (`$21`). **Bit 6 is free** for "up".
  `BarbaStepSlotY` (`src/breath.inc`) must subtract (start at 3 px/update) and kill on borrow or Y < `$10`, mirroring
  the existing `>= $E0` wrap guard. The three backed records (`src/extra_fire.inc`, `$6400+`) alias native slot 0 and
  share this path: verify upward shots work in those slots too.
- Latch the up/forward decision once per volley at the first shot (Up released mid-volley must not split it).
- The head-butt hitbox goes at the **native** head top plus a little reach, not the 48 px art top. Extend
  `BarbaSetDownstab` (`src/tall_player.inc`) or rename it `BarbaSetThrusts`.
- Muzzle for upward shots: the top of the head (see `BarbaGeometry`, `$05F2/$05F3`). The folded-head-under-ceiling
  case must still spawn a shot (it breaks a gloved brick directly above).
- Art: a looking-up head is **out of scope** (it will be done by hand later). Use the existing open-jaw attack head.
- Keep `BarbaLoadOk` / `LOAD_LIMIT` unchanged.

## Acceptance (all required; report the numbers)

1. New `tests/upstab.lua` covering the plan's cases 1-6: airborne Up+B with the tech emits 5 shots with Y strictly
   decreasing and X drifting toward facing; without the tech it's a normal forward volley; grounded Up+B (and on an
   elevator, if a fixture is practical; otherwise say so) does not fire up; a gloved ceiling brick breaks and stays without
   the glove, with Barba's pose/velocity unchanged; shots reaching the top clear without wrapping; head-butt damages an
   enemy above a rising Barba and does nothing while descending.
2. `python tools/build.py` and `python -m unittest discover -s tests` pass.
3. Every scenario in AGENTS.md's full-suite list passes, run one at a time, **except the four listed there as known
   stale** (town_safety, shouts, shout_queue, dialogue_speed). They must fail exactly as on the base commit, no worse.
4. Performance: `perf_volley` and `perf_lava` before (base `262501a`) and after. No new lag frames; peak within +300 cycles.
   Add an upward-volley phase to perf_volley (or a separate probe) in the six-enemy fight and report it.
5. Update `docs/UPSTAB-FIRE-PLAN.md` (status: implemented, with any deviations), `docs/STATUS.md`, `AGENTS.md`
   (memory map if RAM/ROM use changed), and add a checkpoint only if it's cheap. If you add one, keep the scene list in
   sync across `tools/state_scenarios.lua`, `tools/create_test_pack.py` and `tests/state_pack.lua`. Otherwise
   F3 (all techniques) is the playtest scene.
6. Regenerate the test pack (`python tools/create_test_pack.py --force`) in the worktree.

Commit on `feat/upstab-fire` (end the message with `Co-Authored-By: Codex <noreply@openai.com>`). Do not merge,
push or touch other branches. Never advance gates. Write a short report to `build/UPSTAB-REPORT.md` in the worktree
and as your final message, including a 5-step playtest for the producer (F-key, buttons, what to expect). Then stop.
