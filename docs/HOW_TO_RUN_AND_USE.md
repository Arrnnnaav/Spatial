# How to run and use Spatial (Point & Ask)

Circle anything you are reading in Chrome — a web page, a web app, an online or downloaded PDF — ask a
question by typing or speaking, and get an answer about exactly that region, optionally read aloud.

Two parts: a **local server** (Python) that talks to the models, and a **Chrome extension** that draws the
overlay and sends what you circled to the server.

---

## 1. Requirements

| Need | Why | Check |
|---|---|---|
| Python 3.11+ | server | `py -3.12 --version` |
| Chrome / Edge / Brave | extension (Manifest V3) | `chrome://version` |
| Node 18+ (optional) | only for the extension unit tests | `node -v` |
| Ollama (optional, recommended) | free local models | https://ollama.com → `ollama --version` |
| NVIDIA NIM key (optional) | free hosted models incl. vision | https://build.nvidia.com → API key starts with `nvapi-` |

Hardware: any laptop, but RAM matters. `qwen3:4b-instruct` needs ~3 GB, `qwen2.5vl:3b` ~3.5 GB, whisper `base` +
pocket-tts ~1.5 GB together. On a 16 GB machine with a browser open that is tight: the server unloads the speech
models after 5 idle minutes (`SPATIAL_AUDIO_IDLE_UNLOAD_SECONDS`), and NVIDIA's free tier costs no local RAM.

---

## 2. Install the server

```powershell
cd D:\PROJECTS\Spatial\server
py -3.12 -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
# optional CPU extras (mic transcription, read-aloud, OCR of the crop):
pip install faster-whisper pocket-tts rapidocr-onnxruntime pillow numpy
copy .env.example .env
```

Edit `.env`:

```ini
SPATIAL_PROVIDERS=ollama,nvidia          # order of preference; first that answers wins
OLLAMA_MODEL=qwen3:4b-instruct
OLLAMA_VISION_MODEL=qwen2.5vl:3b         # or "none" to skip vision and OCR the crop instead
NVIDIA_API_KEY=nvapi-...                 # free tier models only (see PROVIDERS.md)
NVIDIA_MODEL=openai/gpt-oss-20b
NVIDIA_VISION_MODEL=meta/llama-3.2-11b-vision-instruct
SPATIAL_FORCE_IPV4=1                     # only if Hugging Face downloads stall
```

Pull local models (one time):

```powershell
ollama pull qwen3:4b-instruct
ollama pull qwen2.5vl:3b
```

Start:

```powershell
uvicorn app.main:app --port 8787
```

Open http://127.0.0.1:8787/api/health — it lists which providers are configured and whether STT/TTS
are installed. First mic use downloads faster-whisper `base` (~150 MB); first read-aloud downloads
pocket-tts (~240 MB + a voice embedding). Both are cached afterwards. If those downloads stall, `bash scripts/fetch_models.sh` fetches them with curl.

Quick self-test of everything that is configured:

```powershell
cd ..
py -3.12 scripts\try_providers.py          # against the running server
py -3.12 scripts\try_providers.py --direct # without the server
```

---

## 3. Install the extension

1. Open `chrome://extensions`, turn on **Developer mode** (top right).
2. **Load unpacked** → choose `D:\PROJECTS\Spatial\extension`.
3. Click the extension's **Details** → enable **Allow access to file URLs** (needed for downloaded PDFs).
4. Pin the icon. Click it: the popup should say *Connected. Providers ready: ollama, nvidia …*.
   If it says it cannot reach the server, the server is not running or the URL in *Server settings* is wrong.

Popup options:
- **Model provider** — *Auto* uses the server order; or force one (e.g. `nvidia` to always use the cloud).
- **What leaves this browser** — crop of the marked region (default) / text only / whole visible tab.
- **Read answers aloud automatically** — speaks every answer with pocket-tts (or the OS voice if the server has no TTS).
- **Server settings** — URL, optional API token (`SPATIAL_API_TOKEN` in `.env`), preferred voice.

