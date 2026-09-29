import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.speech_eval import summarize, word_errors


def test_word_error_rate_counts_substitutions_insertions_and_deletions():
    assert word_errors("make a todo list", "make the todo list") == (1, 4)
    assert word_errors("first item", "first") == (1, 2)
    assert word_errors("first", "first and second") == (2, 1)


def test_summary_reports_weighted_wer_and_latency_without_transcripts():
    result = summarize([
        {"status": "ok", "word_errors": 1, "reference_words": 4, "latency_ms": 400, "real_time_factor": 0.2},
        {"status": "ok", "word_errors": 0, "reference_words": 6, "latency_ms": 800, "real_time_factor": 0.4},
        {"status": "error"},
    ])
    assert result == {"clips": 3, "successful": 2, "fallback_clips": 0, "wer": 0.1,
                      "successful_clip_wer": 0.1, "latency_ms_p50": 400,
                      "latency_ms_p95": 800, "real_time_factor_p50": 0.2}


def test_failures_are_deletions_in_weighted_wer_and_latency():
    result = summarize([
        {"status": "ok", "word_errors": 1, "reference_words": 5, "latency_ms": 300,
         "real_time_factor": 0.1, "used_fallback": True},
        {"status": "unavailable", "word_errors": 5, "reference_words": 5, "latency_ms": 900},
    ])
    assert result["wer"] == 0.6
    assert result["successful_clip_wer"] == 0.2
    assert result["fallback_clips"] == 1
    assert result["latency_ms_p95"] == 900
