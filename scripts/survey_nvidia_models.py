"""Survey every NVIDIA NIM chat model visible to your key on three checkable Spatial tasks, through the server's real
provider code (same system prompt, thinking-off template, token budget, streaming parser).

    python scripts/survey_nvidia_models.py [--models a,b,c] [--runs 1] [--out scripts/experiments/results/nvidia_survey.json]

Per model: success rate, median time-to-answer, and correctness per task (keyword checks). The ranking favours
models that answer every task correctly and fast; use it to set NVIDIA_MODEL and NVIDIA_FALLBACK_MODELS."""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import httpx  # noqa: E402

from app import providers  # noqa: E402
from app.config import ProviderConfig, settings  # noqa: E402

SKIP = (
    "embed",
    "reward",
    "safety",
    "guard",
    "rerank",
    "parse",
    "retriever",
    "diffusion",
    "vision",
    "-vl",
    "vila",
    "neva",
    "paligemma",
    "kosmos",
    "deplot",
    "fuyu",
    "clip",
    "omni",
    "audio",
    "asr",
    "tts",
    "coder-6.7b",
    "content-safety",
    "nemoguard",
    "llamaguard",
    "detector",
    "translate",
    "riva",
    "cosmos",
)
TASKS = [
    {
        "name": "math",
        "anchors": [
            {
                "type": "pdf-text",
                "text": "d/dx (x^2) = 2x, so the slope of y = x^2/2 is (2x)/2 = x",
                "is_target": True,
            }
        ],
        "question": "why is this step dividing by 2?",
        "sources": [],
        "check": lambda a: any(
            k in a.lower() for k in ("constant", "1/2", "½", "half", "coefficient")
        ),
    },
    {
        "name": "cited",
        "anchors": [
            {
                "type": "p",
                "text": "Adam optimizer: adaptive moment estimation",
                "is_target": True,
            }
        ],
        "question": "who invented this optimizer and in what year?",
        "sources": [
            {
                "id": 1,
                "url": "https://example.org/adam",
                "title": "Adam history",
                "passages": [
                    "Adam was introduced in 2014 by Diederik Kingma and Jimmy Ba."
                ],
            }
        ],
        "check": lambda a: "2014" in a and "kingma" in a.lower() and "[1]" in a,
    },
    {
        "name": "debug",
        "anchors": [
            {
                "type": "pre",
                "text": "TypeError: Cannot read properties of undefined (reading 'map')",
                "is_target": True,
            }
        ],
        "question": "why am I getting this error?",
        "sources": [],
        "check": lambda a: (
            "undefined" in a.lower()
            and any(
                k in a.lower()
                for k in ("array", "initial", "check", "default", "optional")
            )
        ),
    },
]


def chat_models() -> list[str]:
    cfg = settings.providers["nvidia"]
    data = httpx.get(
        cfg.base_url.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        timeout=30,
    ).json()["data"]
    return sorted(m["id"] for m in data if not any(s in m["id"].lower() for s in SKIP))


def run_task(model: str, task: dict) -> dict:
    base = settings.providers["nvidia"]
    config = ProviderConfig(
        "nvidia", base.base_url, base.api_key, model, None, "openai"
    )
    providers._SYSTEM_OVERRIDE["prompt"] = (
        providers.RESEARCH_SYSTEM if task["sources"] else providers.SYSTEM_PROMPT
    )
    providers._SYSTEM_OVERRIDE["level"] = None
    providers._SYSTEM_OVERRIDE["mode"] = None
    prompt = providers.build_prompt(
        task["question"],
        {"title": "Notes", "surface": "web"},
        task["anchors"],
        "",
        [],
        task["sources"],
    )
    started = time.perf_counter()
    try:
        text = "".join(
            item
            for item in providers.stream_provider(config, prompt, None, False)
            if isinstance(item, str)
        )
        text = providers.clean_answer(text)
        return {
            "ok": bool(text),
            "correct": bool(text) and task["check"](text),
            "seconds": round(time.perf_counter() - started, 1),
            "answer": text[:300],
        }
    except Exception as exc:
        code, message = providers.classify_error(exc)
        return {
            "ok": False,
            "correct": False,
            "seconds": round(time.perf_counter() - started, 1),
            "error": f"{code}: {message}",
        }


def survey(model: str, runs: int) -> dict:
    results = {
        task["name"]: [run_task(model, task) for _ in range(runs)] for task in TASKS
    }
    flat = [r for rs in results.values() for r in rs]
    ok_times = [r["seconds"] for r in flat if r["ok"]]
    return {
        "model": model,
        "success": sum(r["ok"] for r in flat) / len(flat),
        "correct": sum(r["correct"] for r in flat) / len(flat),
        "median_s": statistics.median(ok_times) if ok_times else None,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument(
        "--out", default=str(ROOT / "scripts/experiments/results/nvidia_survey.json")
    )
    args = parser.parse_args()
    settings.timeout_seconds = 30.0
    models = args.models.split(",") if args.models else chat_models()
    print(
        f"surveying {len(models)} models x {len(TASKS)} tasks x {args.runs} runs",
        flush=True,
    )
    rows = []
    with cf.ThreadPoolExecutor(6) as pool:
        for row in pool.map(lambda m: survey(m, args.runs), models):
            rows.append(row)
            print(
                f"{row['model']:<55} ok {row['success']:.0%} correct {row['correct']:.0%} median {row['median_s']}s",
                flush=True,
            )
    rows.sort(key=lambda r: (-r["correct"], -r["success"], r["median_s"] or 999))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print("\nTOP 10")
    for row in rows[:10]:
        print(
            f"  {row['model']:<55} correct {row['correct']:.0%} ok {row['success']:.0%} median {row['median_s']}s"
        )


if __name__ == "__main__":
    main()
