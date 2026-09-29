# Spatial desktop (Tauri v2, Windows first)

Press **Alt+Shift+S** anywhere → the screen freezes → circle / box (**B**) / point (**P**) what you mean → ask in the
panel that opens beside it. **Esc** cancels. The tray has Ask, Open Spatial, Snooze Ask shortcut, Settings, Start server,
Dictate, and Quit. Snooze applies until Spatial restarts; tray Ask remains available.

**Dictate** uses **Alt+Shift+D** (hold and release to finish, tap to toggle; **Esc** cancels) or the composer button.
It places editable text in Spatial's Ask composer; Ask remains a separate explicit action. Dictation uses `/api/stt`;
spoken punctuation, list/restart cleanup and the personal dictionary run locally. Optional polish is off by default and
sends transcript text only to the configured answer provider. An on-demand `.docx` download is available from the
composer. No dictation audio or transcript history is saved. This beta does not include SayStride models or meeting
capture.

The panel's **Status** view reports server, configured answer provider, speech backend and shortcut state. Recent
activity keeps up to 40 event categories and timestamps locally; it never stores prompts, answers, screenshots,
transcripts, credentials or URLs. Clear activity removes the list. Copy diagnostics copies status and event categories.

Ask only explains marked content. Dictate is a separate explicit text-insertion action. The local server (`server/`, `uvicorn app.main:app --port 8787`) owns screen capture,
UI Automation reading and answering (`server/app/desktop.py`, spec `docs/superpowers/specs/2026-09-24-desktop-app-design.md`).

## Build and run

```bash
# prerequisites: Rust (rustup, MSVC toolchain), WebView2 (ships with Windows 11)
cd desktop/src-tauri
cargo build                     # debug build -> target/debug/spatial-desktop.exe
cargo build --release           # release build, no console window
```

Start the server first: it writes the per-launch desktop token (`%LOCALAPPDATA%\Spatial\desktop.token`) that the app
must send on every screen route. After restarting the server, the next ask picks up the new token automatically.

For a Windows installer, install the Tauri CLI once (`cargo install tauri-cli --version '^2' --locked`), then run
`powershell -File desktop/build-release.ps1` from the repository root. The script builds a bundled server and an
NSIS installer in `desktop/src-tauri/target/release/bundle/nsis/`. The installed app starts its own server. Provider
keys can be placed in `%LOCALAPPDATA%\Spatial\server.env`; history stays in that directory as `spatial.db`.
The bundled server creates a random API token in `%LOCALAPPDATA%\Spatial\api.token`; the desktop app reads it
automatically. To connect the browser extension, open desktop Settings, copy the pairing token, and paste it into
the extension popup's API token field. The token is not sent to a web page.
When paired, a desktop mark over Chrome uses DOM text and links from the captured tab where available. A blocked or
unidentifiable tab is protected; a safe tab with no DOM result falls back to Windows UI Automation and OCR.
Read-aloud uses the server voice when available and the Windows system voice in WebView2 otherwise.

## Layout

```
src-tauri/src/main.rs   hotkey, tray, commands own_pid + desktop_token + pairing_token; closing windows only hides them
src-tauri/build.rs      copies extension/geometry.js into ui/ (one geometry for extension, desktop and resolver parity)
ui/overlay.*            frozen-frame overlay: draw, then hide BEFORE the panel asks for candidates
ui/panel.*              candidates -> /api/ask/stream (v3, capture_id), sources ⚠, "Did you mean" chips, settings
ui/shared.js            server URL, token headers, JSON POST
```

Settings (server URL, custom-server API token, web verification, TypeSafe opt-in, autostart) live in the app's localStorage.
