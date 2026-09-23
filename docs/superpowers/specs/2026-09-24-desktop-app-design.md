# Desktop App (Sub-project 4) — Design

**Date:** 2026-09-24 · **Status:** In progress (goal: build phase by phase, merge each)
**Evidence:** UIA spike (`scripts/spikes/uia_region_probe.py`, `docs/MEMORY.md` 2026-09-24)

## Goal

Press a global hotkey anywhere in Windows, draw on a frozen copy of the screen, ask, and get the same grounded answer
the extension gives — for any application.

## Split of responsibilities

| Piece | Where | Why |
|---|---|---|
| Screen capture (freeze-frame), UI Automation + TextPattern candidates, OCR of the frozen frame | **Server** (`server/app/desktop.py`, Python; proven in the spike) | One place owns pixels and OS access; the client never ships pixels over HTTP except the frozen frame for display |
| Global hotkey, full-screen overlay showing the frozen frame, drawing (reuses `extension/geometry.js`), ask panel, clarify chips, tray | **Tauri app** (`desktop/`) | Chosen stack (Windows first, ports to macOS); thin shell over the server API |

## Server API (phase 4a)

- `POST /api/desktop/capture` → freezes the monitor under the cursor. Returns
  `{capture_id, monitor: {x, y, width, height}, image_data: "data:image/jpeg;base64,…"}`. The frame stays in memory
  (last 3 captures, 5 min TTL).
- `POST /api/desktop/candidates {capture_id, region: {x,y,width,height}, exclude_pids: []}` (region in monitor pixels)
  → `{candidates: CandidateObject[] (source uia | ocr), window: {app, process, title}}`. Reads the topmost windows under
  the region (z-order), skipping excluded pids (the overlay itself) and sensitive processes (password managers).
  Candidate bboxes are monitor-relative pixels.
- `Ask.capture_id` (v3): the server crops the frozen frame around the mark (28 px padding) and attaches it as the crop
  when the privacy policy allows — the client never re-uploads pixels.
- Windows-only: other platforms get `501 DESKTOP_UNSUPPORTED`. CORS additionally allows the Tauri origins
  (`tauri://localhost`, `http(s)://tauri.localhost`). Token rules unchanged.

**Coordinates:** desktop surface = the captured monitor in physical pixels, origin at its top-left; the server is
per-monitor DPI aware. The overlay converts CSS px × `devicePixelRatio`.

## Security (privacy review 2026-09-24)

- **Desktop token:** the server writes a per-launch secret to `%LOCALAPPDATA%\Spatial\desktop.token`; `/api/desktop/*`
  and any ask carrying `capture_id` need it in `X-Spatial-Desktop` (403 `DESKTOP_TOKEN` otherwise), even when
  `SPATIAL_API_TOKEN` is unset. The custom header forces a CORS preflight, which web origins fail. The Tauri app reads
  the file through a Rust command.
- **Host check:** `TrustedHostMiddleware` (`SPATIAL_ALLOWED_HOSTS`, default `127.0.0.1,localhost`) blocks DNS rebinding.
- **Sensitive windows:** z-order is snapshotted at capture. Every window visible under the region (topmost first,
  stopping at one that fully covers it) is checked; if any is a password manager (process list or title words), has an
  unreadable process name (elevated/protected — fails closed), or enumeration failed: no UIA, no OCR, no ask crop,
  blank title. UIA elements with `IsPassword` are skipped.
- Non-finite numbers are rejected (422); expired frames are swept on every capture/lookup.
- On-screen text under a mark goes into `anchors_used` and history, like page text in the extension.

## Tauri app (phase 4b)

- Global hotkey `Alt+Shift+S` → `capture` → full-screen, always-on-top, borderless overlay on that monitor showing the
  frozen frame; pen / box / point tools (geometry.js); Esc cancels.
- On mark: `candidates` → v3 ask via `/api/ask/stream` with `capture_id`; floating panel near the mark streams the
  answer, shows sources with ⚠, clarify chips re-ask with `target_id`.
- Tray: server status, open settings (server URL, token), quit. Overlay excludes itself from UIA reads by pid.

## Error handling

Server unreachable → overlay shows a one-line error; UIA failures → OCR-only candidates; capture failure → no overlay,
tray notification. Any desktop failure never blocks the browser extension path.

## Testing

Server: fake capture backend + fake UIA reader (pure functions over element dicts), endpoint shapes, exclusion, TTL,
crop-from-capture on ask, 501 off Windows. Tauri: `cargo build` + manual smoke (hotkey → draw → answer) recorded in
MEMORY.
