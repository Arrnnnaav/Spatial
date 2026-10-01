// Spatial desktop shell: global hotkey + tray. The server owns capture, UI Automation and answering;
// this app only shows the frozen frame, lets the user draw, and shows the answer (see docs/ARCHITECTURE.md).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::menu::{Menu, MenuItem};
#[cfg(windows)]
use tauri::path::BaseDirectory;
use tauri::tray::TrayIconBuilder;
use tauri::{Emitter, Manager, WindowEvent};
use tauri_plugin_global_shortcut::{Code, Modifiers, Shortcut, ShortcutState};

const HOTKEY_LABEL: &str = "Alt+Shift+S";
const DICTATION_HOTKEY_LABEL: &str = "Alt+Shift+D";
static ASK_SNOOZED: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
static DICTATION_ACTIVE: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);
const MAX_NOTICES: usize = 5;
static STARTUP_NOTICE: std::sync::Mutex<Vec<String>> = std::sync::Mutex::new(Vec::new());

/// Keep every distinct startup problem (newest last, capped) so a later hotkey error cannot hide a server error.
fn push_notice(list: &mut Vec<String>, message: String) {
    if list.contains(&message) { return; }
    list.push(message);
    if list.len() > MAX_NOTICES { list.remove(0); }
}

#[tauri::command]
fn startup_notice() -> Vec<String> {
    STARTUP_NOTICE.lock().map(|notices| notices.clone()).unwrap_or_default()
}

#[tauri::command]
fn set_dictation_active(app: tauri::AppHandle, active: bool) -> Result<(), String> {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    let escape = Shortcut::new(None, Code::Escape);
    let shortcuts = app.global_shortcut();
    if active {
        shortcuts.register(escape).map_err(|err| err.to_string())?;
        DICTATION_ACTIVE.store(true, std::sync::atomic::Ordering::Relaxed);
    } else {
        DICTATION_ACTIVE.store(false, std::sync::atomic::Ordering::Relaxed);
        let _ = shortcuts.unregister(escape);
    }
    Ok(())
}

#[cfg(windows)]
#[tauri::command]
fn foreground_target() -> Option<u64> {
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};
    let hwnd = unsafe { GetForegroundWindow() };
    if hwnd.0.is_null() { return None; }
    let mut pid = 0;
    unsafe { GetWindowThreadProcessId(hwnd, Some(&mut pid)); }
    (pid != std::process::id()).then_some(hwnd.0 as usize as u64)
}

#[cfg(windows)]
#[tauri::command]
fn paste_dictation(target_hwnd: u64, text: String) -> Result<(), String> {
    use windows::Win32::Foundation::HWND;
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE,
        VIRTUAL_KEY,
    };
    use windows::Win32::UI::WindowsAndMessaging::GetForegroundWindow;
    if text.is_empty() || text.encode_utf16().count() > 12000 { return Err("Dictation text is empty or too long".into()); }
    let target = HWND(target_hwnd as usize as *mut _);
    if unsafe { GetForegroundWindow() } != target { return Err("Focus changed; dictation was not inserted".into()); }
    let mut inputs = Vec::with_capacity(text.encode_utf16().count() * 2);
    for unit in text.encode_utf16() {
        for flags in [KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP] {
            inputs.push(INPUT {
                r#type: INPUT_KEYBOARD,
                Anonymous: INPUT_0 { ki: KEYBDINPUT { wVk: VIRTUAL_KEY(0), wScan: unit, dwFlags: flags, ..Default::default() } },
            });
        }
    }
    let sent = unsafe { SendInput(&inputs, std::mem::size_of::<INPUT>() as i32) };
    if sent != inputs.len() as u32 { return Err("Windows rejected text insertion".into()); }
    Ok(())
}

#[cfg(not(windows))]
#[tauri::command]
fn foreground_target() -> Option<u64> { None }

#[cfg(not(windows))]
#[tauri::command]
fn paste_dictation(_target_hwnd: u64, _text: String) -> Result<(), String> {
    Err("Dictation insertion is available on Windows only".into())
}

#[cfg(windows)]
fn start_server(app: &tauri::AppHandle) -> Result<(), String> {
    use std::os::windows::process::CommandExt;
    let state = app.state::<std::sync::Mutex<Option<std::process::Child>>>();
    let mut child = state.lock().map_err(|_| "server process lock failed")?;
    if let Some(process) = child.as_mut() {
        if process.try_wait().map_err(|e| e.to_string())?.is_none() {
            return Ok(());
        }
    }
    let path = app.path().resolve("resources/spatial-server/spatial-server.exe", BaseDirectory::Resource)
        .map_err(|e| e.to_string())?;
    if !path.is_file() {
        return Err("bundled server missing; start the development server manually".into());
    }
    let process = std::process::Command::new(path)
        .creation_flags(0x08000000) // CREATE_NO_WINDOW
        .spawn().map_err(|e| e.to_string())?;
    *child = Some(process);
    Ok(())
}

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

