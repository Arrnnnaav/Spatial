"""Desktop surface (sub-project 4): freeze the monitor under the cursor, then read UI Automation elements and editor
text lines (TextPattern) for the region the user marked, plus OCR of the frozen frame. Windows-only; the Tauri
overlay (desktop/) only draws, the server owns pixels and OS access. Proven in scripts/spikes/uia_region_probe.py.

Coordinates: the captured monitor in physical pixels, origin at its top-left (the process is per-monitor DPI aware)."""

from __future__ import annotations

import base64
import hmac
import io
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.candidates import merge, ocr_candidates
from app.config import settings
from app.contracts import BBox, CandidateObject, CropInfo, Provenance
from app.ocr import ocr_blocks

logger = logging.getLogger("spatial.desktop")
SUPPORTED = sys.platform == "win32"
MAX_CAPTURES = 3
CAPTURE_TTL_SECONDS = 300
CROP_PADDING = 28
# Never read these windows' contents, even when they sit on top of the mark.
SENSITIVE_PROCESSES = {
    "keepass.exe",
    "keepassxc.exe",
    "1password.exe",
    "bitwarden.exe",
    "lastpass.exe",
    "dashlane.exe",
    "enpass.exe",
    "credentialuibroker.exe",
    "consent.exe",
    "logonui.exe",
    "keeper.exe",
    "keeperpasswordmanager.exe",
    "roboform.exe",
    "nordpass.exe",
    "proton pass.exe",
    "protonpass.exe",
}
# Portable / renamed builds: also match the window title.
SENSITIVE_TITLE_WORDS = ("keepass", "1password", "bitwarden", "lastpass", "dashlane", "enpass", "keeper",
                         "roboform", "nordpass", "proton pass", "password manager")
TOKEN_HEADER = "X-Spatial-Desktop"
_captures: "OrderedDict[str, dict]" = OrderedDict()
_lock = threading.Lock()
_token: str | None = None


def _token_path() -> Path:
    override = os.environ.get("SPATIAL_DESKTOP_TOKEN_FILE")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".spatial")
    return Path(base) / "Spatial" / "desktop.token"


def session_token() -> str:
    """Per-launch secret shared with the desktop app through a file only the local user can read. Screen capture must
    never be reachable by a web page on this machine, even with SPATIAL_API_TOKEN unset."""
    global _token
    with _lock:
        if _token is None:
            _token = secrets.token_urlsafe(32)
            path = _token_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(_token, encoding="utf-8")
        return _token


def token_ok(value: str | None) -> bool:
    return bool(value) and hmac.compare_digest(value, session_token())


class CaptureNotFound(KeyError):
    pass


# --- OS access (replaced in tests) --------------------------------------------------------------------------


def _dpi_aware() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass


def _grab_monitor():
    """Screenshot of the monitor under the cursor -> (PIL image, {x, y, width, height})."""
    import mss
    import win32api
    from PIL import Image

    _dpi_aware()
    cx, cy = win32api.GetCursorPos()
    with mss.mss() as sct:
        monitors = sct.monitors[1:] or sct.monitors
        mon = next(
            (
                m
                for m in monitors
                if m["left"] <= cx < m["left"] + m["width"]
                and m["top"] <= cy < m["top"] + m["height"]
            ),
            monitors[0],
        )
        shot = sct.grab(mon)
        image = Image.frombytes("RGB", shot.size, shot.rgb)
    return image, {
        "x": mon["left"],
        "y": mon["top"],
        "width": mon["width"],
        "height": mon["height"],
    }


def _cloaked(hwnd: int) -> bool:
    """Windows 11 keeps suspended UWP apps / other-desktop windows 'visible' but cloaked (not on screen)."""
    import ctypes
    import ctypes.wintypes
    value = ctypes.c_int(0)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.wintypes.HWND(hwnd), 14, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        return False
    return bool(value.value)


