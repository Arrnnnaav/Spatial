# Spatial — Point & Ask

Circle anything you are reading in the browser, a PDF, or a Windows application, ask a question,
and get an answer about exactly that region. The local server supports Ollama and CPU OCR, or
OpenRouter / NVIDIA NIM / OpenAI / Anthropic when configured. Speech uses NVIDIA hosted ASR/TTS
when configured and local faster-whisper / pocket-tts as a fallback.

The interaction is the "spatial context" idea from HeyClicky: natural language is bad at spatial intent,
pointing is fast. Instead of "the second equation under the grey box", circle it and say "why this step?".

```
extension/   Chrome MV3 extension: overlay (pen/circle/box), ask panel, mic, read-aloud, pdf.js viewer
desktop/     Tauri Windows app: global hotkey, freeze-frame overlay, ask panel, tray
server/      FastAPI: /api/ask (providers + OCR + SQLite history), /api/stt, /api/tts, /api/health
scripts/     try_providers.py (live smoke test), fetch_models.sh (curl the speech models if HF stalls)
docs/        HOW_TO_RUN_AND_USE.md, LEARNING_PATH.md, PROVIDERS.md, AUDIO.md, TYPESAFE_OPPORTUNITIES.md
             AGENTS.md (start here), PRD, ARCHITECTURE, DESIGN, RULES, TASKS, MEMORY, master plan, checklist
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

For the Windows desktop app, see [desktop/README.md](desktop/README.md). A development build needs the server
started separately; the release installer bundles and starts it.
The installed server creates a local API token. To use the extension with it, copy the pairing token from desktop
Settings into the extension popup's API token field.

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
`server/app/research.py`: question + marked text → Tavily search when configured (DuckDuckGo and page-fetch
fallback) → select passages → provider answers in ≤3 sentences citing `[n]`; the response carries `sources`
and `cited`. Set `TAVILY_API_KEY` in the server environment for faster search. TypeSafe Jev can rerank passages
and check citations when the ask opts into System One.

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

## Tracing (opt-in)

Toggle **Keep a local trace log** in the extension popup, or set `SPATIAL_TRACE=on` in `server/.env`. Each ask
appends one JSON line (question, answer, marks, candidates, what was resolved, timings — never images) to
`%APPDATA%\Spatial\logs\YYYY-MM-DD.jsonl` (override with `SPATIAL_LOG_DIR`). Kept 14 days / 50 MB.
`GET /api/traces/export` downloads everything; `DELETE /api/traces` wipes it.

## Eval

```bash
python scripts/eval.py cases                              # top-1/top-3 over golden + eval cases
python scripts/eval.py traces "%APPDATA%\Spatial\logs"    # replay your own traces
python scripts/export_schema.py                           # regenerate schema/spatial-context.v3.json
```
