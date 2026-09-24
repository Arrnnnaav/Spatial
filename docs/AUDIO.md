# Audio: speech in, speech out

## Current setup (2026-09-24)

| | Primary: NVIDIA hosted (same `NVIDIA_API_KEY`) | Fallback: local CPU |
|---|---|---|
| Speech → text, English | **Parakeet-tdt-0.6b-v2** | faster-whisper `base` |
| Speech → text, other languages | **Whisper-large-v3** | faster-whisper `base` |
| Text → speech | **Magpie-tts-multilingual**, voice `Aria` | Kyutai pocket-tts `alba` |

Measured on this laptop through `server/app/audio.py`: after the startup warm-up (runs in the background, ~14 s),
the first real STT took **0.48 s** (webm/opus from the mic) and TTS **0.42 s**; the local models needed ~5 s / ~2 s
warm and 25–30 s cold. Busy gRPC errors are retried 3 times; timeout (`SPATIAL_SPEECH_TIMEOUT`, 12 s), bad key or
undecodable audio falls back to the local models (`fallback_reason` in the STT response). Force a side with
`SPATIAL_SPEECH_BACKEND=nvidia|local`. The hosted side needs `pip install nvidia-riva-client`; audio decoding of
webm uses PyAV via faster-whisper. **Privacy:** with the NVIDIA backend your recorded question and the answer text
are sent to NVIDIA; set `SPATIAL_SPEECH_BACKEND=local` to keep speech on the machine.

Rejected: **PersonaPlex** (NVIDIA, 7B full-duplex speech-to-speech on Moshi) and **nemotron-voicechat**: they answer
with their own LLM, so they cannot speak Spatial's grounded answer about the marked thing; PersonaPlex also needs an
A100-class GPU on Linux and has no hosted API. Worth revisiting for a future live voice-conversation mode.

The desktop panel has the same 🎤 / 🔊 buttons; its Rust shell grants the microphone to its own bundled pages so
WebView2 does not ask on every launch.

## Local engines (fallback) — details

### Speech → text (the 🎤 button)

Server: **faster-whisper** (`SPATIAL_STT_MODEL=base`, int8 on CPU). `tiny` ≈ 75 MB and ~1 s for a
10 s clip on a laptop; `base` ≈ 150 MB, noticeably better; `small` ≈ 480 MB, best that still feels
instant for short questions. Audio comes from `MediaRecorder` (webm/opus) → `POST /api/stt`.
If the server has no STT installed, the extension falls back to the browser's Web Speech API
(Chrome sends that audio to Google).

Alternatives considered, all CPU-friendly:
- **whisper.cpp** — C++ port, same models, tiny binary; use if you do not want a Python server.
- **Vosk** — very small (50 MB) streaming models, lower accuracy, good for keyword-style commands.
- **sherpa-onnx** — Zipformer/Paraformer ONNX models, streaming, runs on phones; more setup.
- **Moonshine** (Useful Sensors) — 27M/61M-param models tuned for short clips; comparable to whisper
  tiny/base at lower latency, ONNX/JS builds exist (could run in the extension itself later).

### Text → speech (🔊 Read aloud)

Server: **Kyutai pocket-tts** (https://github.com/kyutai-labs/pocket-tts) — 100M parameters, CPU only,
~200 ms to first audio, faster than real-time on 2 cores, English + fr/de/es/it/pt, voice cloning from a
short WAV. Model weights and the voice embedding download from Hugging Face on first use.
`SPATIAL_TTS_VOICE` picks a bundled voice (`alba`, `jane`, `paul`, …) or a path to your own `.wav`.

Alternatives, all CPU:
- **Piper** — ONNX VITS voices, ~20 MB each, extremely fast, robotic-but-clear; best for very low-end CPUs.
- **Kokoro-82M** — high quality, ONNX build runs on CPU at ~real-time; ~330 MB.
- **Supertonic / Chatterbox-Turbo** — newer small models; heavier than pocket-tts.
- **Browser `speechSynthesis`** — zero install, uses OS voices; quality varies. Wired as the automatic
  fallback when the server has no TTS.

### Why not fully in-browser?

pocket-tts and Moonshine both have WebAssembly/ONNX-web builds, so the whole audio path could move
into the extension. Kept server-side for now so one download serves every tab and the CPU work does
not block the page.
