"""Spatial is standalone: no StudyOS coupling may creep back into shipped code or docs."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERN = re.compile(r"studyos|sync_spatial|quiz|learning-platform", re.I)
SCANNED = [
    ROOT / "extension",
    ROOT / "server" / "app",
    ROOT / "server" / "tests",
    ROOT / "README.md",
    ROOT / "docs",
]
SKIP_PARTS = {"vendor", "__pycache__", ".venv", "superpowers"}
SKIP_FILES = {
    "test_independence.py",
    "SPATIAL_STANDALONE_MASTER_PLAN.md",
    "MEMORY.md",
    "TASKS.md",
    "DESIGN.md",
}


def scanned_files():
    for base in SCANNED:
        paths = [base] if base.is_file() else base.rglob("*")
        for path in paths:
            if (
                path.is_file()
                and path.suffix in {".js", ".py", ".html", ".json", ".md"}
                and not SKIP_PARTS & set(path.parts)
                and path.name not in SKIP_FILES
            ):
                yield path


def test_no_studyos_references():
    offenders = [
        f"{p.relative_to(ROOT)}:{i}"
        for p in scanned_files()
        for i, line in enumerate(
            p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        )
        if PATTERN.search(line)
    ]
    assert offenders == []


def test_dashboard_detector_removed():
    assert not (ROOT / "extension" / "detect.js").exists()
