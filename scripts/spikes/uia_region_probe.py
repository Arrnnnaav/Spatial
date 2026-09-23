"""THROWAWAY SPIKE (sub-project 3): what does Windows UI Automation give us for a screen region, and does it feed
Spatial's v3 contract end to end?

For each target window: take a box in the middle of the window (the "mark"), collect UIA elements whose bounding
rectangle intersects it, turn them into v3 CandidateObjects (source="uia") and POST a v3 ask to a running server.
Only windows this script launched itself are read (never your editor/browser: they may show secrets).

    python scripts/spikes/uia_region_probe.py [--server http://127.0.0.1:8796]
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import json
import subprocess
import tempfile
import time
from pathlib import Path

import comtypes.client
import httpx
import win32gui

ctypes.windll.shcore.SetProcessDpiAwareness(
    2
)  # per-monitor DPI aware: UIA rects == physical screen pixels
comtypes.client.GetModule("UIAutomationCore.dll")
from comtypes.gen import UIAutomationClient as UIA  # noqa: E402

AUTOMATION = comtypes.client.CreateObject(
    UIA.CUIAutomation, interface=UIA.IUIAutomation
)
CONTROL_TYPES = {
    getattr(UIA, n): n.replace("UIA_", "").replace("ControlTypeId", "")
    for n in dir(UIA)
    if n.startswith("UIA_") and n.endswith("ControlTypeId")
}
ROOT = Path(__file__).resolve().parents[2]


def launch_targets() -> list[subprocess.Popen]:
    sample = Path(tempfile.gettempdir()) / "spatial_uia_sample.txt"
    sample.write_text(
        "Gradient descent updates each weight against the gradient.\n"
        "The learning rate controls the step size.\n"
        "Momentum smooths the path.\n",
        encoding="utf-8",
    )
    return [
        subprocess.Popen(["notepad.exe", str(sample)]),
        subprocess.Popen(["calc.exe"]),
        subprocess.Popen(["explorer.exe", str(ROOT / "docs")]),
    ]


def find_window(title_part: str) -> int | None:
    found = []

    def cb(hwnd, _):
        # Exact title (or "<file>.<ext> - App") only: never pick up a browser tab or editor that merely mentions it.
        title = win32gui.GetWindowText(hwnd).lower()
        wanted = title_part.lower()
        if win32gui.IsWindowVisible(hwnd) and (
            title == wanted
            or title.startswith(wanted + ".")
            or title == wanted + " - file explorer"
        ):
            found.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return found[0] if found else None


def region_elements(
    hwnd: int, region: tuple[int, int, int, int]
) -> tuple[list[dict], float]:
    started = time.perf_counter()
    cache = AUTOMATION.CreateCacheRequest()
    for prop in (
        UIA.UIA_NamePropertyId,
        UIA.UIA_ControlTypePropertyId,
        UIA.UIA_BoundingRectanglePropertyId,
        UIA.UIA_IsOffscreenPropertyId,
        UIA.UIA_ValueValuePropertyId,
        UIA.UIA_AutomationIdPropertyId,
    ):
        cache.AddProperty(prop)
    root = AUTOMATION.ElementFromHandle(hwnd)
    found = root.FindAllBuildCache(
        UIA.TreeScope_Descendants, AUTOMATION.CreateTrueCondition(), cache
    )
    left, top, right, bottom = region
    out = []
    for i in range(found.Length):
        el = found.GetElement(i)
        rect = el.CachedBoundingRectangle
        if el.CachedIsOffscreen or rect.right <= rect.left or rect.bottom <= rect.top:
            continue
        if (
            rect.right < left
            or rect.left > right
            or rect.bottom < top
            or rect.top > bottom
        ):
            continue
        name = (el.CachedName or "").strip()
        try:
            value = (
                el.GetCachedPropertyValue(UIA.UIA_ValueValuePropertyId) or ""
            ).strip()
        except Exception:
            value = ""
        text = name or value
        if not text:
            continue
        out.append(
            {
                "type": CONTROL_TYPES.get(
                    el.CachedControlType, str(el.CachedControlType)
                ),
                "text": text[:300],
                "bbox": {
                    "x": rect.left,
                    "y": rect.top,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                },
                "automation_id": el.CachedAutomationId or "",
            }
        )
    out.extend(text_lines(found, region))
    return out, (time.perf_counter() - started) * 1000


def text_lines(found, region) -> list[dict]:
    """Editors (Notepad, Word, VS Code...) expose text only through TextPattern: sample points in the region,
    expand each to its line, and emit one candidate per distinct line with its real bounding box."""
    left, top, right, bottom = region
    lines, seen = [], set()
    for i in range(found.Length):
        el = found.GetElement(i)
        if el.CachedControlType not in (
            UIA.UIA_DocumentControlTypeId,
            UIA.UIA_EditControlTypeId,
        ):
            continue
        try:
            unknown = el.GetCurrentPattern(UIA.UIA_TextPatternId)
            pattern = unknown.QueryInterface(UIA.IUIAutomationTextPattern)
        except Exception:
            continue
        for fy in (0.1, 0.3, 0.5, 0.7, 0.9):
            point = ctypes.wintypes.POINT(
                int((left + right) / 2), int(top + (bottom - top) * fy)
            )
            try:
                rng = pattern.RangeFromPoint(point)
                rng.ExpandToEnclosingUnit(UIA.TextUnit_Line)
                text = (rng.GetText(400) or "").strip()
                rects = rng.GetBoundingRectangles() or ()
            except Exception:
                continue
            if not text or text in seen or len(rects) < 4:
                continue
            seen.add(text)
            x, y, w, h = rects[0], rects[1], rects[2], rects[3]
            lines.append(
                {
                    "type": "TextLine",
                    "text": text[:300],
                    "bbox": {"x": x, "y": y, "width": w, "height": h},
                    "automation_id": "",
                }
            )
    return lines


def v3_ask(
    app: str, title: str, hwnd: int, region, elements: list[dict], question: str
) -> dict:
    screen_w, screen_h = (
        ctypes.windll.user32.GetSystemMetrics(0),
        ctypes.windll.user32.GetSystemMetrics(1),
    )
    left, top, right, bottom = region
    return {
        "protocol_version": 3,
        "research": False,
        "context": {
            "surface": {
                "kind": "desktop",
                "app": app,
                "window_title": title,
                "viewport": {"width": screen_w, "height": screen_h},
            },
            "marks": [
                {
                    "kind": "rectangle",
                    "bbox": {
                        "x": left,
                        "y": top,
                        "width": right - left,
                        "height": bottom - top,
                    },
                }
            ],
            "candidates": [
                {
                    "candidate_id": f"uia-{i}",
                    "source": "uia",
                    "object_type": e["type"],
                    "text": e["text"],
                    "bbox": e["bbox"],
                    "provenance": {"extractor": "uia-spike"},
                }
                for i, e in enumerate(elements)
            ],
            "question": question,
            "privacy_policy": "anchors_only",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8796")
    args = parser.parse_args()
    procs = launch_targets()
    time.sleep(4)
    opened: list[int] = []
    try:
        targets = [
            ("Notepad", "spatial_uia_sample", "what does this line mean?", (0.05, 0.12, 0.6, 0.3)),
            ("Calculator", "Calculator", "what does this button do?", (0.3, 0.3, 0.7, 0.6)),
            ("Explorer", "docs", "what is this file?", (0.3, 0.3, 0.7, 0.6)),
        ]
        report = []
        for app, title_part, question, box in targets:
            hwnd = find_window(title_part)
            if hwnd:
                opened.append(hwnd)
            if not hwnd:
                report.append({"app": app, "error": "window not found"})
                continue
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            w, h = r - l, b - t
            region = (l + int(w * box[0]), t + int(h * box[1]), l + int(w * box[2]), t + int(h * box[3]))
            elements, ms = region_elements(hwnd, region)
            row = {
                "app": app,
                "window": win32gui.GetWindowText(hwnd)[:60],
                "elements_in_region": len(elements),
                "uia_ms": round(ms),
                "types": sorted({e["type"] for e in elements}),
                "sample": [f"{e['type']}: {e['text'][:50]}" for e in elements[:6]],
            }
            try:
                started = time.perf_counter()
                answer = httpx.post(
                    f"{args.server}/api/ask",
                    json=v3_ask(app, row["window"], hwnd, region, elements, question),
                    timeout=120,
                ).json()
                row.update(
                    {
                        "ask_s": round(time.perf_counter() - started, 1),
                        "target": (answer.get("anchors_used") or [{}])[0].get(
                            "text", ""
                        )[:60],
                        "resolver": (answer.get("resolution_v3") or {}).get("resolver"),
                        "clarify": len(answer.get("clarify") or []),
                        "answer": (answer.get("answer") or answer.get("detail", ""))[
                            :160
                        ]
                        if isinstance(
                            answer.get("answer") or answer.get("detail", ""), str
                        )
                        else answer.get("detail"),
                    }
                )
            except Exception as exc:
                row["ask_error"] = f"{type(exc).__name__}: {exc}"[:160]
            report.append(row)
    finally:
        for hwnd in opened:
            win32gui.PostMessage(
                hwnd, 0x0010, 0, 0
            )  # WM_CLOSE: only windows this spike opened
        for proc in procs:
            proc.terminate()
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
