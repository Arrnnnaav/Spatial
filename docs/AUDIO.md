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

## Deepgram (opt-in)

**Settings → Dictation → "Use Deepgram cloud speech recognition"** turns it on (off by default; enabling asks for
confirmation because your voice recordings leave the computer). It needs `DEEPGRAM_API_KEY` in the per-user file below;
without a key the checkbox is disabled and nothing changes. Live-preview windows and the final clip both go through
Deepgram while it is on (about 2× the recorded audio is sent). Any failure falls back to on-device speech.
`SPATIAL_SPEECH_BACKEND=local` or `nvidia` (environment) always overrides the toggle. The mic tooltip and the Home card
show the real destination ("sent to Deepgram" / "on this computer").

### Details

Batch speech-to-text through Deepgram (`nova-3`) exists as an **opt-in** backend: `SPATIAL_SPEECH_BACKEND=deepgram`.
`auto` never picks it. On any failure the local model answers and the response carries `fallback_reason: deepgram: ...`.
Put the key only in the per-user file `%LOCALAPPDATA%\Spatial\server.env` (the server now reads it; it never overrides a
real environment variable or `server/.env`):

```
DEEPGRAM_API_KEY=your-trial-key
```

The key is never logged, returned by an endpoint, or shown in the UI. Streaming (live transcript) through Deepgram is
**not built**: only add it if the evaluation below shows it beats the current path (see sub-project 7 phase F).

### Result on a synthetic set (2026-10-01, indicative only)

`scripts/make_synthetic_clips.py` speaks the 12 prompts with 3 Windows voices under clean / fast / noisy (10 dB) / quiet
conditions (144 clips, identical audio for both engines). Local = faster-whisper `base` on this CPU; Deepgram = `nova-3`
over the network from India with a kept-alive connection.

| | local | Deepgram |
|---|---|---|
| WER, all prompts | 15.8 % | 11.6 % |
| WER without the numbers prompt ("$4,280" vs words inflates both) | 11.8 % | **7.1 %** |
| clean / fast / noisy / quiet | 8.6 / 10.8 / **14.0** / 9.5 | 6.9 / 6.7 / **6.0** / 5.8 |
| latency p50 / p95 | 870 / 968 ms | **347 / 845 ms** |

Deepgram was clearly better under noise and on names and tech terms; both fail the same way on spoken numbers. Caveat:
synthetic voices are cleaner than people, so absolute numbers are optimistic. Confirm on real recordings
(`scripts/record_clips.py`) before treating this as final. Streaming (live transcript) through Deepgram is still not built.

### Recording a consented test set

```powershell
pip install sounddevice                      # one-time, server venv
python scripts/record_clips.py               # reads 12 prompts aloud -> ~/spatial-speech-clips/{clips,manifest.json}
```

## Dictation quality and latency evaluation

Use a consented, representative set of recordings with human-checked references; keep that set under user control.
Create a JSON manifest with relative audio paths, reference text, optional language, and a non-sensitive clip id:

```json
[{"id":"short-list-01","audio":"clips/short-list-01.wav","reference":"Create a todo list first call Sam then send the notes","language":"en"}]
```

Run each configured path against the identical manifest, preferably in the same session and machine state:

```powershell
py -3.12 scripts/eval_speech.py path/to/manifest.json --backend auto --runs 3
py -3.12 scripts/eval_speech.py path/to/manifest.json --backend nvidia --runs 3
py -3.12 scripts/eval_speech.py path/to/manifest.json --backend local --runs 3
py -3.12 scripts/eval_speech.py path/to/manifest.json --backend deepgram --runs 3   # needs DEEPGRAM_API_KEY
```

The report includes weighted word error rate, failure-penalized WER, fallback use, p50/p95 request latency and real-time
factor. Transcript/reference text is omitted unless `--include-transcripts` is explicitly used. Keep privacy and latency
conditions comparable: hosted NVIDIA sends recordings to NVIDIA; local mode does not. Existing measurements above are
historical and were not measured on a shared evaluation corpus, so they do not establish which backend is more accurate.

SayStride behavior informed hold/toggle interaction, Escape cancellation, spoken punctuation, restart cleanup,
numbered/list formatting and dictionary replacements. Spatial keeps the current Parakeet/Whisper and faster-whisper
pipeline; Jev remains a mark/research judge and is not used to rewrite transcripts. No SayStride source or local model
bundle was copied. Spatial dictation writes an editable draft into its composer and only sends transcript text to the
optional configured-provider polish route.

| Layer | Spatial | SayStride (source inspected locally) |
|---|---|---|
| Primary ASR | Hosted NVIDIA Parakeet for English; Whisper large-v3 for multilingual | Local sherpa-onnx Parakeet int8 for English |
| Fallback / optional ASR | Local faster-whisper `base`; NVIDIA failure falls back locally | faster-whisper fallback; optional Groq Whisper large-v3-turbo, including long clips |
| Text cleanup | Local deterministic commands + user dictionary; optional configured answer provider | Deterministic cleanup/dictionary + optional local Qwen 3.5 4B or cloud polisher |
| Current interaction | Hold/toggle, Escape, final editable draft in Spatial composer | Hold/toggle, Escape, interim replacement into foreground field, final cleanup and safe replace |
| Known measured latency | Historical Spatial run: hosted ~0.48 s after warm-up; local ~5 s warm / 25–30 s cold | No same-device/same-clip benchmark available |

These are architecture observations, not an accuracy ranking: no shared reference corpus/WER results exist yet.
SayStride's Windows implementation has local interim recognition or a Deepgram stream, followed by full-clip
recognition and cleanup. Spatial sends 16 kHz PCM from the composer Dictate action to an authenticated speech worker;
interim text revises the composer draft in place, then the complete recording still goes through `/api/stt` for the
final transcript. When hosted streaming is unavailable or disabled, Spatial recognizes bounded 3-second windows
locally with 0.5-second overlap; it does not repeatedly send an ever-growing recording. The configured NVIDIA
Parakeet function currently rejects online recognition, so it uses the same local-window fallback. Live recognition
is currently English; external-app insertion remains final-only so live revisions cannot overwrite intervening
keystrokes or text in a changed focus target.

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
On Windows, if that optional package/model is absent or fails to load, the desktop server uses the built-in SAPI
system voice and returns a WAV. This fallback adds no model download and is reported in `/api/health`.

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
