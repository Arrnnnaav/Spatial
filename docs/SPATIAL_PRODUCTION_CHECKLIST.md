# Spatial — Production Readiness Checklist

**Product**: Spatial — Point & Ask (Chrome MV3 Extension + FastAPI Server)
**Status**: Local-first spatial grounding primitive
**Last Updated**: 2026-09-18

---

## 🎯 Scope: What This Covers

| ✅ Included | ❌ Excluded |
|-------------|-------------|
| Chrome MV3 Extension (overlay, panel, capture) | Public website / SEO / marketing pages |
| FastAPI Server (resolver, providers, OCR, audio, research, store) | User accounts / auth / billing |
| Local-first architecture (Ollama, privacy tiers, deterministic fallback) | Analytics / telemetry / uptime monitoring |
| Cross-browser extension parity (Chrome, Firefox, Edge) | CDN / bundle optimization / public assets |
| Native app migration path (Tauri + shared geometry) | Database scaling / migrations beyond SQLite |

---

## 1. 🧹 Code Cleanup — Vibe-Code Leftovers

- [ ] Remove all `console.log`, `console.debug`, `print()` statements
- [ ] Remove commented-out experimental code
- [ ] Remove unused imports (Python + JS)
- [ ] Remove unused dependencies (`pip-audit`, `npm audit`)
- [ ] Remove `TODO`, `FIXME`, `placeholder`, `dummy` from codebase
- [ ] Remove hardcoded `localhost` URLs from production config
- [ ] Verify no API keys/secrets in frontend (extension) code
- [ ] Verify `.env` not committed (check `.gitignore`)
- [ ] Fix all console errors in extension DevTools
- [ ] Fix all console warnings in extension DevTools
- [ ] Remove development-only UI (debug panels, test buttons)
- [ ] Remove React/Vite dev indicators (not applicable — vanilla JS)

---

## 2. 🎨 Extension UI / Overlay

### Visual Consistency
- [ ] No horizontal scrolling in overlay/panel
- [ ] No overlapping components (toolbar, panel, hint, consent)
- [ ] Consistent spacing (8px grid)
- [ ] Consistent typography (system-ui, 13-14px base)
- [ ] Consistent border radius (6-14px)
- [ ] Consistent button styles (primary, secondary, role buttons)
- [ ] Consistent colors (STROKE `#ff3d7f`, SOURCE `#ff3d7f`, TARGET `#2f7cf6`, HIGHLIGHT `#00d4aa`)
- [ ] Consistent shadows (overlay, panel, toolbar, consent card)
- [ ] Proper visual hierarchy (toolbar > panel > hint > overlay)
- [ ] Proper alignment (panel positions relative to mark)

### Overlay Functionality
- [ ] Hotkey `Alt+Shift+A` toggles overlay
- [ ] Pen tool: freehand stroke → polygon mark
- [ ] Circle tool: drag → circle mark
- [ ] Box tool: drag → rectangle mark
- [ ] Stroke simplification (tolerance 2px)
- [ ] Closed stroke detection → no padding
- [ ] Open stroke → adaptive padding (8-40px)
- [ ] Role toolbar: Reference / Source / Target toggle
- [ ] Clear marks button works
- [ ] Done button closes overlay
- [ ] Esc key closes overlay
- [ ] Consent modal on first run (crop_only / anchors_only / full_frame)
- [ ] Consent persists to storage

### Ask Panel
- [ ] Opens near mark (right preferred, flips left if needed)
- [ ] Thread shows Q/A history
- [ ] Textarea: Enter sends, Shift+Enter newlines
- [ ] Mic button: Web Speech API (default) + server STT (power mode)
- [ ] Send button: disabled while busy
- [ ] Streaming deltas render progressively
- [ ] Status messages render ("resolving_mark", "checking sources…")
- [ ] Research toggle (default on) persists
- [ ] Level selector: eli5 / student / expert persists
- [ ] Speaker button: server TTS → browser fallback
- [ ] Sources list: cited links bold, open in new tab
- [ ] Meta note line: provider/model, anchors, vision/OCR, confidence, diagram, level, pages, quota