def _windows_topdown() -> list[dict]:
    """Visible top-level windows, topmost first: {hwnd, pid, process, title, rect=(l, t, r, b)}."""
    import win32api
    import win32con
    import win32gui
    import win32process

    _dpi_aware()
    out: list[dict] = []

    def visit(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd) or _cloaked(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = ""
        try:
            handle = win32api.OpenProcess(
                win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
            process = win32process.GetModuleFileNameEx(handle, 0).rsplit("\\", 1)[-1]
        except Exception:
            pass  # elevated / protected process: name unknown, contents still readable via UIA or not at all
        out.append(
            {
                "hwnd": hwnd,
                "pid": pid,
                "process": process,
                "title": title,
                "rect": win32gui.GetWindowRect(hwnd),
            }
        )

    win32gui.EnumWindows(visit, None)
    return out


def _uia_read(hwnd: int, region: tuple[int, int, int, int], pid: int | None = None) -> list[dict]:
    """UIA elements under a grid of points in the screen-pixel region (plus a few ancestors each), from `pid` only,
    plus editor lines via TextPattern. Point probes are ~100x cheaper than walking a big window's whole tree and
    follow real z-order; the overlay must be hidden while this runs (the client does that after the mark)."""
    import ctypes.wintypes

    import comtypes.client
    import pythoncom
    pythoncom.CoInitialize()  # FastAPI runs sync endpoints on worker threads
    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA
    automation = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
    walker = automation.ControlViewWalker
    names = {getattr(UIA, n): n.replace("UIA_", "").replace("ControlTypeId", "") for n in dir(UIA)
             if n.startswith("UIA_") and n.endswith("ControlTypeId")}
    left, top, right, bottom = region
    out: list[dict] = []
    seen: set[tuple] = set()
    text_hosts: list = []
    steps = 6
    for i in range(steps + 1):
        for j in range(steps + 1):
            point = ctypes.wintypes.POINT(int(left + (right - left) * i / steps), int(top + (bottom - top) * j / steps))
            try:
                element = automation.ElementFromPoint(point)
            except Exception:
                continue
            for _ in range(4):  # the element and a few ancestors (a button's group, a line's document)
                if element is None:
                    break
                try:
                    if pid is not None and element.CurrentProcessId != pid:
                        break
                    if element.CurrentIsPassword:
                        element = walker.GetParentElement(element)
                        continue
                    rect = element.CurrentBoundingRectangle
                    key = (element.CurrentControlType, rect.left, rect.top, rect.right, rect.bottom)
                    if key not in seen:
                        seen.add(key)
                        control = names.get(element.CurrentControlType, str(element.CurrentControlType))
                        text = (element.CurrentName or "").strip()
                        if not text:
                            try:
                                value = element.GetCurrentPropertyValue(UIA.UIA_ValueValuePropertyId)
                                text = (value or "").strip() if isinstance(value, str) else ""
                            except Exception:
                                text = ""
                        if text and rect.right > rect.left and rect.bottom > rect.top:
                            out.append({"type": control, "text": text[:1500], "bbox": {"x": rect.left, "y": rect.top,
                                        "width": rect.right - rect.left, "height": rect.bottom - rect.top}})
                        if element.CurrentControlType in (UIA.UIA_DocumentControlTypeId, UIA.UIA_EditControlTypeId):
                            text_hosts.append(element)
                    element = walker.GetParentElement(element)
                except Exception:
                    break
    for host in text_hosts[:3]:
        out.extend(_text_lines(host, UIA, region))
    return out


def _text_lines(element, UIA, region) -> list[dict]:
    import ctypes.wintypes

    left, top, right, bottom = region
    try:
        pattern = element.GetCurrentPattern(UIA.UIA_TextPatternId).QueryInterface(
            UIA.IUIAutomationTextPattern
        )
    except Exception:
        return []
    lines, seen = [], set()
    for fy in (0.1, 0.3, 0.5, 0.7, 0.9):
        for fx in (0.2, 0.5):
            point = ctypes.wintypes.POINT(
                int(left + (right - left) * fx), int(top + (bottom - top) * fy)
            )
            try:
                rng = pattern.RangeFromPoint(point)
                rng.ExpandToEnclosingUnit(UIA.TextUnit_Line)
                text = (rng.GetText(1500) or "").strip()
                rects = rng.GetBoundingRectangles() or ()
            except Exception:
                continue
            if not text or text in seen or len(rects) < 4:
                continue
            seen.add(text)
            lines.append(
                {
                    "type": "TextLine",
                    "text": text,
                    "bbox": {
                        "x": rects[0],
                        "y": rects[1],
                        "width": rects[2],
                        "height": rects[3],
                    },
                }
            )
    return lines


# --- API ----------------------------------------------------------------------------------------------------


def _data_url(image, quality: int = 80) -> str:
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _sweep() -> None:
    now = time.monotonic()
    for key in [k for k, v in _captures.items() if now - v["at"] > CAPTURE_TTL_SECONDS]:
        _captures.pop(key, None)


def _safe_windows() -> list[dict] | None:
    try:
        return _windows_topdown()
    except Exception as exc:  # a window closing mid-enumeration, etc.
        logger.warning("window enumeration failed: %s", type(exc).__name__)
        return None


def capture() -> dict:
    image, monitor = _grab_monitor()
    # z-order as it was when the frame froze (before the overlay shows): sensitivity is judged on what the user saw.
    windows = _safe_windows()
    capture_id = uuid.uuid4().hex
    with _lock:
        _sweep()
        _captures[capture_id] = {
            "image": image,
            "monitor": monitor,
            "windows": windows,
            "at": time.monotonic(),
        }
        while len(_captures) > MAX_CAPTURES:
            _captures.popitem(last=False)
    return {
        "capture_id": capture_id,
        "monitor": monitor,
        "image_data": _data_url(image),
    }


def get_capture(capture_id: str) -> dict:
    with _lock:
        _sweep()
        item = _captures.get(capture_id)
    if item is None:
        raise CaptureNotFound(capture_id)
    return item


def _intersects(rect: tuple, region: tuple) -> bool:
    return not (
        rect[2] <= region[0]
        or rect[0] >= region[2]
        or rect[3] <= region[1]
        or rect[1] >= region[3]
    )


def _contains(rect: tuple, region: tuple) -> bool:
    return rect[0] <= region[0] and rect[1] <= region[1] and rect[2] >= region[2] and rect[3] >= region[3]


def is_sensitive(window: dict) -> bool:
    """Fails closed: an unknown process (elevated/protected, name unreadable) counts as sensitive."""
    process = (window.get("process") or "").lower()
    title = (window.get("title") or "").lower()
    return not process or process in SENSITIVE_PROCESSES or any(w in title for w in SENSITIVE_TITLE_WORDS)


def _screen_rect(monitor: dict, region: dict) -> tuple:
    return (
        monitor["x"] + region["x"],
        monitor["y"] + region["y"],
        monitor["x"] + region["x"] + region["width"],
        monitor["y"] + region["y"] + region["height"],
    )


def visible_windows(item: dict, region: dict, exclude_pids=()) -> list[dict] | None:
    """Windows that may show pixels inside the region, topmost first: stop at the first one covering it entirely.
    None when the window list is unknown (enumeration failed)."""
    if item.get("windows") is None:
        return None
    screen = _screen_rect(item["monitor"], region)
    excluded = set(exclude_pids)
    out = []
    for window in item["windows"]:
        if window["pid"] in excluded or not _intersects(window["rect"], screen):
            continue
        out.append(window)
        if _contains(window["rect"], screen):
            break
    return out


def region_sensitive(item: dict, region: dict, exclude_pids=()) -> bool:
    windows = visible_windows(item, region, exclude_pids)
    return windows is None or any(is_sensitive(w) for w in windows)


def _app_name(window: dict) -> str:
    title = window.get("title") or ""
    if " - " in title:
        return title.rsplit(" - ", 1)[-1].strip()
    return (window.get("process") or "").removesuffix(".exe") or title


def crop_box(capture_id: str, bbox: dict) -> tuple[str, CropInfo] | None:
    """Crop of the frozen frame around a monitor-pixel bbox (+ padding) as (data URL, CropInfo)."""
    item = get_capture(capture_id)
    image = item["image"]
    try:
        left = max(0, int(bbox["x"]) - CROP_PADDING)
        top = max(0, int(bbox["y"]) - CROP_PADDING)
        right = min(image.width, int(bbox["x"] + bbox["width"]) + CROP_PADDING)
        bottom = min(image.height, int(bbox["y"] + bbox["height"]) + CROP_PADDING)
    except (ValueError, OverflowError):
        return None
    if right <= left or bottom <= top:
        return None
    crop = image.crop((left, top, right, bottom))
    return _data_url(crop, 86), CropInfo(
        bbox=BBox(x=left, y=top, width=right - left, height=bottom - top), scale=1.0
    )


def crop_for_ask(capture_id: str, bbox: dict) -> tuple[str, CropInfo] | None:
    """The ask-path crop: never from a region where a sensitive window is visible (pixels would reach the model,
    OCR text the prompt and history)."""
    item = get_capture(capture_id)
    padded = {"x": bbox["x"] - CROP_PADDING, "y": bbox["y"] - CROP_PADDING,
              "width": bbox["width"] + 2 * CROP_PADDING, "height": bbox["height"] + 2 * CROP_PADDING}
    if region_sensitive(item, padded, item.get("exclude_pids", ())):
        return None
    return crop_box(capture_id, bbox)


def candidates(capture_id: str, region: dict, exclude_pids: list[int]) -> dict:
    item = get_capture(capture_id)
    item["exclude_pids"] = tuple(exclude_pids)  # remembered for the ask-path crop check
    monitor = item["monitor"]
    screen = _screen_rect(monitor, region)
    windows = visible_windows(item, region, exclude_pids)
    window = windows[0] if windows else None
    if windows is None or any(is_sensitive(w) for w in windows):
        # Never read, never OCR, never fall through; a sensitive title can name the vault or entry.
        info = {"app": "", "process": (window or {}).get("process", ""), "title": "", "sensitive": True}
        return {"candidates": [], "window": info}
    found: list[CandidateObject] = []
    info: dict[str, Any] = {"app": "", "process": "", "title": ""}
    if window is not None:
        info = {
            "app": _app_name(window),
            "process": window.get("process", ""),
            "title": window.get("title", ""),
        }
        try:
            elements = _uia_read(window["hwnd"], screen, window.get("pid"))
        except Exception as exc:
            logger.warning("UIA read failed: %s", type(exc).__name__)
            elements = []
        for index, element in enumerate(elements):
            b = element["bbox"]
            rect = (b["x"], b["y"], b["x"] + b["width"], b["y"] + b["height"])
            if not _intersects(rect, screen):
                continue
            found.append(
                CandidateObject(
                    candidate_id=f"uia-{index}",
                    source="uia",
                    object_type=element["type"],
                    text=element["text"][:1500],
                    bbox=BBox(
                        x=b["x"] - monitor["x"],
                        y=b["y"] - monitor["y"],
                        width=b["width"],
                        height=b["height"],
                    ),
                    provenance=Provenance(extractor="uia", extractor_version="1"),
                )
            )
    # OCR only as a fallback (canvas apps, games, remote desktops): UIA text is exact and far cheaper.
    if not found and settings.ocr_enabled:
        cropped = crop_box(capture_id, region)
        if cropped:
            found.extend(ocr_candidates(ocr_blocks(cropped[0]), cropped[1]))
    return {"candidates": [c.model_dump() for c in merge(found)], "window": info}
