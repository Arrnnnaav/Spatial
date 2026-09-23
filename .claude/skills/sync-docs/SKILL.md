---
name: sync-docs
description: Bring Spatial's living docs (docs/TASKS.md, docs/MEMORY.md, docs/ARCHITECTURE.md, docs/AGENTS.md, docs/DESIGN.md, docs/PRD.md) up to date with the work done since they were last touched. Use at the end of any task, before committing, or when the user asks to update/track progress.
---

# Sync the living docs

1. Find what changed since the docs were last updated:
   ```bash
   git log --oneline $(git log -1 --format=%H -- docs/TASKS.md)..HEAD
   git diff --stat $(git log -1 --format=%H -- docs/TASKS.md)..HEAD
   ```
   plus any uncommitted changes (`git status --short`).
2. `docs/TASKS.md`: tick finished items `[x]`, mark started ones `[~]`, add newly discovered tasks, update the
   roadmap status column and "Last updated".
3. `docs/MEMORY.md`: add dated entries (YYYY-MM-DD) for decisions, facts learned (numbers, API behaviour, limits)
   and gotchas that are not obvious from code or git log. Remove entries that became wrong.
4. `docs/AGENTS.md`: keep commands and the current test count true (run `cd server && python -m pytest -q` and
   `node --test extension/tests/geometry.test.mjs` to get real numbers — never guess).
5. `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/PRD.md`: edit only statements that are now untrue; add a
   DESIGN decision-log row for any design decision taken.
6. Keep edits small and factual. Commit the docs together with the code they describe when the user asks for a commit.