---

## 3. 📱 Responsive / Cross-Context

- [ ] Extension popup renders correctly (360px max)
- [ ] Overlay works on desktop viewport (1280px+)
- [ ] Overlay works on laptop viewport (1024px)
- [ ] Overlay works on tablet viewport (768px) — if testing mobile Chrome
- [ ] Touch targets ≥ 44×44px (buttons, toolbar)
- [ ] Text ≥ 13px (no zoom required)
- [ ] Panel fits within viewport (max-width: calc(100vw - 24px))
- [ ] Content scripts work inside PDF viewer (`viewer.html`)
- [ ] Content scripts work on `file://` PDFs
- [ ] Content scripts work on `chrome://` blocked pages (graceful block message)

---

## 4. 🔗 Navigation & Deep Links

- [ ] Extension action click → toggles overlay
- [ ] Context menu "Open PDF in Spatial viewer" works
- [ ] PDF auto-redirect (when `pdfViewer` enabled) works
- [ ] `context_id` persists across refreshes (same mark + page)
- [ ] New mark clears `context_id` (new conversation)
- [ ] Follow-up questions inherit resolved object (unless new mark/page change)

---

## 5. 🔒 Security (Critical for Local-First)

### Extension
- [ ] No API keys in `content.js`, `background.js`, `popup.js`
- [ ] `manifest.json` CSP: `script-src 'self' 'wasm-unsafe-eval'`
- [ ] `host_permissions: ["<all_urls>"]` justified (capture + injection)
- [ ] No secrets in `localStorage` / `chrome.storage.local` (token stored in background only)
- [ ] Device ID generated client-side (crypto.randomUUID)

### Server
- [ ] `.env` not committed (check `.gitignore`)
- [ ] `SPATIAL_API_TOKEN` optional but enforced if set
- [ ] CORS: `allow_origin_regex` for `chrome-extension://*` + `moz-extension://*`
- [ ] Input validation: Pydantic models on all endpoints
- [ ] Rate limiting: provider-level (429 handling) + future per-device
- [ ] No stack traces in error responses (friendly codes only)
- [ ] `npm audit` / `pip-audit` clean (or documented exceptions)
- [ ] Dependencies pinned in `requirements.txt` / `package.json`

### Privacy Tiers (Enforced Client + Server)
- [ ] `anchors_only`: no `image_data` sent
- [ ] `crop_only`: marked region + stroke only (≤1600px, JPEG 0.86)
- [ ] `full_frame`: explicit opt-in only
- [ ] Server drops `image_data` if policy doesn't allow

---

## 6. ⚡ Server API & Functionality

### Core Endpoints
- [ ] `GET /api/health` → provider status, OCR, audio, version
- [ ] `POST /api/ask` → non-streaming answer
- [ ] `POST /api/ask/stream` → SSE (status → deltas → complete/error)
- [ ] `GET /api/contexts` → recent history (limit 25)
- [ ] `GET /api/contexts/{id}` → full context
- [ ] `DELETE /api/contexts/{id}` → delete
- [ ] `POST /api/stt` → faster-whisper transcription
- [ ] `POST /api/tts` → pocket-tts WAV

### Resolver (`resolver.py`)
- [ ] Normalizes marks (polygon→bbox, freehand→bbox+points)
- [ ] Validates anchors (id, text, bbox, page)
- [ ] IoU / overlap / containment scoring
- [ ] Tie-break: longer text → smaller area
- [ ] Confidence calculation (0.0–0.99, explainable)
- [ ] Source+Target role boost (+0.03)
- [ ] Zero-dimension mark penalty (≤0.65)
- [ ] Returns `anchors_ranked` (top 8) + `confidence`

