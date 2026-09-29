"""Stage a source-only copy and run Strix against that isolated copy."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOTS = {"server", "extension", "desktop", "scripts", "schema", "docs"}
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".json", ".toml", ".lock", ".md", ".ps1"}
EXCLUDED_PARTS = {".git", ".venv", ".build-venv", ".security-venv", "__pycache__", "node_modules",
                  "target", "build", "dist", "resources", "strix_runs", "brag-output"}


def source_files() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, check=True, capture_output=True)
    selected = []
    for raw in result.stdout.decode("utf-8").split("\0"):
        if not raw:
            continue
        relative = Path(raw)
        name = relative.name.lower()
        if relative.parts[0] not in ALLOWED_ROOTS and raw not in {"README.md", ".gitignore"}:
            continue
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if name.startswith(".env") or any(term in name for term in (".token", "credential", "secret", ".pem", ".key")):
            continue
        if relative.suffix.lower() not in SOURCE_SUFFIXES and raw != ".gitignore":
            continue
        path = ROOT / relative
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            continue
        selected.append(relative)
    return sorted(set(selected))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--mode", choices=["quick", "standard", "deep"], default="standard")
    parser.add_argument("--max-budget", type=float, default=5)
    args = parser.parse_args()
    if args.max_budget <= 0:
        parser.error("--max-budget must be positive")
    if not args.prepare_only:
        if not os.environ.get("STRIX_LLM") or not os.environ.get("LLM_API_KEY"):
            parser.error("set STRIX_LLM and LLM_API_KEY in your environment first")
        subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = ROOT / ".security" / stamp
    target = output / "source"
    target.mkdir(parents=True)
    files = source_files()
    for relative in files:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    (output / "source-manifest.json").write_text(json.dumps([p.as_posix() for p in files], indent=2), encoding="utf-8")
    print(f"Prepared {len(files)} files in {target}")
    if args.prepare_only:
        print(f"Review {output / 'source-manifest.json'} before running a scan.")
        return 0
    executable = ROOT / ".security-venv" / "Scripts" / "strix.exe"
    cli = str(executable) if executable.is_file() else shutil.which("strix")
    if not cli:
        parser.error("Strix is not installed; see docs/security/STRIX.md")
    command = [cli, "-n", "--target", str(target), "--scope-mode", "full", "--scan-mode", args.mode,
               "--max-budget", str(args.max_budget), "--instruction-file", str(ROOT / "docs/security/strix-scope.md")]
    return subprocess.run(command, cwd=output, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
