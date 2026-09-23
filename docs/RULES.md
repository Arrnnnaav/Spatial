# Rules

*These are defaults, not laws. If a rule gets in the way of doing the right thing, break it deliberately,
say why in the commit or `MEMORY.md`, and edit this file if the change should stick.*

## Product invariants (the closest thing to hard rules)

1. **Reference, never authority.** A mark never triggers a click, keystroke, submit or delete. Any future
   "do this" feature needs explicit permission → approval → execution → verification, outside the mark path.
2. **Show what was understood.** Always highlight / name the resolved target. Surface ambiguity; don't hide it.
3. **Never a dead end.** Provider or resolver failure falls back (next provider → geometry-only → quoted text).

## Engineering

- **Small, focused files.** If a file passes ~400 lines or mixes jobs, split it when you are already working
  there (don't refactor unrelated code).
- **Tests first where practical.** Resolver, contracts, geometry, trace and privacy code: write the failing
  test first. UI: manual checklist in `SPATIAL_PRODUCTION_CHECKLIST.md`.
- **Geometry parity.** Any change to ranking math changes both `geometry.js` and `resolver.py` and adds a
  golden case.
- **Numbers in code, judgments in models.** Arithmetic, geometry, thresholds, counting → code.
  "Which one did they mean?", "is this ambiguous?", "does this need research?" → System One (Jev/Laya).
- **One contract.** New clients or candidate sources speak `SpatialContext` / `CandidateObject`; no
  source-specific branches in the server.
- **Keep old clients working** across protocol bumps (accept v2 while v3 rolls out).
- **Swappable vendors.** Model/provider calls go behind an interface selected by config.
- **Measure before claiming.** Resolver changes report eval numbers (top-1/top-3/latency) against the
  committed baseline.

## Secrets & data

- Keys only in `server/.env` (gitignored) or shell env. Never in extension code, docs, commits or traces.
- Trace log is opt-in and never contains image bytes.
- Don't commit `*.db`, `.venv`, model weights, or `.env`.

## Workflow

- New sub-project: brainstorm → spec (`docs/superpowers/specs/`) → plan (`docs/superpowers/plans/`) → build.
- Small change: short design in chat, approval, build.
- Update `TASKS.md` when starting/finishing work; `MEMORY.md` when learning or deciding something
  non-obvious; other docs when they become untrue.
- Commit messages: conventional style (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`), explain *why* when
  not obvious. Commit or push only when asked.

## Style

- Python: type hints, pydantic for API models, no FastAPI imports in core modules.
- JS: vanilla, no build step for the extension (for now); plain-script modules that also run under `node:test`.
- Comment the *why*, not the *what*; match surrounding density.