---

## 4. Use it

1. On any page press **Alt+Shift+A** (or click the icon → *Start marking on this tab*).
   The page dims slightly, the cursor becomes a crosshair, a toolbar appears at the top.
2. **Scribble a circle** around the thing (pen is default). Or pick **Circle** / **Box** for a neat shape.
   Draw more than one mark if the question spans two things ("how do these relate?").
3. A panel opens next to the mark. **Type** the question and press Enter, or press **🎤**, speak, press it
   again to stop — the words appear in the box — then Enter.
4. Read the answer. The footer says which provider/model answered, how many text anchors it used, whether
   it saw the crop (`crop seen`) or OCR'd it, and the mark confidence. **🔊 Read aloud** speaks it.
5. Ask **follow-ups** in the same panel — they reuse the same mark. **Clear** starts a new context, **Done**
   or **Esc** closes the overlay.

6. First run shows a **consent card**: pick crop (default), text-only or full tab; change later in the popup.
   **A Source** / **B Target** on the toolbar tag marks for relational questions. After an answer the
   resolved element pulses with a green ring.
7. **Power mode** (popup) unlocks the provider picker and server speech (faster-whisper in, pocket-tts out)
   instead of the browser's Web Speech / OS voice. Chrome asks for the microphone once via `permission.html`.

PDFs: right-click a PDF link or page → *Open PDF in Point & Ask viewer*, use the popup button on a PDF tab,
or tick *Always open PDFs in the viewer* in the popup. The viewer renders pages with a selectable text
layer; text under the mark comes with page numbers.

The overlay never runs on banking, payment, health or government sites; add your own hosts in the popup.

History: `GET http://127.0.0.1:8787/api/contexts` lists past asks (question, page, answer, turns);
`DELETE /api/contexts/{id}` removes one. Data lives in `server/spatial.db`.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Popup: *Cannot reach http://127.0.0.1:8787* | start the server; check firewall; check the URL in Server settings |
| Answer footer: `no model configured` | no provider reachable; check `/api/health`, `.env`, `ollama serve` |
| errors: `ollama … std::bad_alloc` / 500 | out of RAM: wait for the audio models to unload, use `SPATIAL_STT_MODEL=tiny`, or put `nvidia` first in `SPATIAL_PROVIDERS` |
| Footer note: `vision model unavailable, answered from text` | `ollama pull qwen2.5vl:3b`, or set `OLLAMA_VISION_MODEL=none` to silence; OCR still reads the crop |
| `ollama: model 'x' is not pulled` in errors | run the `ollama pull` it names |
| NVIDIA 401 / 402 | wrong key, or the model is not on the free tier; pick another from `/v1/models` |
| STT returns 503 `failed to allocate memory` | RAM pressure: Ollama vision model + TTS + whisper together want ~6 GB free. Use `SPATIAL_STT_MODEL=tiny`, or `OLLAMA_VISION_MODEL=none` (OCR instead), or close other apps |
| Mic button hidden or "Microphone blocked" | allow the microphone for that site (lock icon in the address bar) |
| Read aloud says `unavailable` | `pip install pocket-tts`; first use downloads weights; `SPATIAL_FORCE_IPV4=1` if it stalls |
| Hugging Face downloads stuck at a few MB | IPv6 route problem: `SPATIAL_FORCE_IPV4=1` in `.env`; if still stuck run `bash scripts/fetch_models.sh` (curl over IPv4 straight into the HF cache) |
| PDF viewer: "Cannot read this local file" | enable *Allow access to file URLs* for the extension |
| Nothing happens on `chrome://` or the Web Store | extensions cannot inject there by design |
| Low confidence warning | circle tighter around one thing, or use Box for a precise region |

---

## 6. Tests

```powershell
cd server;    py -3.12 -m pytest -q
cd extension; node --test tests/geometry.test.mjs
```

Manual/visual: `cd extension; py -3.12 -m http.server 5173` then open
http://localhost:5173/dev/harness.html (stubs `chrome.*`, talks to the server on 8787).
