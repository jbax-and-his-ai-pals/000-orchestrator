# Seeding brief: judgment pass for ONE project (architect-claude)

A deep dossier for the repo named in your message was just written by another agent. Your job is the part that needs
taste: the player experience, the scores, the biggest blocker, and the next milestone. Work only on that repo, then stop.
Never advance gates; never commit in the producer's checkout.

ORCH = `C:/jbax-and-his-ai-pals/_orchestrator/.venv/Scripts/python.exe C:/jbax-and-his-ai-pals/_orchestrator/scripts/orch.py --as architect-claude`

1. Read `_orchestrator/state/TASTE_PROFILE.md`, then `_orchestrator/dossiers/<repo>/DOSSIER.md`. Spot-check the repo
   only where a claim looks wrong (budget: 5 files).
2. Copy DOSSIER.md to `DOSSIER.deep.md` in the same folder and edit ONLY these sections, keeping every heading:
   - `## Snapshot` → **What it is:** one plain sentence a stranger understands. It is the project's description on the
     dashboard, shown above the player experience, so it should say what the thing *is*, not how it plays.
   - `## Player experience`: 3-5 vivid, honest sentences in second person. Concrete moments, not genre labels.
     "Intended (not yet playable): ..." if the loop isn't wired.
   - `## Bottlenecks` → **Biggest blocker**: the one thing that most holds the game back from being fun or shippable.
   - `## Next milestone`: one demoable outcome the producer would be excited to play, sized for 1-3 agent sessions,
     with lane-tagged bullets ([gemma] [codex] [claude] [producer]). Prefer feel and fun over infrastructure unless
     nothing runs.
   - Author line: append ` · judged by architect-claude <YYYY-MM-DD>`. Keep the original author first.
3. Submit, with scores only where the dossier gives evidence (playability 0 nothing runs / 3 tech demo / 6 playable
   loop / 9 polished; visual 0 / 3 programmer art / 6 cohesive / 9 striking):
   `ORCH write-dossier <repo> C:/jbax-and-his-ai-pals/_orchestrator/dossiers/<repo>/DOSSIER.deep.md --playability <n> --visual <n> --bottleneck "<Biggest blocker>"`
   Then delete DOSSIER.deep.md. Stop.
