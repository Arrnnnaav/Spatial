# Home Tasks & Reminders (Phase D) Implementation Plan

> Executed inline, TDD. Spec: `docs/superpowers/specs/2026-10-01-desktop-dashboard-design.md` (phase D).

**Goal:** Simple personal tasks/notes and reminders on the dashboard Home; a reminder fires with the dashboard window closed (app in the tray).

**Architecture:** Two small tables (`tasks`, `reminders`) in the existing local SQLite DB via `server/app/personal.py`; CRUD under `/api/tasks*` and `/api/reminders*` behind `require_token` + `require_desktop`. The dashboard webview stays loaded while hidden, so a 15 s timer there asks `GET /api/reminders/due`, marks each fired, and shows a small always-on-top `reminder` window (no new Rust dependency; native-toast crates are not available offline). Missed reminders fire on the next start.

**Global constraints:** text is local only (never sent to a provider); activity log stays content-free; text rendered with text nodes; `due_at` must carry a timezone and is stored as UTC; a reminder fires at most once.

## Review Focus
- Naive/garbage `due_at` → 422; far-past `due_at` fires immediately once, not repeatedly.
- App restarted after the due time: fires on next poll, exactly once.
- Two reminders due together: popup lists both; dismissing one keeps the other.
- Deleting a task does not delete its reminders silently (reminder keeps its own text).
- Hostile task text renders as text.

## Tasks
1. **Server store + routes** — `personal.py`: `add_task/list_tasks/update_task/delete_task`, `add_reminder/list_reminders/due_reminders(now)/mark_fired/delete_reminder`; routes; tests in `server/tests/test_personal.py` (CRUD, 422 on naive time, due excludes future + already-fired, fired is idempotent, auth + desktop token required).
2. **Model** — `dashboard-model.js`: `quickDue(kind, now) -> ISO string` (`10m`, `1h`, `tomorrow9`), `formatDue(iso)`, `taskCard`, `reminderCard`; node tests.
3. **UI** — `dashboard.html/js`: Home gets Tasks (add, tick, delete, note) and Reminders (text + quick buttons + datetime-local, list, delete); poller; `reminder.html/js` popup (Dismiss, Snooze 10 min); `tauri.conf.json` window `reminder`, capability `reminder`.
4. **Verify** — smoke test round-trip for tasks/reminders on the packaged server; full suites; rebuild; native check: reminder due in ~20 s fires with the dashboard hidden (`--autostart` launch). Docs.
