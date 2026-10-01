# Authenticode signing helper for the Windows release. Dot-source it:  . desktop/sign.ps1
#
# Signing is OPT-IN so an unsigned developer build still works:
#   $env:SPATIAL_SIGN_THUMBPRINT = '<certificate thumbprint in Cert:\CurrentUser\My or LocalMachine\My>'
#   $env:SPATIAL_SIGN_TIMESTAMP  = 'http://timestamp.digicert.com'   # default; 'none' skips timestamping (tests only)
# The certificate and its private key stay in the Windows certificate store; nothing secret is read from files here.

function Get-SpatialSigningCertificate {
    $thumbprint = ($env:SPATIAL_SIGN_THUMBPRINT -replace '\s', '').ToUpperInvariant()
    if (-not $thumbprint) { return $null }
    foreach ($store in 'Cert:\CurrentUser\My', 'Cert:\LocalMachine\My') {
        $cert = Get-ChildItem $store -ErrorAction SilentlyContinue | Where-Object { $_.Thumbprint -eq $thumbprint } | Select-Object -First 1
        if ($cert) { return $cert }
    }
    throw "SPATIAL_SIGN_THUMBPRINT is set but no certificate with that thumbprint is in the CurrentUser or LocalMachine store"
}

function Sign-SpatialFile([Parameter(Mandatory)][string]$Path) {
    $cert = Get-SpatialSigningCertificate
    if (-not $cert) {
        Write-Warning "UNSIGNED: $(Split-Path $Path -Leaf) (set SPATIAL_SIGN_THUMBPRINT to sign; see docs/SIGNING.md)"
        return $false
    }
    if (-not $cert.HasPrivateKey) { throw 'The signing certificate has no private key in this store' }
    $timestamp = if ($env:SPATIAL_SIGN_TIMESTAMP) { $env:SPATIAL_SIGN_TIMESTAMP } else { 'http://timestamp.digicert.com' }
    $args = @{ FilePath = $Path; Certificate = $cert; HashAlgorithm = 'SHA256' }
    if ($timestamp -ne 'none') { $args.TimestampServer = $timestamp }
    $result = Set-AuthenticodeSignature @args
    if (-not $result.SignerCertificate -or $result.Status -eq 'HashMismatch') {
        throw "Signing failed for ${Path}: $($result.Status) $($result.StatusMessage)"
    }
    Write-Host "Signed $(Split-Path $Path -Leaf) as '$($cert.Subject)' ($($result.Status))"
    return $true
}
