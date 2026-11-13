# Gemma capability contract

Local Gemma (`ollama/gemma4:12b`, 32k context, RTX 4070 Ti) is free and always on, but it is a 12B model.
It is reliable at narrow, fully specified, verifiable work. It is unreliable at judgment, design, multi-file
reasoning, and anything where a plausible wrong answer looks the same as a right one.

This contract decides what goes to Gemma and what needs a frontier model. **`scripts/orch.py` enforces the
starred rules (★). The prompts restate them, but the code is the guardrail.**

## How we get the most out of Gemma

1. **Python does the thinking-free work first.** `orch.py scan` and `orch.py smoke` compute file counts,
   largest files, git activity, test commands and smoke results deterministically. Gemma narrates
   `SCAN.json` and `SMOKE.json`; it never has to discover facts by exploring a repo.
2. **One job per run.** `orch.py queue scout` returns exactly one job: one scan *or* one subtask.
3. **Fill-in templates, not open prose.** Dossiers use a fixed template with fixed headings ★, so output
   is easy to check and easy for the frontier agents to read.
4. **Small, bounded context.** Gemma reads `SCAN.json`, `SMOKE.json`, the README head, and at most the
   files a subtask names. It never reads whole repos.
5. **Every code task ships with its own test.** Gemma's subtasks carry a `verify` command ★ (POSIX shell, run by
   `orch.py verify` under Git Bash in the worktree, so `grep`, `test` and `&&` all work). Gemma
   loops edit → verify → fix (at most twice), and can only mark a task done after a pass ★.
6. **Escalating is the right move, not a failure.** When unsure, Gemma runs `orch.py escalate` immediately.
   That costs one frontier call. A confident wrong edit costs a review cycle and the producer's trust.

## Gemma may do

| Work | Conditions |
| :-- | :-- |
| Dossier narration | From `SCAN.json`/`SMOKE.json`/README only, in the fixed template ★ |
| Provisional scores | `playability_score` / `visual_maturity` 0–10, labelled provisional in the dossier |
| Running smoke tests and profilers | Through `orch.py smoke` only (throwaway detached worktree) |
| Code subtasks routed `gemma` | 1–2 named files ★, explicit steps ★, acceptance ★, `verify` command ★, ≤150 changed lines ★, no files outside the list ★ |
| On `complexity: high` projects | Only subtasks the planner flags `"mechanical": true` ★: renames, constant/data tables, test scaffolds, docs, boilerplate |

## Gemma must not do (frontier required)

- Pitches, HLDs, LLDs, execution plans, or code review. Those belong to architect-claude and planner-codex.
- Design or taste judgments that set direction. Its dossier scores are inputs only; the architect re-judges them.
- Non-mechanical changes to 6502/65816/6507 assembly, bank layouts, mapper code, cycle-counted kernels,
  shaders, physics or netcode.
- Edits that span more than 2 files, need reading more than ~4 files to understand, or have no runnable check.
- Anything on `main`/`master` ★, or outside `_orchestrator/worktrees/` ★. Pushing, ever.

## Escalation triggers

| Trigger | What happens |
| :-- | :-- |
| Planner routes an out-of-contract subtask to gemma | `attach-plan` refuses the plan with the reasons ★ |
| Gemma's commit touches unlisted files or exceeds 150 lines | `commit` refuses; Gemma runs `discard`, then marks the subtask `blocked` ★ |
| Gemma marks a subtask `blocked` twice | Auto-reassigned to `codex`, logged as `escalated` ★ |
| Instructions are ambiguous, a listed file is missing, or the fix needs another file | Gemma runs `orch.py escalate <id> <sub> --reason "..."` at once |
| Dossier missing a template heading or over 12k chars | `write-dossier` refuses ★; Gemma retries once, then logs and stops |
| The dossier's `## Needs frontier` section lists something | The architect reads it on its next cycle and may pitch it |

## Tuning

Limits live in `GEMMA` in `scripts/orch.py` (`max_files`, `max_changed_lines`, `max_attempts`, `escalate_to`).
Loosen them only after real runs show Gemma clearing them. Its `escalated` and `review_fail` events on the
Activity tab are the evidence to check.