/// Token for pairing the browser extension with the bundled loopback server.
#[tauri::command]
fn pairing_token() -> Result<String, String> {
    let base = std::env::var("LOCALAPPDATA").map_err(|_| "LOCALAPPDATA not set".to_string())?;
    let path = std::path::Path::new(&base).join("Spatial").join("api.token");
    std::fs::read_to_string(&path)
        .map(|s| s.trim().to_string())
        .map_err(|_| "Bundled server has not created a pairing token yet".to_string())
}

/// WebView2 asks "tauri.localhost wants to use your microphones" on every launch and does not remember "Allow".
/// Grant it here instead — microphone only, and only to our own bundled pages (the CSP already blocks remote content).
#[cfg(windows)]
fn allow_own_microphone(window: &tauri::WebviewWindow) {
    let _ = window.with_webview(|webview| unsafe {
        use webview2_com::Microsoft::Web::WebView2::Win32::{
            COREWEBVIEW2_PERMISSION_KIND, COREWEBVIEW2_PERMISSION_KIND_MICROPHONE, COREWEBVIEW2_PERMISSION_STATE_ALLOW,
        };
        use webview2_com::{take_pwstr, PermissionRequestedEventHandler};
        let Ok(core) = webview.controller().CoreWebView2() else {
            return;
        };
        let handler = PermissionRequestedEventHandler::create(Box::new(|_, args| {
            if let Some(args) = args {
                let mut kind = COREWEBVIEW2_PERMISSION_KIND::default();
                args.PermissionKind(&mut kind)?;
                let mut uri = windows_core::PWSTR::null();
                args.Uri(&mut uri)?;
                let uri = take_pwstr(uri);
                let own = uri.starts_with("http://tauri.localhost/") || uri.starts_with("https://tauri.localhost/");
                if kind == COREWEBVIEW2_PERMISSION_KIND_MICROPHONE && own {
                    args.SetState(COREWEBVIEW2_PERMISSION_STATE_ALLOW)?;
                }
            }
            Ok(())
        }));
        let mut token = 0i64;
        let _ = core.add_PermissionRequested(&handler, &mut token);
    });
}

fn show_dashboard(app: &tauri::AppHandle, view: &str) {
    if let Some(dashboard) = app.get_webview_window("dashboard") {
        let _ = dashboard.show();
        let _ = dashboard.unminimize();
        let _ = dashboard.set_focus();
    }
    let _ = app.emit_to("dashboard", "spatial://open", serde_json::json!({ "view": view }));
}

/// App-level problems (server start, hotkey ownership, autostart) belong in Settings, never in the Ask panel.
fn notify(app: &tauri::AppHandle, message: String) {
    if let Ok(mut current) = STARTUP_NOTICE.lock() { push_notice(&mut current, message.clone()); }
    let _ = app.emit_to("dashboard", "spatial://notice", serde_json::json!({ "message": message }));
}

fn start_ask(app: &tauri::AppHandle) {
    let _ = app.emit_to("overlay", "spatial://start", ());
}

/// Hotkey/tray dictation goes straight to the app that had focus (no screen marking, no Ask panel).
/// The Ask panel's own Dictate button still targets its composer.
fn dictation_payload(target: Option<u64>) -> serde_json::Value {
    serde_json::json!({"target_hwnd": target.unwrap_or(0), "destination": "external"})
}

fn start_dictation(app: &tauri::AppHandle) {
    // Capture the foreground window before any Spatial UI appears.
    let _ = app.emit_to("dictate", "spatial://dictate-down", dictation_payload(foreground_target()));
}

