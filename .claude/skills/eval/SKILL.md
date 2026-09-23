---
name: eval
description: Run the Spatial resolver eval against the committed baseline, list misses by category, and record results in docs/MEMORY.md. Use after any change to resolution (geometry, candidates, System-One/Jev resolver) and for every Jev/Laya experiment.
disable-model-invocation: true
---

# Resolver eval

1. From the repo root run:
   ```bash
   python scripts/eval.py cases --baseline server/tests/eval_baseline.json
   ```
   Add `--json` if you need to diff numbers programmatically. For a recorded trace log use
   `python scripts/eval.py traces "%APPDATA%\Spatial\logs"`.
2. Report: total top-1 / top-3 / abstain rate / p50 / p95, the per-category table, and the list of top-1 misses.
   Compare every number with `server/tests/eval_baseline.json` and say which cases changed (newly fixed, newly broken).
3. Exit code 1 means top-1 dropped more than 2 points below baseline: treat as a regression, find the case(s)
   responsible before continuing.
4. Append one dated line to `docs/MEMORY.md` → "Facts learned": what was evaluated (commit / resolver backend /
   question wording), the headline numbers, and the notable misses.
5. Only rewrite the baseline (`--write-baseline server/tests/eval_baseline.json`) when the user agrees the new
   numbers are the new bar. Never edit eval cases to raise a score.
