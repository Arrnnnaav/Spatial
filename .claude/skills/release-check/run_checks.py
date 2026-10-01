"""Run the Spatial release gate in order and print one pass/fail table.

  python .claude/skills/release-check/run_checks.py            # fast suites + eval + schema drift
  python .claude/skills/release-check/run_checks.py --build    # also the release build + packaged-server smoke test

Exit code is 0 only if every step passed. Output per step is kept short (last lines on failure).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable
ENV = {
    **os.environ,
    "PATH": os.environ.get("PATH", "")
    + os.pathsep
    + str(Path.home() / ".cargo" / "bin"),
}
ISOLATED_SERVER = ROOT / "server"


def steps(build: bool):
    node_desktop = sorted(str(p) for p in (ROOT / "desktop" / "tests").glob("*.cjs"))
    out = [
        ("server pytest", [PY, "-m", "pytest", "-q"], ISOLATED_SERVER),
        (
            "extension geometry",
            ["node", "--test", "tests/geometry.test.mjs"],
            ROOT / "extension",
        ),
        ("desktop JS", ["node", "--test", *node_desktop], ROOT / "desktop"),
        (
            "desktop Rust",
            ["cargo", "test", "--bin", "spatial-desktop"],
            ROOT / "desktop" / "src-tauri",
        ),
        (
            "resolver eval",
            [
                PY,
                "scripts/eval.py",
                "cases",
                "--baseline",
                "server/tests/eval_baseline.json",
            ],
            ROOT,
        ),
        ("schema drift", [PY, "scripts/export_schema.py"], ROOT),
    ]
    if build:
        out += [
            (
                "release build",
                ["powershell", "-NoProfile", "-File", "desktop/build-release.ps1"],
                ROOT,
            ),
            ("packaged smoke", [PY, "desktop/tests/bundled_server_smoke.py"], ROOT),
        ]
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--build",
        action="store_true",
        help="include the (slow) release build and packaged smoke test",
    )
    args = parser.parse_args()
    rows = []
    for name, cmd, cwd in steps(args.build):
        started = time.time()
        try:
            done = subprocess.run(
                cmd, cwd=cwd, env=ENV, capture_output=True, text=True, timeout=3600
            )
            ok, tail = (
                done.returncode == 0,
                (done.stdout + done.stderr).strip().splitlines()[-4:],
            )
        except Exception as exc:  # missing tool, timeout
            ok, tail = False, [f"{type(exc).__name__}: {exc}"]
        if (
            name == "schema drift" and ok
        ):  # export rewrites the file; any diff means the committed schema is stale
            diff = subprocess.run(
                ["git", "diff", "--stat", "--", "schema"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            ).stdout.strip()
            ok, tail = (
                (not diff),
                (
                    ["schema/ differs from the committed version", diff]
                    if diff
                    else tail
                ),
            )
        rows.append((name, ok, time.time() - started, tail))
        print(f"{'PASS' if ok else 'FAIL'}  {name:<20} {rows[-1][2]:6.1f}s", flush=True)
        if not ok:
            print("      " + "\n      ".join(tail), flush=True)
    failed = [r[0] for r in rows if not r[1]]
    print(
        "\nRELEASE GATE:",
        "ALL PASSED" if not failed else "FAILED -> " + ", ".join(failed),
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
