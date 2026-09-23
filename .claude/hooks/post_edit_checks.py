"""PostToolUse checks for invariants that break silently:
- geometry.js / resolver.py must rank identically (golden parity tests)
- contracts.py changes must regenerate schema/spatial-context.v3.json
On failure exit 2 so the test tail is fed back to Claude."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
data = json.load(sys.stdin)
path = (
    str((data.get("tool_input") or {}).get("file_path") or "")
    .replace("\\", "/")
    .lower()
)


def run(args, cwd):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr)[-1500:]


steps = []
if path.endswith("extension/geometry.js") or path.endswith("server/app/resolver.py"):
    steps = [
        (
            [sys.executable, "-m", "pytest", "-q", "tests/test_resolver_cases.py"],
            ROOT / "server",
        )
    ]
elif path.endswith("server/app/contracts.py"):
    steps = [
        ([sys.executable, "scripts/export_schema.py"], ROOT),
        (
            [sys.executable, "-m", "pytest", "-q", "tests/test_schema.py"],
            ROOT / "server",
        ),
    ]

for args, cwd in steps:
    code, tail = run(args, cwd)
    if code != 0:
        print(f"Invariant check failed after editing {path}:\n{tail}", file=sys.stderr)
        sys.exit(2)
