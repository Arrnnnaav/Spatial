# Audio: speech in, speech out — on CPU

## Speech → text (the 🎤 button)

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

## Text → speech (🔊 Read aloud)

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

## Why not fully in-browser?

pocket-tts and Moonshine both have WebAssembly/ONNX-web builds, so the whole audio path could move
into the extension. Kept server-side for now so one download serves every tab and the CPU work does
not block the page.
