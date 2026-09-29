"""Score a local, user-supplied speech fixture manifest without printing transcripts by default.

Manifest JSON: [{"id":"clip-1", "audio":"audio/clip-1.wav", "reference":"expected words", "language":"en"}]
Run from the repo root: py -3.12 scripts/eval_speech.py path/to/manifest.json --backend local
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app import audio  # noqa: E402
from app.config import settings  # noqa: E402
from app.speech_eval import summarize, word_errors, words  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--backend", choices=("auto", "nvidia", "local"), default="auto")
    parser.add_argument("--runs", type=int, default=1, help="repeat each clip for a more stable latency sample")
    parser.add_argument("--include-transcripts", action="store_true", help="include recognized and reference text in output")
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error("--runs must be between 1 and 20")
    manifest = args.manifest.resolve()
    cases = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        parser.error("manifest must be a non-empty JSON array")
    settings.speech_backend = args.backend
    rows = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or not isinstance(case.get("reference"), str) or not isinstance(case.get("audio"), str):
            parser.error(f"manifest item {index} needs string audio and reference fields")
        path = (manifest.parent / case["audio"]).resolve()
        if not path.is_file():
            parser.error(f"audio file does not exist for item {index}")
        data = path.read_bytes()
        for run in range(args.runs):
            started = time.perf_counter()
            ref_words = len(words(case["reference"]))
            try:
                result = audio.transcribe(data, case.get("language"))
                elapsed_ms = (time.perf_counter() - started) * 1000
                if result.get("status") != "ok":
                    row = {"id": case.get("id", str(index)), "status": result.get("status", "error"),
                           "word_errors": ref_words, "reference_words": ref_words,
                           "latency_ms": round(elapsed_ms, 1), "backend": result.get("backend", "unknown")}
                else:
                    recognized = str(result.get("text", ""))
                    edits, ref_words = word_errors(case["reference"], recognized)
                    duration = float(result.get("duration", 0) or 0)
                    row = {"id": case.get("id", str(index)), "status": "ok", "word_errors": edits,
                           "reference_words": ref_words, "latency_ms": round(elapsed_ms, 1),
                           "real_time_factor": round(elapsed_ms / 1000 / duration, 3) if duration else 0.0,
                           "backend": result.get("backend", "unknown"), "model": result.get("model", "unknown")}
                    if result.get("fallback_reason"):
                        row["used_fallback"] = True
                    if args.include_transcripts:
                        row.update(reference=case["reference"], transcript=recognized)
            except Exception as exc:  # report safe categories only; never dump provider details or audio/text
                elapsed_ms = (time.perf_counter() - started) * 1000
                row = {"id": case.get("id", str(index)), "status": "error", "error": type(exc).__name__,
                       "word_errors": ref_words, "reference_words": ref_words, "latency_ms": round(elapsed_ms, 1)}
            if args.runs > 1:
                row["run"] = run + 1
            rows.append(row)
    output = {"requested_backend": args.backend, "summary": summarize(rows), "results": rows}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if all(row["status"] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
