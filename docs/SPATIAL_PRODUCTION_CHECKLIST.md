# Spatial release checklist

**Updated:** 2026-09-28. This is the release gate for the Chrome extension, local FastAPI server, and Windows desktop app. The long-horizon ideas live in `SPATIAL_STANDALONE_MASTER_PLAN.md`; implementation status lives in `TASKS.md`.

## Automated checks

- [x] `cd server && python -m pytest -q` passes with no skipped tests (233 passed).
- [x] `cd extension && node --test tests/*.test.mjs` passes (11 passed).
- [x] `python scripts/eval.py cases --baseline server/tests/eval_baseline.json` has no geometry regression (92% top-1).
- [x] `python scripts/eval.py cases --resolver hybrid` passes against the recorded System One cassette (50/50 top-1); record fresh cases before making a live accuracy claim.
- [x] `cd desktop/src-tauri && cargo check --locked` passes.
- [x] `git diff --check` passes; generated builds, keys, `.env`, databases, and model files are absent from the diff.

## Windows desktop manual pass

- [ ] Install the NSIS bundle from a clean user profile. Launch from Start and verify the server starts and `/api/health` responds without a development checkout or Python install.
- [ ] Alt+Shift+S, tray Ask, Settings and Quit work; Quit terminates the bundled server it started. Autostart can be enabled and disabled in Settings.
- [ ] Test pen, box, point, Escape, and a follow-up question over Notepad, File Explorer, Chrome, a PDF reader, and an image or canvas app.
- [ ] The named target matches the marked item; ambiguity chips correct a wrong target without keeping the rejected answer in the follow-up context.
- [ ] Source links open in the default browser. Markdown headings, lists and inline code remain readable while streaming.
- [ ] Mic and read-aloud work with both configured NVIDIA speech and the available local fallback.
- [ ] Test monitors at different scaling factors, including a monitor left of the primary display; marks and panel placement use physical pixels correctly.
- [ ] Sensitive windows remain unreadable; an elevated or inaccessible window fails safely and still permits a useful OCR fallback where appropriate.
- [ ] With TypeSafe disabled for an ask, no Jev target, passage-ranking, or citation-check request is sent.
- [ ] With the extension paired, a Chrome desktop mark selects the page DOM target; blocked, ambiguous, and unreadable tabs remain protected. Disconnect the extension and verify desktop UIA/OCR fallback.

## Chrome extension manual pass

- [ ] Load `extension/` unpacked in Chrome; Alt+Shift+A, popup Start, pen/circle/box, clear, and Escape work on web pages and the bundled PDF viewer.
- [ ] Ask streams an answer, highlights the resolved target, shows citations, and supports correction chips and follow-ups.
- [ ] Consent and privacy settings persist; `anchors_only` sends no pixels, and the TypeSafe toggle controls the request independently of the answer provider.
- [ ] Research, speech input, read-aloud, and blocked-site behavior work without console errors.
- [ ] Extension version, icons, and package contents are reviewed before store upload.

## Server and data

- [ ] Fresh setup from `server/requirements.txt` starts cleanly; test configured providers with `python scripts/try_providers.py` and check fallback with no provider available.
- [ ] The server listens on loopback by default; desktop capture and candidates reject requests without the desktop token and non-local Host headers.
- [ ] A fresh bundled server creates a random API token; unauthorized extension origins cannot read contexts or traces. Pair the real extension using the desktop Settings copy button.
- [ ] Restart preserves SQLite history. Trace logging is opt-in, exports correctly, deletes correctly, and contains no pixels, embedded data URLs, keys, or provider error bodies.
- [ ] Research answers cite fetched sources; unsupported citations are marked. Review the offline research set and a small live sample before release.
- [ ] Check a fresh install's data path and migration behavior before changing the database format or protocol.

## Distribution

- [ ] Run `powershell -File desktop/build-release.ps1`; smoke-test the bundled server and installer on a clean Windows VM.
- [ ] Run `python scripts/smoke_bundle.py desktop/dist/spatial-server.exe` (requires `psutil`) to verify startup and token enforcement without touching a real profile.
- [ ] Bundle does not contain `server/.env`, user data, test fixtures, development tools, or credentials.
- [ ] Update `README.md`, `desktop/README.md`, extension manifest version, Tauri version, and a user-facing changelog entry together.
- [ ] Archive the exact artifacts and record their hashes. Sign installers when distributing outside a trusted test group.

macOS AX/screen capture remains a separate implementation task in `TASKS.md`. The desktop–extension bridge still needs its full desktop GUI pass before release.
