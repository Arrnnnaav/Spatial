$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$builder = Join-Path $PSScriptRoot '.build-venv\Scripts\python.exe'
$server = Join-Path $project 'server'
$tauri = Join-Path $PSScriptRoot 'src-tauri'
. (Join-Path $PSScriptRoot 'sign.ps1')   # Sign-SpatialFile: opt-in Authenticode signing (docs/SIGNING.md)

if (-not (Test-Path -LiteralPath $builder)) {
    python -m venv (Join-Path $PSScriptRoot '.build-venv')
}
& $builder -m pip install -r (Join-Path $server 'requirements.txt') pyinstaller mss pywin32 comtypes pillow numpy rapidocr-onnxruntime faster-whisper
if ($LASTEXITCODE -ne 0) { throw 'Could not install release dependencies' }

Push-Location $PSScriptRoot
try {
    & $builder -m PyInstaller --noconfirm --name spatial-server --paths $server `
        --collect-submodules app --collect-submodules uvicorn --collect-all faster_whisper --collect-all ctranslate2 `
        --collect-all av --collect-all rapidocr_onnxruntime `
        --collect-all riva (Join-Path $server 'run_desktop.py')
    if ($LASTEXITCODE -ne 0) { throw 'Server packaging failed' }
    $serverResource = Join-Path $tauri 'resources\spatial-server'
    $tauriPath = [System.IO.Path]::GetFullPath($tauri) + [System.IO.Path]::DirectorySeparatorChar
    $serverResourcePath = [System.IO.Path]::GetFullPath($serverResource)
    if (-not $serverResourcePath.StartsWith($tauriPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to clear a server resource path outside the Tauri project'
    }
    if (Test-Path -LiteralPath $serverResourcePath) {
        Remove-Item -LiteralPath $serverResourcePath -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $serverResourcePath | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'dist\spatial-server') |
        Copy-Item -Destination $serverResourcePath -Recurse -Force

    # Sign the bundled server before it is packed into the installer.
    [void](Sign-SpatialFile (Join-Path $serverResourcePath 'spatial-server.exe'))

    Push-Location $tauri
    try {
        cargo tauri build --config tauri.release.conf.json
        if ($LASTEXITCODE -ne 0) { throw 'Tauri installer build failed' }
        # The installer is what users download (and what SmartScreen inspects).
        Get-ChildItem (Join-Path $tauri 'target\release\bundle\nsis') -Filter '*-setup.exe' | ForEach-Object { [void](Sign-SpatialFile $_.FullName) }
    } finally { Pop-Location }
} finally { Pop-Location }
