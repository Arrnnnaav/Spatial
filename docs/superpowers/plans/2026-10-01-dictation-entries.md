# Dictation Entries (Phase C) Implementation Plan

> **For agentic workers:** executed inline (user chose native execution for this spec). Steps are TDD: failing test → implement → pass.

**Goal:** Hotkey dictation leaves a saved, editable, deletable entry (title, one-line summary, time, source app/page, STT + cleanup provider) shown in the dashboard's Dictation logs with `.docx` download; the dictation pill shows a live transcript. Audio is never saved.

**Architecture:** New SQLite table `dictations` in the existing local DB. Server resolves title/summary (provider chain, text only; deterministic fallback) and the source app from the foreground window handle (sensitive windows → no source). `dictation.js` posts the final transcript after insertion/fallback. Dashboard lists/edits/deletes via new routes.

**Tech Stack:** FastAPI + SQLite, pytest, vanilla JS, node --test, Tauri.

**Spec:** `docs/superpowers/specs/2026-10-01-desktop-dashboard-design.md` (phase C)

## Global Constraints
- Only the final transcript text + metadata is stored; never audio, never window handles, never the sensitive-window title.
- Routes behind `require_token`; entries only created from desktop (`require_desktop`).
- Title/summary generation sends transcript text only to the configured answer provider (same disclosure as "Polish dictation"); failure falls back to a local title.
- Text rendered with text nodes only.

## Review Focus
- Sensitive foreground window (password manager) → source app/title empty, entry still saved.
- Provider down/slow → entry still saved with fallback title/summary.
- 12,000-char transcript and empty/whitespace transcript (rejected 422).
- Editing an entry's text does not regenerate/leak anything; delete really deletes; clear-all empties.
- Composer dictation (Ask panel) is NOT saved.

## Tasks

### Task 1: Store + local title/summary
Files: `server/app/dictations.py` (create), `server/tests/test_dictations.py` (create).
Interfaces — Produces: `dictations.fallback_meta(text) -> (title, summary)`; `create(text, title, summary, source_app, source_title, stt_provider, cleanup_provider) -> dict`; `list_recent(limit) -> list[dict]`; `get(id)`; `update(id, **fields) -> dict|None` (title/summary/text only); `delete(id) -> bool`; `clear() -> int`. Entry dict keys: `id, created_at, title, summary, text, source_app, source_title, stt_provider, cleanup_provider`.
- [ ] Tests: fallback title ≤ 60 chars/≤ 8 words, summary ≤ 140 chars one line; create/list newest-first/get/update/delete/clear round-trip.
- [ ] Run (fail: no module) → implement (`create table if not exists dictations …` via `store.connect()`'s DB path) → run (pass).

### Task 2: Routes
Files: `server/app/main.py`, `server/app/desktop.py` (`window_label(hwnd) -> {"app","title"}`), `server/tests/test_dictations.py`.
Interfaces — Produces: `POST /api/dictations` body `{text(1..12000, non-blank), target_hwnd?:int, stt_provider?:str, cleanup_provider?:str}` → entry; `GET /api/dictations?limit` ; `GET/PATCH/DELETE /api/dictations/{id}`; `DELETE /api/dictations`.
- [ ] Tests (providers off ⇒ fallback meta): create returns entry with fallback title; blank → 422; token required; PATCH edits title/text; DELETE 200 then 404; clear empties; `window_label` monkeypatched sensitive → empty source.
- [ ] Implement routes; LLM meta via `answer_stream` like `/api/dictate/polish` (JSON `{"title","summary"}` parsed defensively, else fallback); run all server tests.

### Task 3: Client capture + live pill
Files: `desktop/ui/dictation.js`, `desktop/ui/dictate.html`.
- [ ] Live preview for hotkey dictation: start the live socket for both destinations; for `external`, show the last ~60 chars of the live text in `#status`.
- [ ] After final transcript (inserted or Copy fallback) and destination `external`, `Spatial.post('/api/dictations', {text, target_hwnd, stt_provider, cleanup_provider})` (best effort, never blocks insertion); emit `spatial://dictation-saved`.
- [ ] `node --check`; existing dictation tests stay green.

### Task 4: Dashboard Dictation logs
Files: `desktop/ui/dashboard-model.js` (+`dictationCard`), `desktop/tests/dashboard-model.test.cjs`, `dashboard.html`, `dashboard.js`.
- [ ] Test: `dictationCard(entry) -> {id,title,summary,when,source}` with hostile text kept as plain strings, source "" when unknown.
- [ ] UI: list newest first, open detail with editable title/text, Save (PATCH), Delete, Clear all, Download .docx (existing `/api/dictate/docx`); refresh on `spatial://dictation-saved`.

### Task 5: Docs, build, verify
- [ ] Smoke test: POST/GET/DELETE `/api/dictations` on the packaged server. Full suites, release build. Update TASKS/ARCHITECTURE/DESIGN/MEMORY.
