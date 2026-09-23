# Spatial desktop (Tauri v2, Windows first)

Press **Alt+Shift+S** anywhere → the screen freezes → circle / box (**B**) / point (**P**) what you mean → ask in the
panel that opens beside it. **Esc** cancels. The tray icon has Ask, Settings and Quit.

The app only draws and asks. The local server (`server/`, `uvicorn app.main:app --port 8787`) owns screen capture,
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

## Layout

```
src-tauri/src/main.rs   hotkey, tray, commands own_pid + desktop_token; closing windows only hides them
src-tauri/build.rs      copies extension/geometry.js into ui/ (one geometry for extension, desktop and resolver parity)
ui/overlay.*            frozen-frame overlay: draw, then hide BEFORE the panel asks for candidates
ui/panel.*              candidates -> /api/ask/stream (v3, capture_id), sources ⚠, "Did you mean" chips, settings
ui/shared.js            server URL, token headers, JSON POST
```

Settings (server URL, optional API token, web verification) live in the app's localStorage.