### Providers (`providers.py`)
- [ ] Provider order: `SPATIAL_PROVIDERS` env var respected
- [ ] Ollama native `/api/chat` (streaming)
- [ ] OpenAI-compatible (OpenRouter, NVIDIA, OpenAI)
- [ ] Anthropic `/messages`
- [ ] Bedrock Converse API (streaming)
- [ ] Vision models get crop; text models get OCR
- [ ] First successful provider wins; failures fall through
- [ ] Deterministic fallback: quoted anchor text + question
- [ ] Cost estimation per request (USD)
- [ ] Research mode: DDG + Gemini grounding → citations

### OCR (`ocr.py`)
- [ ] RapidOCR ONNX loads lazily
- [ ] Returns joined text (confidence ≥ 0.4)
- [ ] Graceful fallback if not installed

### Audio (`audio.py`)
- [ ] faster-whisper loads lazily (int8 CPU, float16 GPU)
- [ ] Auto-unload after `SPATIAL_AUDIO_IDLE_UNLOAD_SECONDS` (default 300s)
- [ ] pocket-tts loads lazily
- [ ] Voice selection (`SPATIAL_TTS_VOICE`, default `alba`)

### Store (`store.py`)
- [ ] SQLite schema: contexts, marks, resolution, answer, history
- [ ] `create` → returns `context_id`
- [ ] `update` → appends turn to history
- [ ] `get` / `recent` / `delete` work
- [ ] WAL mode for concurrent access

---

## 7. 🧠 Candidate Discovery & Semantic Resolution

### Current (Must Work)
- [ ] `elementsFromPoint` 6×6 grid under mark
- [ ] `anchorFilter` rejects page-sized containers (>45% viewport)
- [ ] PDF textLayer spans merged into paragraphs (per page, reading order)
- [ ] User text selection → top-ranked anchor
- [ ] `rankAnchors` matches server resolver exactly (golden tests)
- [ ] Top 12 anchors sent to server

### Phase 2 Targets (In Progress)
- [ ] SVG semantic grouping (primitives → Chart_1/Legend_1)
- [ ] PDF figure/equation/table detection
- [ ] Shadow DOM (open roots) traversal
- [ ] Same-origin iframe traversal + coordinate transform
- [ ] Canvas Tier 1 (surrounding DOM) + Tier 2 (OCR blocks)
- [ ] Accessibility tree as candidate source
- [ ] Candidate deduplication (DOM + OCR + a11y)
- [ ] Ground-truth in top-12 for >95% golden cases

### Jev / System One Integration (Phase 3)
- [ ] `SystemOneProvider` interface: `choose` / `noul` / `score`
- [ ] TypeSafe Jev `Choice` → target candidate + probabilities
- [ ] TypeSafe Jev `Noul` → ambiguity probability
- [ ] TypeSafe Jev `Score` → semantic fit (0–2 scale)
- [ ] Reference phrase extraction ("this chart", "that table")
- [ ] Candidate serialization: aliases (A/B/C/D) + geometry + labels
- [ ] Confidence fusion: `fuse(geometric, semantic, extractor_trust, margin)`
- [ ] Abstention: `confidence < 0.5` OR `noul > 0.6`
- [ ] Clarification UI: numbered overlays, click to correct
- [ ] Correction capture → labeled training tuple

---

## 8. 🧪 Testing & Quality Gates

### Automated
- [ ] `cd server && python -m pytest -q` → all pass
- [ ] `cd extension && node --test tests/geometry.test.mjs` → all pass
- [ ] `python scripts/try_providers.py` → configured providers respond
- [ ] Resolver golden cases: 20 web / 20 PDF / 10 diagram / 10 ambiguity
- [ ] Client/server geometry parity (JS + Python same ranking)

### Manual (Per Release)
- [ ] Extension loads unpacked in Chrome/Edge/Firefox
- [ ] Hotkey opens/closes overlay
- [ ] Draw pen/circle/box → marks appear
- [ ] Ask question → streaming answer appears
- [ ] Highlight ring pulses on resolved anchor
- [ ] Research mode toggles → cites sources
- [ ] Voice: mic → transcribe → submit works
- [ ] Voice: TTS reads answer
- [ ] Privacy tiers: `anchors_only` / `crop_only` / `full_frame` verified
- [ ] Multi-mark: Source → Target → "How does A lead to B?"
- [ ] Follow-up inherits context
- [ ] PDF viewer: open PDF → textLayer merge works
- [ ] Server restart → history persists

