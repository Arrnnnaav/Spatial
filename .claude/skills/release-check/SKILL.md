---
name: release-check
description: Run Spatial's release gate in one go - server pytest, extension geometry, desktop JS and Rust tests, resolver eval vs baseline, schema drift, optionally the release build and packaged-server smoke test - and report one pass/fail table. Use before committing a milestone, before a release, or when asked whether everything still passes.
disable-model-invocation: true
---

# Release check

1. Fast gate (about 1-2 minutes):
   ```bash
   python .claude/skills/release-check/run_checks.py
   ```
2. Full gate including the Windows release build and the packaged-server smoke test (about 10-20 minutes; run in the
   background and use Monitor so you are notified, not Read-polling):
   ```bash
   python .claude/skills/release-check/run_checks.py --build
   ```
3. Report the table as-is. For each FAIL show the printed tail and name the likely cause; never claim success on a
   partial run. A step that could not run (missing tool) is a FAIL, not a skip.
4. Not covered by this gate (say so): native UI behaviour (use `/native-e2e`), real microphone dictation, tray menu clicks,
   live provider calls (`scripts/try_providers.py`).
5. If `schema drift` fails, `schema/spatial-context.v3.json` was regenerated: review the diff and commit it with the contract change.
