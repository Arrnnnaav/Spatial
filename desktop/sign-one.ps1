# Called by Tauri (bundle.windows.signCommand) for every binary and the installer it produces. No-op with a warning
# unless SPATIAL_SIGN_THUMBPRINT is set (see sign.ps1 and docs/SIGNING.md).
param([Parameter(Mandatory)][string]$Path)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'sign.ps1')
    [void](Sign-SpatialFile $Path)
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
exit 0
