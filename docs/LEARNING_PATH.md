# Learning path: what you need to know to build Spatial yourself

Ordered from "must know to read this codebase" to "needed to push it further". Each topic names the
file in this repo where it is used, so you can study with the real code open. Estimated time is for
someone who already programs in one language.

## 0. Prerequisites (1–2 weeks if new)

- **JavaScript (modern)**: `const/let`, arrow functions, `async/await`, Promises, destructuring,
  template literals, modules. Everything in `extension/` is plain JS, no framework.
- **Python 3**: type hints, dataclasses, `with`, generators, `try/except`. Everything in `server/`.
- **HTTP basics**: methods, status codes, JSON bodies, headers (Authorization, Content-Type), CORS.
- **Git and the command line**.

## 1. The browser side — how the overlay works (1 week)

| Topic | Where used | Learn |
|---|---|---|
| DOM APIs: `createElement`, `append`, events, `getBoundingClientRect`, `elementsFromPoint` | `content.js` (`collectAnchors`) | MDN "Introduction to the DOM", "Element.getBoundingClientRect" |
| Pointer events (`pointerdown/move/up`, `setPointerCapture`) and coordinate spaces (client vs page vs screen, `devicePixelRatio`) | `content.js` drawing; `background.js` crop math | MDN Pointer events; "CSS pixels vs device pixels" |
| SVG basics: `<path d="M… L…">`, `<ellipse>`, `<rect>`, stroke attributes | `content.js` `svgNode` | MDN SVG tutorial |
| Shadow DOM: isolating your UI's CSS from the host page | `content.js` `attachShadow` | MDN "Using shadow DOM" |
| CSS: `position: fixed`, `z-index`, flexbox, `inset` | overlay + panel styles | any CSS course; MDN flexbox |
| `MediaRecorder` + `getUserMedia` (record mic to webm/opus) | `content.js` `setupMic` | MDN MediaStream Recording API |
| Web Speech API (`SpeechRecognition`, `speechSynthesis`) as fallbacks | `content.js` | MDN Web Speech API |
| `Audio`, data URLs, `FileReader`, `Blob` | read-aloud, crop transfer | MDN Blob / FileReader |

## 2. Chrome extensions, Manifest V3 (1 week)

| Topic | Where used |
|---|---|
| `manifest.json`: permissions vs host_permissions, `commands` (hotkeys), `action`, `web_accessible_resources`, CSP | `extension/manifest.json` |
| Service worker background script (no DOM, may be killed any time → keep state in `chrome.storage`) | `background.js` |
| `chrome.scripting.executeScript` to inject on demand; content-script world vs page world | `background.js` `toggleOverlay` |
| Messaging: `chrome.runtime.sendMessage` / `onMessage` with async `sendResponse` (`return true`) | both files |
| `chrome.tabs.captureVisibleTab`, `OffscreenCanvas`, `createImageBitmap` for cropping | `background.js` `captureCrop` |
| `chrome.webNavigation.onBeforeNavigate` + `tabs.update` to hijack PDF URLs | `background.js` |
| `chrome.storage.local`, popup pages, `file://` access | `popup.js` |
| Why extension origins need CORS on the server (`chrome-extension://…`) | `server/app/main.py` CORS regex |

Read: Chrome for Developers → "Extensions → Get started" and "Manifest V3 migration". Build a
toy extension that injects a button and sends a message to its service worker before reading `content.js`.

## 3. PDFs in the browser (3–4 days)

- **pdf.js** (`pdfjs-dist`): `getDocument`, `getPage`, `getViewport`, `render` to canvas, `TextLayer`
  for selectable text with per-span positions → `viewer.js`.
- Why the built-in Chrome PDF viewer cannot be scripted, and the redirect trick.
- Reading order reconstruction: sorting text spans by (page, y, x) and merging → `content.js` `pdfTextBlocks`.

## 4. Geometry for "what did they circle?" (2–3 days)

- Bounding boxes, point simplification, closed-vs-open stroke heuristics → `extension/geometry.js`.
- Intersection over Union (IoU), containment, area-based tie-breaking → `server/app/resolver.py`.
- Normalising coordinates to the canvas (0–1) so marks survive resizes.
- Writing unit tests for pure geometry with `node:test` → `extension/tests/geometry.test.mjs`.

## 5. The server — FastAPI (1 week)

