# Signing the Windows release

Unsigned installers trigger Windows SmartScreen ("Windows protected your PC") and antivirus suspicion, which is the single
biggest trust hurdle for a tool that sees your screen. The release pipeline can sign; it needs a code-signing certificate
that only you can obtain.

## What is already built

- `desktop/sign.ps1` — `Sign-SpatialFile`: Authenticode signing with PowerShell's built-in `Set-AuthenticodeSignature`
  (no Windows SDK needed). **Opt-in**: with no certificate configured it prints `UNSIGNED: <file>` and the build continues.
- `desktop/sign-one.ps1` — the wrapper Tauri calls (`bundle.windows.signCommand` in `tauri.release.conf.json`) for every
  binary and the installer it produces.
- `desktop/build-release.ps1` — also signs the bundled `spatial-server.exe` before it is packed, and the finished installer.
- Tested 2026-10-01 with a throwaway self-signed certificate: signer embedded, wrong thumbprint fails loudly, unsigned mode
  warns. (A self-signed signature is *not* trusted by Windows; only the pipeline was verified.)

## Use it once you have a certificate

Install the certificate (with its private key) into your Windows certificate store, then:

```powershell
$env:SPATIAL_SIGN_THUMBPRINT = '<thumbprint>'            # CurrentUser\My or LocalMachine\My
$env:SPATIAL_SIGN_TIMESTAMP  = 'http://timestamp.digicert.com'   # optional; default shown; 'none' only for tests
powershell -File desktop/build-release.ps1
Get-AuthenticodeSignature desktop\src-tauri\target\release\bundle\nsis\*-setup.exe   # expect Status: Valid
```

Never commit a certificate or password. The thumbprint is not a secret; the private key stays in the store.

## Getting a certificate (decide with current information)

I cannot verify today's programs, prices or eligibility; check each before buying.

| Option | Notes |
|---|---|
| Cloud signing service (e.g. Microsoft's Trusted Signing / similar) | Usually the cheapest and simplest for a small team; no hardware token. Check whether individuals or only registered organizations are eligible in your country. May need a different `signCommand` (their client tool) instead of `sign.ps1`. |
| OV (organization-validated) code-signing certificate | Widely available. SmartScreen reputation builds up over downloads, so early installs may still see a warning. |
| EV (extended-validation) certificate | Stricter vetting, hardware-token based. Historically gave faster SmartScreen reputation; verify that this still holds. |

Whichever you pick, SmartScreen reputation is earned over time: expect warnings to fade as more people install the same
signed file. Keep the publisher name stable.

## Known gaps

- Auto-update, a stable download page and release notes are not built; an installer without a trusted publisher name will
  keep a "More info → Run anyway" step until reputation exists. The user-test guide (`docs/USER_TEST.md`) covers that step.
- The `signCommand` entry in `tauri.release.conf.json` was added without a trusted certificate to test it end to end; the
  first signed build should be checked with `Get-AuthenticodeSignature` on both the installer and the installed
  `spatial-desktop.exe`.