---

## 9. 📦 Build / Deploy / Distribution

### Extension
- [ ] `manifest.json` version bumped
- [ ] Icons present: 16/32/48/128
- [ ] Load unpacked works (no build step required)
- [ ] Chrome Web Store package: `zip -r spatial.zip extension/`
- [ ] Firefox: `web-ext build` (future)

### Server
- [ ] `python -m venv .venv && pip install -r requirements.txt`
- [ ] `cp .env.example .env` → configured
- [ ] `ollama pull qwen3:4b-instruct` (text)
- [ ] `ollama pull qwen2.5vl:3b` (vision, optional)
- [ ] `uvicorn app.main:app --port 8787` starts clean
- [ ] `/api/health` shows all providers "configured: true/false"

### Native App Migration (Tracked Separately)
- [ ] `geometry.js` extracted as `@spatial/geometry` npm package
- [ ] Tauri spike: global hotkey + screen capture + OCR → FastAPI
- [ ] Shared `SpatialContext` contract (TypeScript + Pydantic)

---

## 10. 📊 Observability (Local-First)

- [ ] `/api/health` shows provider status + latency
- [ ] Response meta includes: `provider`, `model`, `vision`, `ocr`, `latency_ms`, `cost_usd`, `confidence`
- [ ] Error codes surfaced: `AUTH_REQUIRED`, `RATE_LIMITED`, `COST_CAP`, `CLIENT_OUTDATED`, `PROVIDER_*`
- [ ] Daily quota shown in panel meta (if implemented)
- [ ] Correction events logged (for future calibration)

---

## 11. 📋 Definition of Done (Per Release)

```
[ ] All automated tests pass
[ ] Manual smoke test passes (items in §8)
[ ] No console errors/warnings
[ ] No API keys in frontend
[ ] .env not committed
[ ] Version bumped in manifest.json + server
[ ] CHANGELOG.md updated
[ ] README.md reflects current config
[ ] Extension zip created for distribution
[ ] Server starts clean on fresh venv
```

---

## 12. 🚫 Explicitly Out of Scope (Do Not Add)

- [ ] Public website / landing page
- [ ] SEO / meta tags / sitemap / robots.txt
- [ ] User accounts / authentication / OAuth
- [ ] Billing / subscriptions / Stripe
- [ ] Analytics / Mixpanel / GA / PostHog
- [ ] CDN / Vercel / Netlify / Cloudflare Workers
- [ ] Database migrations / PostgreSQL / Redis
- [ ] Docker / Kubernetes / CI/CD pipelines
- [ ] Email notifications / SendGrid
- [ ] Social login / OAuth providers
- [ ] Team workspaces / sharing / collaboration
- [ ] Plugin marketplace / third-party extensions
- [ ] Mobile app (iOS/Android) — native app covers desktop

---

## 📌 Quick Reference: File Locations

| Component | Path |
|-----------|------|
| Extension overlay/panel | `extension/content.js` |
| Extension background (capture, messaging) | `extension/background.js` |
| Shared geometry | `extension/geometry.js` |
| Manifest | `extension/manifest.json` |
| Server entry | `server/app/main.py` |
| Resolver | `server/app/resolver.py` |
| Providers | `server/app/providers.py` |
| OCR | `server/app/ocr.py` |
| Audio | `server/app/audio.py` |
| Research | `server/app/research.py` |
| Store | `server/app/store.py` |
| Config | `server/app/config.py` |
| Golden cases | `server/tests/cases/*.json` |
| Geometry tests | `extension/tests/geometry.test.mjs` |

---

**Use this checklist before every release.** If it's not on this list, it's not blocking for Spatial's current phase.