| Topic | Where used |
|---|---|
| FastAPI routes, Pydantic models for validation, `Depends` for auth, `HTTPException` | `server/app/main.py` |
| File uploads (`UploadFile`, `python-multipart`), binary responses (`Response(media_type="audio/wav")`) | `/api/stt`, `/api/tts` |
| Server-Sent Events with `StreamingResponse` | `/api/ask/stream` |
| CORS middleware | `main.py` |
| SQLite with the standard `sqlite3` module; JSON columns; simple schema migration | `server/app/store.py` |
| Settings from environment / `.env` (`python-dotenv`) | `server/app/config.py` |
| `httpx` for outbound HTTP with timeouts | `server/app/providers.py` |
| Testing with `TestClient`, `monkeypatch`, fixtures | `server/tests/test_server.py` |
| Running with `uvicorn`; virtual environments | README |

## 6. Talking to LLMs and vision models (1 week)

- **Chat-completions shape** (system / user / assistant messages), temperature, max tokens.
- **OpenAI-compatible APIs**: the same `/v1/chat/completions` contract is served by OpenRouter, NVIDIA NIM,
  Groq, LM Studio, vLLM… → `_call_openai_compatible`. One code path, many vendors.
- **Multimodal input**: sending an image as base64 `image_url` (OpenAI style), `images: [...]` (Ollama
  native), `{"type": "image", "source": {...}}` (Anthropic Messages API).
- **Ollama**: `ollama pull`, `/api/chat` vs `/v1/chat/completions`, quantisation (Q4_K_M), VRAM budgeting.
- **Prompt design for grounded answers**: give the model the page title, the ranked text under the mark,
  OCR text, prior turns; tell it the mark is a reference, not a command → `build_prompt`, `SYSTEM_PROMPT`.
- **Fallback chains and observability**: try providers in order, record every error, never dead-end →
  `providers.answer`.
- **Model choice**: small instruct models (Qwen3 4B, Llama 3.1 8B) vs vision-language models (Qwen2.5-VL,
  Llama 3.2 Vision); what "free tier" means on OpenRouter (`:free`) and NVIDIA (credits).

## 7. OCR and speech on CPU (3–5 days)

- **OCR**: RapidOCR (PaddleOCR models exported to ONNX): detection → recognition → text lines →
  `server/app/ocr.py`. Understand why OCR + text model is a cheap stand-in for a vision model.
- **Speech-to-text**: Whisper architecture at a high level; `faster-whisper` (CTranslate2, int8),
  model sizes vs accuracy vs latency, VAD filtering → `server/app/audio.py`.
- **Text-to-speech**: Kyutai **pocket-tts** (100M params, streaming, voice embeddings), how it is loaded
  and why the model and voice state are cached in memory; WAV encoding with the `wave` module.
- Alternatives worth knowing: whisper.cpp, Vosk, Moonshine (STT); Piper, Kokoro (TTS). See `AUDIO.md`.
- **ONNX Runtime** as the common CPU inference layer behind RapidOCR/Piper/Kokoro.

## 8. Product and safety thinking (ongoing)

- **Spatial context as a primitive**: pointing beats describing; the mark is *what*, the utterance is *why*.
  Read the HeyClicky launch material and the `SPATIAL CONTEXT.md` positioning note in the parent repo.
- **Reference ≠ authority**: a circled "Delete" button must never authorise deleting. Any future "act on
  this" feature needs permission → risk → approval → execute → verify.
- **Privacy tiers**: text-only / crop / full frame; local-first defaults; what an operator may see.
- **Confidence and confirmation**: when to ask the user to circle tighter instead of guessing.

## 9. Where to go next (project ideas that extend this repo)

1. Streaming tokens to the panel (SSE already exists; render partial text).
2. Two-mark interactions: SOURCE and TARGET ("move this here", "make these match").
3. AI → human pointing: let the answer highlight elements on the page (reverse spatial context).
4. In-browser audio: pocket-tts / Moonshine WebAssembly builds so no server is needed for speech.
5. Accessibility-tree anchors (`role`, `aria-label`) and Office/desktop plugins via UI Automation.
6. Evaluation set: 50 saved marks with expected anchors; measure anchor accuracy and p95 latency.
7. Spaced-repetition: turn each ask into a flashcard ("quiz me on this later").

## Suggested order and timeline

Weeks 1–2: sections 0–2 (build a toy extension that draws a rectangle and logs the elements under it).
Week 3: sections 4–5 (write the resolver + a FastAPI `/api/ask` that echoes the text under the mark).
Week 4: section 6 (plug in Ollama, then one hosted provider; add fallback + errors map).
Week 5: sections 3 and 7 (PDF viewer; mic → whisper; read-aloud with pocket-tts).
Week 6: section 8 + one item from section 9.

By the end of week 3 you will have re-built the core of this repo; the rest is polish and reach.
