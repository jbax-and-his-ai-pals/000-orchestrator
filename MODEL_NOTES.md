# Model notes: what each model is actually good at

A living ledger the conductor (Claude in chat) uses to create, size and route work. Every claim should come from an
observed run: date it, and say what happened. `orch.py model-stats` gives the hard counts behind it.
Update this after any dispatch that teaches something.

## Routing summary (current best guess)

| Model / lane | Give it | Don't give it | Prompting that works |
| :-- | :-- | :-- | :-- |
| **Gemma 4 12B** (local, scout-gemma) | Template-filled dossiers from precomputed facts; 1–2-file mechanical edits with a grep-able verify; new data-only files | Judgment, scoring without evidence, anything needing >2 files of context, appends without an exact anchor | One job per run; a **literal JSON example** of every tool call; fixed headings; code-enforced limits |
| **Codex gpt-6.1-sol** (OpenAI sub, planner-codex) | LLDs, execution plans, multi-file implementation with tests, branch reviews, baselines | Ambiguous gates (it will block, correctly, rather than guess) | State acceptance criteria and accepted exceptions explicitly (REVISIONS.md); give it a loop: "do the next available subtask until none remain" |
| **Claude Sonnet 5.5** (Claude sub, architect-claude) | Pitches, HLDs, design-heavy code (shader, motion, typography) | Long mechanical implementation (spend Codex quota instead) | Taste profile + dossier only; scope to one initiative |
| **Claude Opus 5.5** | High-complexity HLDs; producer-facing judgment in chat | Routine conducting (use Sonnet) | — |
| **Gemini 3.6 / 3.5 / 3.0 Flash** (free tier, reviewer-gemini, parked) | Long-context deep reads and second opinions (untested in a full run) | Anything blocking: free tier can 503 | Fallback chain 3.6 → 3.5 → 3.0; never fall back to Gemma |

## Observations log

### 2026-11-13: first proof-of-concept run (initiative #2, 002-wasteball impact beats)

**Gemma 4 12B, local**
- Dossier narration: accurate and honest in ~25–30 s; it writes "unknown" instead of inventing (003-big-city has no README).
- Scored playability 3 with an unknown core loop, then 0/0 when it passed the literal placeholder `N`. Fixed with a code
  guard (no score without evidence; 0 only if nothing runs) plus a concrete example command.
- `edit` tool: twice sent a malformed call (`path` inside the edit item, empty `oldText` for an append). Fixed by
  putting an exact JSON example in the playbook; after that, edits worked.
- Appended at the wrong anchor (mid-file); the verify command caught it, and Gemma followed the protocol (discard → blocked).
- Escalated "missing file" for a subtask that creates new files: a playbook bug, now handled via `new_files`.
- Mechanical constants subtask (2 new files, 17 lines): perfect, verified, committed in 20 s.
- Lesson: Gemma's reliability comes from examples plus a verify command, not from instructions alone.

**Codex gpt-6.1-sol**
- LLD + plan in ~4.5 min: very rigorous (time-scale safety, stale-timer tokens, baseline gate, rollback). Routing to
  Gemma was contract-compliant on the first try.
- Baseline subtask: correctly BLOCKED on pre-existing engine leaks under a "zero engine errors" gate. Needed a producer
  decision (leaks = accepted floor). Lesson: anticipate pre-existing failures when writing gates.
- Implementation (2 subtasks, tests 97 → 137) in one looped run of ~10 min; review with full test rerun in 1.5 min.

**Claude Sonnet 5.5 (agent)**
- 2 on-taste pitches in 26 s. HLD in 94 s with accurate code citations; missed one file (camera_rig.gd).
- Shader + stencil callout + font acquisition subtask in ~5 min, clean, no new engine errors.

**Gemini (free tier)**
- 3.8 Flash: HTTP 503 every time we tried. 3.6 / 3.5 / 3.0 Flash and the Flash-Lites answer. Hosted Gemma 4: HTTP 400.
  Pro and Argon-class models: 429 (not free).