fn main() {
    let hotkey = Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyS);
    let dictate_hotkey = Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::KeyD);
    let escape_hotkey = Shortcut::new(None, Code::Escape);
    tauri::Builder::default()
        // Must be first: prevent duplicate processes from competing for global hotkeys/server ownership.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            show_dashboard(app, "home");
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec!["--autostart"])))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &hotkey && event.state() == ShortcutState::Pressed
                        && !ASK_SNOOZED.load(std::sync::atomic::Ordering::Relaxed) {
                        start_ask(app);
                    }
                    if shortcut == &dictate_hotkey {
                        if event.state() == ShortcutState::Pressed { start_dictation(app); }
                        if event.state() == ShortcutState::Released { let _ = app.emit_to("dictate", "spatial://dictate-up", ()); }
                    }
                    if shortcut == &escape_hotkey && DICTATION_ACTIVE.load(std::sync::atomic::Ordering::Relaxed)
                        && event.state() == ShortcutState::Pressed {
                        let _ = app.emit_to("dictate", "spatial://dictate-cancel", ());
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![own_pid, desktop_token, pairing_token, startup_notice, foreground_target, paste_dictation, set_dictation_active])
        .setup(move |app| {
            use tauri_plugin_global_shortcut::GlobalShortcutExt;
            #[cfg(windows)]
            {
                app.manage(std::sync::Mutex::new(None::<std::process::Child>));
                if let Err(err) = start_server(app.handle()) {
                    notify(app.handle(), format!("Server: {err}"));
                }
            }
            #[cfg(windows)]
            if let Some(panel) = app.get_webview_window("panel") {
                allow_own_microphone(&panel);
            }
            #[cfg(windows)]
            if let Some(dictate) = app.get_webview_window("dictate") {
                allow_own_microphone(&dictate);
            }
            if let Err(err) = app.global_shortcut().register(hotkey) {
                eprintln!("could not register {HOTKEY_LABEL}: {err} (another app owns it?) — use the tray");
                notify(app.handle(), format!("Shortcut {HOTKEY_LABEL} unavailable. Use Ask from the tray. {err}"));
            }
            if let Err(err) = app.global_shortcut().register(dictate_hotkey) {
                notify(app.handle(), format!("Dictate shortcut {DICTATION_HOTKEY_LABEL} unavailable. Use the Dictate button or tray. {err}"));
            }
            let ask = MenuItem::with_id(app, "ask", format!("Ask about the screen ({HOTKEY_LABEL})"), true, None::<&str>)?;
            let dictate = MenuItem::with_id(app, "dictate", format!("Dictate ({DICTATION_HOTKEY_LABEL})"), true, None::<&str>)?;
            let open = MenuItem::with_id(app, "open", "Open Spatial", true, None::<&str>)?;
            let snooze = MenuItem::with_id(app, "snooze", "Snooze Ask shortcut", true, None::<&str>)?;
            let settings = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
            let server = MenuItem::with_id(app, "server", "Start server", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Quit Spatial", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&ask, &dictate, &open, &snooze, &settings, &server, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().cloned().expect("bundle icon"))
                .tooltip(format!("Spatial — {HOTKEY_LABEL} to point & ask"))
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "ask" => start_ask(app),
                    "dictate" => start_dictation(app),
                    "open" => show_dashboard(app, "home"),
                    "snooze" => { ASK_SNOOZED.store(true, std::sync::atomic::Ordering::Relaxed); let _ = app.emit_to("dashboard", "spatial://snooze", ()); },
                    "settings" => show_dashboard(app, "settings"),
                    #[cfg(windows)]
                    "server" => {
                        if let Err(err) = start_server(app) {
                            notify(app, format!("Server: {err}"));
                            show_dashboard(app, "settings");
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            // A normal launch opens the dashboard; sign-in autostart stays in the tray.
            if !std::env::args().any(|arg| arg == "--autostart") {
                show_dashboard(app.handle(), "home");
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // Closing a window only hides it: the app lives in the tray until Quit.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Spatial")
        .run(|app, event| {
            #[cfg(windows)]
            if let tauri::RunEvent::Exit = event {
                if let Ok(mut child) = app.state::<std::sync::Mutex<Option<std::process::Child>>>().lock() {
                    if let Some(mut process) = child.take() {
                        // PyInstaller onefile launches a child after extraction. Stop that process tree too.
                        if process.try_wait().ok().flatten().is_none() {
                            use std::os::windows::process::CommandExt;
                            let pid = process.id().to_string();
                            let _ = std::process::Command::new("taskkill")
                                .args(["/PID", pid.as_str(), "/T", "/F"])
                                .creation_flags(0x08000000)
                                .status();
                            let _ = process.kill();
                        }
                        let _ = process.wait();
                    }
                }
            }
            #[cfg(not(windows))]
            let _ = (app, event);
        });
}

#[cfg(test)]
mod tests {
    use super::{dictation_payload, push_notice};

    #[test]
    fn hotkey_dictation_targets_the_foreground_app_and_never_the_ask_composer() {
        let with_target = dictation_payload(Some(4242));
        assert_eq!(with_target["destination"], "external");
        assert_eq!(with_target["target_hwnd"], 4242);
        let without = dictation_payload(None);
        assert_eq!(without["destination"], "external");
        assert_eq!(without["target_hwnd"], 0);
    }

    #[test]
    fn startup_notices_keep_every_distinct_message_up_to_a_cap() {
        let mut list = Vec::new();
        push_notice(&mut list, "Server: failed".into());
        push_notice(&mut list, "Shortcut taken".into());
        push_notice(&mut list, "Shortcut taken".into());
        assert_eq!(list, vec!["Server: failed", "Shortcut taken"]);
        for n in 0..10 { push_notice(&mut list, format!("n{n}")); }
        assert_eq!(list.len(), 5);
        assert_eq!(list.last().unwrap(), "n9");
    }
}
