"""PostToolUse checks for invariants that break silently:
- geometry.js / resolver.py must rank identically (golden parity tests)
- contracts.py changes must regenerate schema/spatial-context.v3.json
- desktop UI scripts get a syntax check + the desktop node tests; Rust changes run `cargo test`;
  Tauri config / capability JSON must parse
On failure exit 2 so the test tail is fed back to Claude."""

import json
import os
import shutil
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
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)
    return result.returncode, (result.stdout + result.stderr)[-1500:]


def json_ok(file):
    try:
        json.loads(Path(file).read_text(encoding="utf-8"))
        return 0, ""
    except Exception as exc:  # report the parse error to Claude
        return 1, f"{file}: {exc}"


env = {**os.environ, "PATH": os.environ.get("PATH", "") + os.pathsep + str(Path.home() / ".cargo" / "bin")}
steps = []
if "/desktop/ui/" in path and path.endswith(".js") and not path.endswith("/geometry.js"):
    node = shutil.which("node")
    if node:
        steps = [
            ([node, "--check", data["tool_input"]["file_path"]], ROOT),
            ([node, "--test", *map(str, (ROOT / "desktop" / "tests").glob("*.cjs"))], ROOT / "desktop"),
        ]
elif "/desktop/src-tauri/src/" in path and path.endswith(".rs"):
    steps = [(["cargo", "test", "--bin", "spatial-desktop"], ROOT / "desktop" / "src-tauri")]
elif "/desktop/src-tauri/" in path and path.endswith(".json") and "/gen/" not in path and "/target/" not in path:
    steps = [(json_ok, data["tool_input"]["file_path"])]
elif path.endswith("extension/geometry.js") or path.endswith("server/app/resolver.py"):
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
    code, tail = args(cwd) if callable(args) else run(args, cwd)
    if code != 0:
        print(f"Invariant check failed after editing {path}:\n{tail}", file=sys.stderr)
        sys.exit(2)
