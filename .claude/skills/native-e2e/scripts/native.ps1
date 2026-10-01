# Helpers for native Spatial desktop checks on Windows. Dot-source:  . .claude/skills/native-e2e/scripts/native.ps1
# Rules baked in: DPI-aware captures (a DPI-unaware PowerShell crops PrintWindow output), kill test copies by EXACT
# exe path (never a user's installed copy), never print tokens.
$script:Exe = Join-Path (Resolve-Path "$PSScriptRoot\..\..\..\..").Path 'desktop\src-tauri\target\release\spatial-desktop.exe'

Add-Type -AssemblyName System.Drawing
Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte b, byte s, uint f, UIntPtr e);' -Name Keys -Namespace SpatialE2E
Add-Type @'
using System; using System.Text; using System.Collections.Generic; using System.Runtime.InteropServices;
public static class SpatialWin {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] static extern bool PrintWindow(IntPtr h, IntPtr dc, uint flags);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L,T,R,B; }
  public static List<string> Windows(uint pid) { var o = new List<string>(); EnumWindows((h,l) => { uint p; GetWindowThreadProcessId(h, out p); if (p == pid) { var sb = new StringBuilder(128); GetWindowText(h, sb, 128); RECT r; GetWindowRect(h, out r); if (sb.Length > 0) o.Add((IsWindowVisible(h) ? "VISIBLE " : "hidden ") + sb + " " + (r.R-r.L) + "x" + (r.B-r.T) + " @" + r.L + "," + r.T); } return true; }, IntPtr.Zero); return o; }
  public static IntPtr Find(uint pid, string title) { IntPtr f = IntPtr.Zero; EnumWindows((h,l) => { uint p; GetWindowThreadProcessId(h, out p); var sb = new StringBuilder(128); GetWindowText(h, sb, 128); if (p == pid && IsWindowVisible(h) && sb.ToString() == title) { f = h; return false; } return true; }, IntPtr.Zero); return f; }
  public static RECT Rect(IntPtr h) { RECT r; GetWindowRect(h, out r); return r; }
  public static bool PrintTo(IntPtr h, IntPtr dc) { return PrintWindow(h, dc, 2); }
}
'@
Add-Type -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y); [DllImport("user32.dll")] public static extern void mouse_event(uint f, uint dx, uint dy, uint d, UIntPtr e); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);' -Name Mouse -Namespace SpatialE2E
[void][SpatialWin]::SetProcessDPIAware()

function Start-SpatialTest([switch]$Visible) {
  # Default is tray-only (--autostart) so the dashboard stays hidden; -Visible opens it like a normal launch.
  if ($Visible) { $p = Start-Process $script:Exe -PassThru } else { $p = Start-Process $script:Exe -ArgumentList '--autostart' -PassThru }
  Start-Sleep 12   # the bundled server needs a few seconds
  return $p
}

function Send-Keys([byte[]]$Keys) {  # e.g. Send-Keys 0x12,0x10,0x53  (Alt+Shift+S)
  foreach ($k in $Keys) { [SpatialE2E.Keys]::keybd_event($k, 0, 0, [UIntPtr]::Zero) }
  Start-Sleep -Milliseconds 120
  [array]::Reverse($Keys)
  foreach ($k in $Keys) { [SpatialE2E.Keys]::keybd_event($k, 0, 2, [UIntPtr]::Zero) }
}

function Get-SpatialWindows($ProcessId) { [SpatialWin]::Windows([uint32]$ProcessId) }

function Save-SpatialWindow($ProcessId, [string]$Title, [string]$Path) {
  $h = [SpatialWin]::Find([uint32]$ProcessId, $Title)
  if ($h -eq [IntPtr]::Zero) { return $false }
  $r = [SpatialWin]::Rect($h)
  $bmp = New-Object System.Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T)
  $g = [System.Drawing.Graphics]::FromImage($bmp); $dc = $g.GetHdc()
  $ok = [SpatialWin]::PrintTo($h, $dc); $g.ReleaseHdc($dc); $g.Dispose()
  if ($ok) { $bmp.Save($Path) }
  $bmp.Dispose(); return $ok
}

function Click-SpatialWindow($ProcessId, [string]$Title, [int]$X, [int]$Y) {
  # X,Y are pixels inside the window as seen in a Save-SpatialWindow capture (DPI-aware, window top-left = 0,0).
  $h = [SpatialWin]::Find([uint32]$ProcessId, $Title)
  if ($h -eq [IntPtr]::Zero) { return $false }
  [void][SpatialE2E.Mouse]::SetForegroundWindow($h); Start-Sleep -Milliseconds 300
  $r = [SpatialWin]::Rect($h)
  [void][SpatialE2E.Mouse]::SetCursorPos($r.L + $X, $r.T + $Y); Start-Sleep -Milliseconds 150
  [SpatialE2E.Mouse]::mouse_event(0x0002, 0, 0, 0, [UIntPtr]::Zero); Start-Sleep -Milliseconds 80   # left down
  [SpatialE2E.Mouse]::mouse_event(0x0004, 0, 0, 0, [UIntPtr]::Zero)                                 # left up
  return $true
}

function Scroll-SpatialWindow($ProcessId, [string]$Title, [int]$X, [int]$Y, [int]$Notches = -5) {
  # Mouse wheel over capture coordinates X,Y; negative notches scroll down.
  $h = [SpatialWin]::Find([uint32]$ProcessId, $Title)
  if ($h -eq [IntPtr]::Zero) { return $false }
  $r = [SpatialWin]::Rect($h)
  [void][SpatialE2E.Mouse]::SetCursorPos($r.L + $X, $r.T + $Y); Start-Sleep -Milliseconds 150
  $delta = [BitConverter]::ToUInt32([BitConverter]::GetBytes([int]($Notches * 120)), 0)
  [SpatialE2E.Mouse]::mouse_event(0x0800, 0, 0, $delta, [UIntPtr]::Zero)
  Start-Sleep -Milliseconds 400
  return $true
}

function Get-SpatialHeaders {  # auth headers for the local server; values are never printed
  $base = Join-Path $env:LOCALAPPDATA 'Spatial'
  @{ Authorization = 'Bearer ' + (Get-Content "$base\api.token" -Raw).Trim(); 'X-Spatial-Desktop' = (Get-Content "$base\desktop.token" -Raw).Trim(); 'Content-Type' = 'application/json' }
}

function Stop-SpatialTest {  # only the release test exe and ITS bundled server; never an installed copy
  Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $script:Exe } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep 3
  Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'spatial-server.exe' -and $_.ExecutablePath -like '*src-tauri\target\release*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
  Start-Sleep 2
  'remaining test processes: ' + @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $script:Exe }).Count
}
