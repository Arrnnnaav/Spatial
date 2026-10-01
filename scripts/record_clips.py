"""Record your own consented speech clips for the Spatial speech eval (scripts/eval_speech.py).

You read each prompt aloud; the script saves a 16 kHz mono WAV per prompt plus a manifest.json whose references are
the prompts. Nothing leaves your machine here. Keep the output folder private (it is outside the repo by default).

  pip install sounddevice            # one-time, in the server venv
  python scripts/record_clips.py                      # records into ~/spatial-speech-clips
  python scripts/record_clips.py --out D:/clips --list-devices

Per clip: press Enter, speak, press Enter again to stop. Type r + Enter to redo a clip, s + Enter to skip it.
Then compare engines on the SAME clips:
  python scripts/eval_speech.py ~/spatial-speech-clips/manifest.json --backend local    --runs 3
  python scripts/eval_speech.py ~/spatial-speech-clips/manifest.json --backend nvidia   --runs 3
  python scripts/eval_speech.py ~/spatial-speech-clips/manifest.json --backend deepgram --runs 3
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path

RATE = 16000

# Reads like real dictation: commands, lists, numbers, names, product terms, a longer paragraph.
PROMPTS = [
    ("short-01", "Call Sam tomorrow about the budget review."),
    ("short-02", "Move the meeting to Thursday at three thirty."),
    (
        "list-01",
        "Create a todo list first call Sam then send the notes then book the room.",
    ),
    ("punct-01", "Please send the draft today comma and copy Priya period"),
    (
        "numbers-01",
        "The invoice total is four thousand two hundred and eighty dollars, due on October fourteenth.",
    ),
    (
        "names-01",
        "Ask Arnav and Meera whether the Tauri build passed on the Windows laptop.",
    ),
    (
        "tech-01",
        "The FastAPI server stores history in SQLite and calls the answer provider over HTTPS.",
    ),
    ("tech-02", "Open the dashboard, check the reminders, and clear the activity log."),
    ("restart-01", "Send it on Friday scratch that send it on Monday morning."),
    (
        "long-01",
        "I looked at the numbers again this morning and the trend is clear, revenue is flat but support tickets are up, so we should hire before the next release.",
    ),
    ("quiet-01", "Remind me to water the plants tonight."),
    (
        "fast-01",
        "Thanks everyone, see you at the stand up, I will share the notes right after.",
    ),
]


def record_one(sd, np):
    """Record until Enter is pressed again; returns int16 mono samples at 16 kHz."""
    frames = []

    def callback(indata, _frames, _time, _status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", callback=callback):
        input("  recording... press Enter to stop ")
    return np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--out", type=Path, default=Path.home() / "spatial-speech-clips"
    )
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()
    try:
        import numpy as np
        import sounddevice as sd
    except ImportError:
        print("Missing dependency: pip install sounddevice numpy", file=sys.stderr)
        return 2
    if args.list_devices:
        print(sd.query_devices())
        return 0
    clips_dir = args.out / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else []
    )
    done = {item["id"] for item in manifest}
    print(
        f"Saving to {args.out}. Only you hear/see these clips; they are never uploaded by this script.\n"
    )
    for clip_id, text in PROMPTS:
        if clip_id in done:
            continue
        while True:
            print(f'[{clip_id}] Read aloud:\n  "{text}"')
            choice = input("  Enter = record, s = skip, q = quit: ").strip().lower()
            if choice == "q":
                manifest_path.write_text(
                    json.dumps(manifest, indent=2), encoding="utf-8"
                )
                return 0
            if choice == "s":
                break
            samples = record_one(sd, np)
            seconds = len(samples) / RATE
            if seconds < 0.5:
                print("  too short, try again")
                continue
            path = clips_dir / f"{clip_id}.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(samples.tobytes())
            print(f"  saved {path.name} ({seconds:.1f} s)")
            if input("  keep it? Enter = yes, r = redo: ").strip().lower() == "r":
                continue
            manifest.append(
                {
                    "id": clip_id,
                    "audio": f"clips/{clip_id}.wav",
                    "reference": text,
                    "language": "en",
                }
            )
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            break
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nDone: {len(manifest)} clips. Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
