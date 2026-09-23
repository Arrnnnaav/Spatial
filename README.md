# Spatial — Point & Ask

Circle anything you are reading in the browser or a PDF, ask a question, get an answer about exactly
that region. Local-first: runs on Ollama with a CPU OCR fallback, or on OpenRouter / NVIDIA NIM /
OpenAI / Anthropic when a key is set. Speech in and out runs on CPU (faster-whisper, Kyutai pocket-tts).

The interaction is the "spatial context" idea from HeyClicky: natural language is bad at spatial intent,
pointing is fast. Instead of "the second equation under the grey box", circle it and say "why this step?".

```
extension/   Chrome MV3 extension: overlay (pen/circle/box), ask panel, mic, read-aloud, pdf.js viewer
server/      FastAPI: /api/ask (providers + OCR + SQLite history), /api/stt, /api/tts, /api/health
scripts/     try_providers.py (live smoke test), fetch_models.sh (curl the speech models if HF stalls)
docs/        HOW_TO_RUN_AND_USE.md, LEARNING_PATH.md, PROVIDERS.md, AUDIO.md, TYPESAFE_OPPORTUNITIES.md
AGENTS.md    start here (agents + contributors); PRD / ARCHITECTURE / DESIGN / RULES / TASKS / MEMORY.md alongside
```

## Quick start

```bash
cd server
python -m venv .venv && .venv\Scripts\activate        # Windows; use source .venv/bin/activate elsewhere
pip install -r requirements.txt
pip install faster-whisper pocket-tts rapidocr-onnxruntime pillow numpy   # optional CPU extras
copy .env.example .env                                  # edit: providers / keys
uvicorn app.main:app --port 8787
```

Then load `extension/` unpacked in Chrome (`chrome://extensions` → Developer mode → Load unpacked),
press **Alt+Shift+A** on any page, circle, ask. Open `http://127.0.0.1:8787/api/health` to see which
providers and speech engines are ready.

### Local, free, private (default)

```
ollama pull qwen3:4b-instruct      # text answers (2.5 GB)
ollama pull qwen2.5vl:3b           # vision: sees the crop (3.2 GB). Optional — without it the crop is OCR'd.
```

### Free API keys

- **OpenRouter** — https://openrouter.ai/keys, models ending in `:free` (rate-limited, no card).
  `OPENROUTER_API_KEY=sk-or-…`
- **NVIDIA NIM** — https://build.nvidia.com (free credits), `NVIDIA_API_KEY=nvapi-…`.
  Llama 3.2 11B Vision sees crops; Llama 3.1 8B handles text + OCR.

Put keys in `server/.env`; order them with `SPATIAL_PROVIDERS=ollama,openrouter,nvidia`. The first
provider that answers wins; failures fall through to the next; with none reachable the server still
replies with the text under the mark so the loop never dead-ends.

## How an ask works

1. Extension collects: marks (viewport px), DOM/PDF text elements under the mark ranked by overlap,
   page title/URL, and (privacy permitting) a JPEG crop of the marked region with the stroke drawn in.
2. `resolver.py` normalises marks (freehand strokes → bbox), re-ranks anchors deterministically and
   reports a confidence (<0.6 asks the user to circle tighter).
3. `providers.py` builds one prompt (page, ranked text, OCR text, earlier turns, question) and calls the
   first configured provider; vision-capable models get the crop, text models get OCR of the crop.
4. Answer + turn history stored in SQLite (`server/spatial.db`); follow-ups pass `context_id`.

Marks are a reference, never authority: nothing here acts on the page.

## Research mode (precise, cited answers)

`"research": true` on `/api/ask` (the extension's **🔎 Verify with sources** toggle, on by default) runs
`server/app/research.py`: question + marked text → DuckDuckGo search → fetch top pages → pick the passages
that overlap the question → provider answers in ≤3 sentences citing `[n]`; the response carries `sources`
and `cited`. No key needed; set `GOOGLE_API_KEY` (+ `pip install google-generativeai`) to add Gemini
grounding, the same search step as `D:/PROJECTS/Cited Multi-Agent Researcher`. Adds ~5 s.

## Bedrock, explain levels, diagram mode

`BEDROCK_ENABLED=1 AWS_REGION=us-east-1 BEDROCK_MODEL=amazon.nova-lite-v1:0` adds Amazon Bedrock (Converse API,
streaming, vision) to the chain; credentials come from the normal AWS chain (`pip install boto3`).
`level: eli5|student|expert` on `/api/ask` picks the explanation depth. When a mark has no readable text but a
crop is attached the server switches to diagram mode (vision first, then OCR) and reports `diagram: true`.

## Tests

```bash
cd server && python -m pytest -q
cd extension && node --test tests/geometry.test.mjs
python scripts/try_providers.py           # live check of configured providers, OCR, STT, TTS
```

## Origin and sync

Extracted from the StudyOS learning platform so the primitive can be used on its own or dropped into another
product. The two repos now share code both ways via `D:/unified/learning-platform/scripts/sync_spatial.py`:

- `extension/*` (everything except `config.js` and `manifest.json`) is copied **from** StudyOS
  `apps/extension`; edit it there. `config.js` is the build flavour (mode, API base, paths, feature flags).
- `server/app/{providers,ocr,audio}.py` are the source of truth and are copied **to** StudyOS
  `services/api/app/core/spatial/`; `server/app/resolver.py` and `server/tests/cases/*.json` come from StudyOS.

`python scripts/sync_spatial.py --check` (run from the StudyOS repo) fails when either side drifts.
