// Spatial desktop shell: global hotkey + tray. The server owns capture, UI Automation and answering;
// this app only shows the frozen frame, lets the user draw, and shows the answer (see docs/ARCHITECTURE.md).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{Menu, MenuItem};
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, WindowEvent};
use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

const HOTKEY_LABEL: &str = "Alt+Shift+S";

/// The overlay passes this to /api/desktop/candidates so the server never reads Spatial's own windows.
#[tauri::command]
fn own_pid() -> u32 {
    std::process::id()
}

/// Per-launch secret the local server writes (server/app/desktop.py::session_token). Web pages cannot read files,
/// so only this app can call the screen-capture routes.
#[tauri::command]
fn desktop_token() -> Result<String, String> {
    let base = std::env::var("LOCALAPPDATA").map_err(|_| "LOCALAPPDATA not set".to_string())?;
    let path = std::path::Path::new(&base).join("Spatial").join("desktop.token");
    std::fs::read_to_string(&path)
        .map(|s| s.trim().to_string())
        .map_err(|_| "Spatial server not started yet (no desktop token)".to_string())
}

fn start_ask(app: &tauri::AppHandle) {
    let _ = app.emit_to("overlay", "spatial://start", ());
}

fn main() {
    let hotkey = Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyS);
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &hotkey && event.state() == ShortcutState::Pressed {
                        start_ask(app);
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![own_pid, desktop_token])
        .setup(move |app| {
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            if let Err(err) = app.global_shortcut().register(hotkey) {
                eprintln!("could not register {HOTKEY_LABEL}: {err} (another app owns it?) — use the tray");
            }
            let ask = MenuItem::with_id(app, "ask", format!("Ask about the screen ({HOTKEY_LABEL})"), true, None::<&str>)?;
            let settings = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Spatial", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&ask, &settings, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().expect("bundle icon"))
                .tooltip(format!("Spatial — {HOTKEY_LABEL} to point & ask"))
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "ask" => start_ask(app),
                    "settings" => {
                        let _ = app.emit_to("panel", "spatial://settings", ());
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing a window only hides it: the app lives in the tray until Quit.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Spatial");
}
