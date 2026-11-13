# <repo-name> dossier

_Scout: scout-gemma · scanned <scanned_at from SCAN.json> · scores are provisional_

## Snapshot
- **Stack:** <one line>
- **What it is:** <one sentence from the README>
- **Size:** <tracked_files> files, <code_lines> code lines
- **Branch / state:** <current_branch>, <N dirty files or "clean">

## Core loop
<2-4 sentences: what the player does minute to minute and whether it seems to work, according to the README/docs. Write "unknown" if the docs do not say.>

## Bottlenecks
- **Frame / CPU:** <evidence from file names, docs, or smoke output, or "no evidence">
- **Memory / size budget:** <for ROM projects: bank or ROM limits mentioned in docs, or "no evidence">
- **Largest files (refactor risk):** <top 3 from largest_code_files with line counts>

## Visual cohesion
<2-3 sentences: is there a named palette, shader, art direction doc, or a mix of styles? Quote file names as evidence. Do not invent.>

## Recent activity
- **Commits in last 14 days:** <commits_last_14d>
- **Latest:** <the 3 newest lines from recent_commits>

## Smoke test
- **Command:** <command or "none detected">
- **Result:** <PASS / FAIL / not run> <add "(likely environment, not code)" if likely_env_failure is true>

## Needs frontier
<Bullet list of anything that needs real design or code judgment (an architecture smell, a likely perf problem you cannot confirm, a direction question). Write "- none" if nothing.>
