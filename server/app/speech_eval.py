"""Small, content-safe ASR metrics shared by the offline speech evaluator and tests."""
from __future__ import annotations

import re
import math


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.casefold())


def word_errors(reference: str, hypothesis: str) -> tuple[int, int]:
    expected, actual = words(reference), words(hypothesis)
    if not expected:
        return (0 if not actual else len(actual)), len(expected)
    previous = list(range(len(actual) + 1))
    for i, word in enumerate(expected, 1):
        current = [i]
        for j, candidate in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (word != candidate)))
        previous = current
    return previous[-1], len(expected)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))]


def summarize(rows: list[dict]) -> dict:
    usable = [row for row in rows if row.get("status") == "ok"]
    # ponytail: failed clips count as deleted words; otherwise a backend can look accurate by failing hard clips.
    errors = sum(int(row.get("word_errors", row.get("reference_words", 0))) for row in rows)
    words_count = sum(int(row.get("reference_words", 0)) for row in rows)
    latencies = [float(row["latency_ms"]) for row in rows if "latency_ms" in row]
    factors = [float(row["real_time_factor"]) for row in usable]
    return {
        "clips": len(rows), "successful": len(usable),
        "fallback_clips": sum(bool(row.get("used_fallback")) for row in rows),
        "wer": round(errors / words_count, 4) if words_count else (1.0 if errors else (0.0 if usable else None)),
        "successful_clip_wer": round(sum(int(row["word_errors"]) for row in usable) /
                                       sum(int(row["reference_words"]) for row in usable), 4)
        if sum(int(row["reference_words"]) for row in usable) else None,
        "latency_ms_p50": round(percentile(latencies, 0.50), 1),
        "latency_ms_p95": round(percentile(latencies, 0.95), 1),
        "real_time_factor_p50": round(percentile(factors, 0.50), 3),
    }
