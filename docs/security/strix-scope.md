# Spatial security assessment scope

Assess only the supplied sanitized copy of the Spatial source. Do not scan third-party providers, public
websites, the host network, or the user's running desktop applications. Do not use real provider keys,
screenshots, history databases, trace logs, or microphone recordings. Build proof-of-concept tests with
synthetic fixtures and temporary data. Findings must include a reproducible example and affected file/line.
Do not alter the original checkout; proposed fixes belong in the report or the scan copy.

Cover:

- FastAPI bearer authentication, desktop-token checks, CORS, Host validation, protocol validation,
  context access, capture identifiers, rate/resource limits, and file handling.
- SSRF and unsafe redirects in research fetching; untrusted provider/search responses; error leakage.
- Extension message boundaries, DOM XSS, unsafe URL handling, consent, screenshot/microphone privacy,
  storage of credentials, and blocked-site behavior.
- Tauri IPC/capabilities/CSP, browser opener URLs, bundled process lifecycle, pairing tokens, autostart,
  installer resources, and data-directory isolation.
- Trace scrubbing/export/deletion, OCR input handling, concurrency, dependency and supply-chain risks.

Use the server's test suite as the starting point. Run the app in the sandbox only, with providers, speech
warm-up, OCR warm-up, and System One disabled, a temporary database, and synthetic tokens. Never contact
paid provider endpoints. Explicitly distinguish validated vulnerabilities, suspected issues, and uncovered
areas. State limitations for Windows UIA/Tauri behavior that a Linux sandbox cannot validate.

This assessment covers security; it does not replace functional, accessibility, performance, installer,
multi-monitor, or macOS validation.
