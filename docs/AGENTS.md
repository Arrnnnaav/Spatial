# AGENTS.md — start here

Entry point for any coding agent (Claude Code, Codex, Cursor, …) or new contributor working on **Spatial — Point & Ask**.
All project docs live in `docs/` (only `README.md` and the `CLAUDE.md` pointer stay at the root). Read this file first, then the docs it points to. These docs are living: update them as you work (see "Working loop").

## What Spatial is

Circle / box / point at anything on screen, ask a question, get an answer about exactly that thing.
Pointing is fast; describing location in words is slow and ambiguous. Spatial turns a human mark into a
structured, inspectable reference (`SpatialContext`) and answers about it.

- **Today:** Chrome MV3 extension (web pages + pdf.js viewer) → local FastAPI server → LLM providers.
- **Next:** OS-level desktop app (Tauri, Windows first, macOS next) so it works over *any* application.
- **Core invariant:** the mark is a **reference, never authority**. Spatial explains, highlights, compares,
  researches. It never clicks, types, submits or deletes.

## Doc map

| File | What it holds | Update when |
|---|---|---|
| `docs/AGENTS.md` | This entry point: orientation, commands, layout, working loop | Commands/layout/workflow change |
| `docs/PRD.md` | Product: problem, users, goals, scope, success metrics | Scope or priorities change |
| `docs/ARCHITECTURE.md` | How the system is built now and where it is going | Components, contracts, data flow change |
| `docs/DESIGN.md` | Interaction + UI design, visual language, key design decisions | UX or a design decision changes |
| `docs/RULES.md` | Working rules and conventions (defaults, not laws) | A rule stops serving the project |
| `docs/TASKS.md` | Roadmap + current task board with status | Every task start / finish |
| `docs/MEMORY.md` | Dated decisions, facts learned, gotchas, open questions | Something non-obvious is learned or decided |
| `docs/superpowers/specs/` | Approved design specs per sub-project | New sub-project design |
| `docs/superpowers/plans/` | Step-by-step implementation plans | Before implementing a spec |
| `docs/HOW_TO_RUN_AND_USE.md`, `PROVIDERS.md`, `AUDIO.md`, `LEARNING_PATH.md` | User/learner guides | Behaviour they describe changes |
| `docs/SPATIAL_STANDALONE_MASTER_PLAN.md` | Long-horizon vision (60 sections, 13 phases). Reference, not the task list | Rarely |
| `docs/SPATIAL_PRODUCTION_CHECKLIST.md` | Release checklist | Release process changes |

## Working loop (every session)

1. Read `docs/TASKS.md` (what is in progress / next) and `docs/MEMORY.md` (recent decisions, gotchas).
2. Pick or confirm the task. Non-trivial new work → brainstorm → spec → plan before code.
3. Work. Tests first where practical (`RULES.md`).
4. Before finishing: run the test commands below; update `TASKS.md` status; add anything non-obvious to
   `MEMORY.md`; update `ARCHITECTURE.md` / `DESIGN.md` / `PRD.md` if what they say is no longer true.
5. Commit docs together with the code they describe.

## Repo layout

```
extension/     Chrome MV3: content.js (overlay, ask panel, anchor collection), background.js (capture, crop,
               server calls, privacy), geometry.js (shared mark/rank math), popup, pdf.js viewer, offscreen audio
server/app/    FastAPI: main.py (routes), resolver.py (deterministic geometry ranking), providers.py (LLM chain,
               prompt), ocr.py (RapidOCR), research.py (search + cited answers), audio.py (STT/TTS), store.py
               (SQLite history), config.py (.env settings)
server/tests/  pytest + golden resolver cases (tests/cases/*.json, shared with extension geometry tests)
scripts/       try_providers.py (live smoke test), fetch_models.sh, probe_nvidia.py
docs/          guides + superpowers/specs + superpowers/plans
```

## Commands

```bash
# server (Windows: .venv\Scripts\activate)
cd server && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
cp .env.example .env            # then fill keys
uvicorn app.main:app --port 8787
python -m pytest -q             # server tests (177 passing as of 2026-09-24)

# extension
cd extension && node --test tests/geometry.test.mjs
# load unpacked: chrome://extensions → Developer mode → Load unpacked → extension/ ; hotkey Alt+Shift+A

# resolver eval + schema (repo root)
python scripts/eval.py cases [--resolver hybrid] [--record]   # hybrid replays server/tests/system_one_cassette.json
python scripts/export_schema.py

# providers live check
python scripts/try_providers.py
```

## Keys and secrets

All keys live in `server/.env` (gitignored, loaded by `server/app/config.py` via python-dotenv).
Never put keys in extension code. Relevant keys:

- LLM answerers: `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, Bedrock via AWS chain.
- **System One (Jev):** `SPATIAL_SYSTEM_ONE=jev|off` (default jev when a key is set), `SPATIAL_SYSTEM_ONE_TIMEOUT=1.5`, `TYPESAFE_API_KEY` — in `server/.env` for the server, and exported in the shell
  (`$env:TYPESAFE_API_KEY="…"` in PowerShell) for experiment scripts.
- **Research:** `TAVILY_API_KEY` (optional; DuckDuckGo fallback), `SPATIAL_RESEARCH_SEARCH=auto|tavily|ddg`, `SPATIAL_RESEARCH_VERIFY=on|off`.
- **Laya (Jev-compatible):** `LAYA_API_KEY` (impossibl hosted) or `LAYA_BASE_URL` for self-hosted `laya-serve`.

## Tooling available to agents

- TypeSafe skill (`typesafe@typesafe-ai` plugin): guidance for Jev / System One question design. Live docs:
  https://docs.typesafe.ai/llms.txt (append `.md` to page paths).
- Superpowers skills: brainstorming → writing-plans → executing-plans / TDD / verification.
- Project automations (`.claude/`, `.mcp.json`):
  - Hooks: `guard_secrets.py` blocks Read/Edit/Write of `server/.env` and edits of `*.db`;
    `post_edit_checks.py` runs the geometry parity tests after editing `geometry.js`/`resolver.py`, and regenerates +
    checks the schema after editing `contracts.py`.
  - Skills: `/eval` (resolver eval vs baseline, logs to MEMORY), `/sync-docs` (update the living docs).
  - Subagent: `privacy-reviewer` — run after changes to traces, contracts, routes/CORS, capture or UIA code.
  - MCP: `context7` (current docs: Tauri, FastAPI, pydantic), `playwright` (drive Chromium with the unpacked extension).
