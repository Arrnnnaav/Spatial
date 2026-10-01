"""Build a SYNTHETIC speech eval set (no human recording needed) for scripts/eval_speech.py.

The 12 dictation prompts from record_clips.py are spoken by every installed Windows (SAPI) voice under four conditions:
clean, fast, noisy (10 dB SNR white noise), quiet (low level + noise floor). Output: <out>/clips/*.wav + manifest.json.

  python scripts/make_synthetic_clips.py --out ~/spatial-synth-clips

CAVEAT: synthetic voices are clean and regular, so word error rates are optimistic and differences between engines are
compressed. Use this to smoke-test pipelines and compare latency and robustness to noise/speed; confirm any decision on
real recordings (scripts/record_clips.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record_clips import PROMPTS  # noqa: E402

RATE = 16000
CONDITIONS = ("clean", "fast", "noisy", "quiet")


def speak(text: str, voice_index: int, rate: int) -> np.ndarray:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        stream = win32com.client.Dispatch("SAPI.SpMemoryStream")
        stream.Format.Type = 18  # 16 kHz, 16-bit, mono
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Voice = speaker.GetVoices().Item(voice_index)
        speaker.Rate = rate
        speaker.AudioOutputStream = stream
        speaker.Speak(text)
        return np.frombuffer(bytes(stream.GetData()), dtype="<i2").astype(np.float32)
    finally:
        pythoncom.CoUninitialize()


def with_noise(
    samples: np.ndarray, snr_db: float, rng: np.random.Generator
) -> np.ndarray:
    power = float(np.mean(samples**2)) or 1.0
    noise = rng.normal(0, np.sqrt(power / (10 ** (snr_db / 10))), samples.shape)
    return samples + noise


def render(
    text: str, voice: int, condition: str, rng: np.random.Generator
) -> np.ndarray:
    samples = speak(text, voice, 5 if condition == "fast" else 0)
    if condition == "noisy":
        samples = with_noise(samples, 10, rng)
    elif condition == "quiet":
        samples = with_noise(samples * 0.12, 20, rng)
    return np.clip(samples, -32768, 32767).astype("<i2")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=Path.home() / "spatial-synth-clips")
    args = parser.parse_args()
    import win32com.client

    voices = win32com.client.Dispatch("SAPI.SpVoice").GetVoices()
    rng = np.random.default_rng(7)  # fixed seed: both engines hear identical noise
    (args.out / "clips").mkdir(parents=True, exist_ok=True)
    manifest = []
    for voice in range(voices.Count):
        label = (
            voices.Item(voice)
            .GetDescription()
            .split(" - ")[0]
            .replace("Microsoft ", "")
            .replace(" Desktop", "")
            .lower()
        )
        language = (
            "en-GB"
            if "great britain" in voices.Item(voice).GetDescription().lower()
            else "en"
        )
        for clip_id, text in PROMPTS:
            for condition in CONDITIONS:
                name = f"{label}-{condition}-{clip_id}"
                pcm = render(text, voice, condition, rng)
                with wave.open(str(args.out / "clips" / f"{name}.wav"), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(RATE)
                    wav.writeframes(pcm.tobytes())
                manifest.append(
                    {
                        "id": name,
                        "audio": f"clips/{name}.wav",
                        "reference": text,
                        "language": language,
                    }
                )
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"{len(manifest)} synthetic clips -> {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
