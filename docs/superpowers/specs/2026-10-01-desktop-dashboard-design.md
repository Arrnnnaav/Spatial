# Desktop dashboard, focused hotkeys and personal history — design

**Date:** 2026-10-01 · **Status:** draft for review · **Sub-project:** 7 (builds on 4, 5, 6)

## Intent

Spatial stays "point at something, ask about exactly that thing". Around that core it becomes a small
personal desk tool: a dashboard you open from the app icon, hotkeys that do one thing each, dictation that
leaves a saved entry, and lightweight tasks/reminders. The mark remains a **reference, never authority**:
nothing added here clicks, types into other apps on its own, submits or deletes anything outside Spatial's own data.

Success: (1) `Alt+Shift+S` and `Alt+Shift+D` never show dashboard/settings clutter; (2) every Ask and dictation
is findable, editable, deletable in the dashboard; (3) settings/recovery errors appear in Settings, not in the
Ask panel; (4) a reminder fires with the window closed; (5) no personal content ever leaves the local DB
except to the provider the user asked to answer/transcribe.

Said by user: dashboard with Home / Ask logs / Dictation logs / Settings; S = mark first then compact panel
(Ask or Dictate); D = dictate directly; dictation saved with title, one-line summary, time, source app, provider,
`.docx` download, no audio saved; Deepgram trial key only in `%LOCALAPPDATA%\Spatial\server.env`; reminders fire
while closed; scope may grow in this direction. Assumptions (correct me): single user, Windows only for now,
reminders are local notifications (no sync/calendar), Deepgram optional behind an eval gate.

## Already in the repo (reuse, do not rebuild)

- `server/app/store.py` SQLite `contexts` (Ask history: create/recent/get/delete).
- `/api/dictate/polish`, `/api/dictate/docx`, `/api/stt`, `/api/stt/live`, `/api/desktop/dictation`.
- Tauri windows `panel`, `overlay`, `dictate`; tray; autostart plugin; single-instance; desktop + API tokens.

## Decomposition (each phase = own plan, ships on its own)

| Phase | Scope | Depends on |
|---|---|---|
| A | Dashboard window shell (Home, Ask logs, Dictation logs, Settings); move server/provider/Jev/research/speech/hotkey/autostart/pairing out of the panel; startup/token/autostart errors routed to Settings | — |
| B | Hotkey flow: `S` = overlay mark → compact panel with Ask / Dictate only; `D` = direct dictation, no overlay; panel stripped of status/settings | A (error routing) |
| C | Dictation entries: foreground-app capture before UI, final transcript → `dictations` table (title, one-line summary, time, source app/page, STT + cleanup provider), `.docx` from entry, edit/delete; audio never stored | A |
| D | Home: tasks/notes + reminders; Tauri-side scheduler + Windows toast so reminders fire with the window closed | A |
| E | Quick recall popup (Ditto-inspired): global hotkey opens a keyboard-first searchable list of Ask + dictation history; Enter copies, Shift-Enter copies plain text, F3 preview, Esc closes | A, C |
| F | Deepgram streaming STT with local Whisper fallback — **only if** the existing speech eval shows NVIDIA live latency/WER is worse; key in `%LOCALAPPDATA%\Spatial\server.env` only | C |

Order: A → B → C → D → E → F(gated).

## Architecture

- **Data** stays in the existing local SQLite file (personal history) in separate tables: `contexts` (exists),
  `dictations`, `tasks`, `reminders`. Content-free operational diagnostics stay in the existing bounded
  activity log and are never joined to personal tables. No telemetry.
- **Server** owns CRUD (`/api/history/*`, `/api/dictations/*`, `/api/tasks/*`, `/api/reminders/*`), all behind
  `require_token`. Title/summary generation uses the existing provider chain on the transcript text only.
- **Desktop** gets a fourth window `dashboard` (plain HTML/JS like existing UI). Tray "Open" and app-icon launch
  open it; the compact `panel` no longer hosts home/settings.
- **Reminders:** Rust side keeps due times in a small file/DB read at start; a timer thread fires a native
  toast and emits to the dashboard when open. Autostart keeps the tray process alive so closed-window reminders
  fire; if autostart is off, Settings says reminders only fire while Spatial runs.
- **Settings** move into the dashboard; the provider-secret UI only writes keys to `server.env`, never echoes them,
  never logs them.

## Data sketch

```
dictations(id, created_at, title, summary, text, source_app, source_title, stt_provider, cleanup_provider)
tasks(id, created_at, text, done, note)
reminders(id, task_id?, due_at, text, fired_at?)
```
`source_title` is page/window title only when the foreground app is not on the exclusion list
(password managers, etc., reusing the UIA exclusion list).

## Error handling

Startup/token/autostart/hotkey-registration errors → Settings "Status" section with a fix action; the Ask panel
only shows errors about the current question. Dictation insert failure keeps the entry and offers Copy.

## Testing

Server: pytest per new table/route (CRUD, token required, delete really deletes, no content in activity log).
Desktop: node tests for dashboard view logic; packaged-server smoke extended with history + dictation-entry
round trip; manual native checklist (hotkeys, toast with window closed, tray, multi-monitor) listed in TASKS.
Run `privacy-reviewer` after phases B, C, D. Geometry/resolver untouched, so eval stays at baseline.

## Out of scope

Cloud sync, calendar integration, mobile, storing audio, any automation that acts on other apps, macOS port
(unchanged, sub-project 5).
