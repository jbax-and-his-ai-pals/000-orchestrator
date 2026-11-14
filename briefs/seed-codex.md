# Seeding brief: deep dossier for ONE project (planner-codex)

Producer directive 2026-11-13: "Start project seeding for all remaining projects." Goal: every project gets a
current, honest, forward-looking dossier the dashboard can show at a glance, and a standardization checklist.

Your message names ONE repo. Work only on it, then stop. Never advance gates, never commit, push, check out or switch
branches in `C:/jbax-and-his-ai-pals/<repo>` (the producer's checkout is read-only to you). Write only the files named below.

ORCH = `C:/jbax-and-his-ai-pals/_orchestrator/.venv/Scripts/python.exe C:/jbax-and-his-ai-pals/_orchestrator/scripts/orch.py --as planner-codex`

## Inputs (read these first)
- `_orchestrator/dossiers/<repo>/SCAN.json`, `SMOKE.json`, and any existing `DOSSIER.md` / `AUDIT_NOTES.md` (Gemma's
  facts: provisional, check them).
- `_orchestrator/state/TASTE_PROFILE.md` (what the producer values).
- The repo itself: README/docs, entry points, main scenes/modules, tests, build scripts, the last ~30 commits.
  Read the code, not just file names. Budget: about 15 minutes of reading.

## Run it (headless only)
- Try the project's own smoke/test/build command once, headless, with a timeout of 5 minutes. Godot: `godot --headless`.
  VR projects (004, 009, 010): never launch VR mode. ROM projects: build only; do not open an emulator window.
- Record exactly what you ran and the result. A failure caused by the environment (missing tool) is labeled as such.

## Output 1: `_orchestrator/dossiers/<repo>/DOSSIER.md`
Write it to `DOSSIER.deep.md` first, then submit with write-dossier (below). Keep these headings EXACTLY, in order:

```
# <repo> dossier

_Author: planner-codex · deep dossier <YYYY-MM-DD> · read the code and ran: <command or "nothing runnable">_

## Snapshot
- **Stack:** Godot 4.6 / GDScript
- **What it is:** <one sentence a stranger understands, e.g. "A top-down arena brawler where you knock scrap robots into a furnace.">
- **Size:** <files> files, <code lines> code lines
- **Branch / state:** main, clean

## Player experience
<3-5 sentences, second person, an average session: how you start, what you spend most time doing, a typical moment of
tension or reward, how it ends. For a tool, the typical user's session. Base it on code you read; if the loop is not
wired up, say what the code is building toward and label it: "Intended (not yet playable): ...">

## Core loop
<2-4 sentences: what the player does minute to minute, and whether it actually works today (cite the scene/script).>

## Current state
<3-6 bullets of what exists and works, what is half-built, what is broken. Cite files. e.g.
"- Works: procedural road network (scripts/secondary_road_generator.gd), viewable in city_debug_view.tscn".>

## Bottlenecks
- **Frame / CPU:** <evidence, or "no evidence">
- **Memory / size budget:** <evidence, or "no evidence">
- **Largest files (refactor risk):** <top 3 with line counts>
- **Biggest blocker:** <ONE sentence: the single thing most holding the project back>

## Visual cohesion
<2-3 sentences with file evidence: palette, shaders, art direction, mixed styles.>

## Recent activity
- **Commits in last 14 days:** <n>
- **Latest:** <3 newest commits>

## Smoke test
- **Command:** <exact command you ran>
- **Result:** <PASS / FAIL (reason) / FAIL (environment: godot not on PATH)>

## Next milestone
<ONE concrete, demoable milestone, sized for 1-3 agent sessions, phrased as an outcome, e.g.
"Playable 3-minute round: spawn, collect, score screen, restart." Then 2-4 bullets of the work it needs, each tagged
with a lane: [gemma] mechanical 1-2 files with a grep-able verify; [codex] multi-file logic; [claude] design/feel/visual;
[producer] needs a human (rendered feel, hardware).>

## Standardization
<One line each, ✅ or ❌ plus a few words:>
- README with what-it-is + how to run: ✅/❌
- Headless smoke command that passes: ✅/❌ (<command>)
- Automated tests: ✅/❌ (<count or framework>)
- .gitignore covers build/import output: ✅/❌
- Clean working tree on main: ✅/❌

## Needs frontier
<Bullets of judgment calls or direction questions for the producer/Claude. "- none" if none.>
```

Rules: no invented facts. Where you truly cannot tell, write a labeled fallback ("Not determinable from code: no main
scene set in project.godot"), never a bare "unknown". Under 12,000 characters.

## Submit
Scores (0-10, only with evidence): playability 0 = nothing runs, 3 = tech demo, 6 = playable loop, 9 = polished and fun;
visual 0 = none, 3 = programmer art, 6 = cohesive style, 9 = striking.
```
ORCH write-dossier <repo> C:/jbax-and-his-ai-pals/_orchestrator/dossiers/<repo>/DOSSIER.deep.md --playability <n> --visual <n> --bottleneck "<the Biggest blocker sentence>"
```
Omit a score flag when you have no evidence. Then delete `DOSSIER.deep.md`.

## Finish
Do not file sparks; the conductor queues [gemma] bullets itself. Then: `ORCH log "seeded <repo>: playability <n>, next milestone: <milestone>" --project <repo>`. Stop.
