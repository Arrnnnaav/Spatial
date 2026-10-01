---
name: native-e2e
description: Drive the built Spatial Windows desktop app (release exe) to verify a change natively - launch tray-only, send hotkeys, list/capture windows, call the local API, then clean up. Use after changing desktop UI, Tauri config/capabilities, hotkeys, tray, reminders, dictation or recall, once a release build exists.
disable-model-invocation: true
---

# Native E2E for the Spatial desktop app

Needs `desktop/src-tauri/target/release/spatial-desktop.exe` (run `powershell -File desktop/build-release.ps1` first; roughly 10-20 min). Use the PowerShell tool.

```powershell
. .claude/skills/native-e2e/scripts/native.ps1          # helpers (DPI-aware, exact-path cleanup)
$app = Start-SpatialTest                                  # tray-only like sign-in autostart; -Visible opens the dashboard
Get-SpatialWindows $app.Id                                # VISIBLE/hidden per window
Send-Keys 0x12,0x10,0x48                                  # Alt+Shift+H (S=0x53 ask, D=0x44 dictate, Esc=0x1B, Enter=0x0D)
Save-SpatialWindow $app.Id 'Spatial Recall' "$env:TEMP\recall.png"   # then Read the PNG to look at it
Click-SpatialWindow $app.Id 'Spatial' 74 294              # click at capture coordinates (here: dashboard "Settings" nav)
Scroll-SpatialWindow $app.Id 'Spatial' 700 500 -8         # mouse wheel at capture coordinates; negative scrolls down
$h = Get-SpatialHeaders                                   # for Invoke-RestMethod against http://127.0.0.1:8787
Stop-SpatialTest                                          # ALWAYS finish with this
```

Window titles: `Spatial` (dashboard), `Spatial overlay`, `Spatial Dictation`, `Spatial Reminder`, `Spatial Recall`.

## Checks that have been used (expected results)
- Normal launch: dashboard visible, Home cards populated. Second launch: exits, one process remains, dashboard focused.
- `--autostart`: every window hidden. `Alt+Shift+S`: overlay appears, Esc hides. `Alt+Shift+D`: only the dictation pill (no Ask panel).
- Hotkey conflict: hold the key from another process (RegisterHotKey) before launch, then Settings shows a red `!` and the Home card says "Unavailable".
- Reminder: POST `/api/reminders` due in about 20 s (`due_at` as ISO with timezone); the popup appears within about 15 s with the dashboard hidden.
- Recall: POST `/api/dictations`, press `Alt+Shift+H`, press Enter; the clipboard equals the text and the window hides.

## Rules
- Test data goes into the real profile (`%LOCALAPPDATA%\Spatial`): delete what you create (DELETE routes) before finishing.
- Never kill a process by name alone; `Stop-SpatialTest` matches the exact release exe path. If a copy from `desktop/install-smoke` or an installed copy is running, ask first.
- Do not print token values. Do not Read `api.token` or `desktop.token` (the hook blocks it); use `Get-SpatialHeaders`.
- Real speech into another app and tray-menu clicks cannot be automated this way; say so in the report.
