"""Resolver eval CLI.
  python scripts/eval.py cases [--resolver geometry|hybrid] [--record] [--json] [--baseline server/tests/eval_baseline.json] [--write-baseline PATH]
  python scripts/eval.py traces <log dir> [--json]
Exits 1 when --baseline is given and top-1 dropped by more than 2 points."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from app import evaluation  # noqa: E402

TESTS = ROOT / "server" / "tests"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("mode", choices=["cases", "traces"])
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--baseline")
    parser.add_argument("--write-baseline")
    parser.add_argument("--resolver", choices=["geometry", "hybrid"], default="geometry")
    parser.add_argument("--record", action="store_true", help="hybrid: call System One live and save answers to the cassette")
    args = parser.parse_args()
    cassette_path = TESTS / "system_one_cassette.json"
    if args.mode == "cases":
        cases = evaluation.load_cases([TESTS / "cases", TESTS / "eval_cases"])
        if args.resolver == "hybrid":
            cassette = evaluation.load_cassette(cassette_path)
            results = [evaluation.run_case_hybrid(c, cassette, record=args.record) for c in cases]
            if args.record:
                evaluation.save_cassette(cassette_path, cassette)
        else:
            results = [evaluation.run_case(c) for c in cases]
    else:
        if not args.directory:
            parser.error("traces mode needs a log directory")
        results = [
            evaluation.run_trace(r)
            for r in evaluation.load_traces(Path(args.directory))
        ]
    summary = evaluation.summarize(results)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(
            f"cases {summary['cases']}  top1 {summary['top1']:.1%}  top3 {summary['top3']:.1%}  "
            f"abstain {summary['abstain_rate']:.1%}  p50 {summary['p50_ms']} ms  p95 {summary['p95_ms']} ms"
        )
        for name, block in summary["by_category"].items():
            print(
                f"  {name:<11} n={block['cases']:<3} top1 {block['top1']:.1%}  top3 {block['top3']:.1%}"
            )
        if summary["failures"]:
            print("  top-1 misses:", ", ".join(summary["failures"]))
    if args.write_baseline:
        Path(args.write_baseline).write_text(
            json.dumps(
                {
                    k: summary[k]
                    for k in ("cases", "top1", "top3", "abstain_rate", "by_category")
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        if summary["top1"] < baseline["top1"] - 0.02:
            print(
                f"REGRESSION: top1 {summary['top1']:.1%} < baseline {baseline['top1']:.1%} - 2pt"
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
