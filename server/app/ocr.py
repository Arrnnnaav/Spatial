"""CPU OCR for the marked crop (RapidOCR / ONNX). Lets text-only models answer about images,
and gives the deterministic fallback something to quote. Optional: missing package = empty string."""
from __future__ import annotations

import base64
import io
from functools import lru_cache


@lru_cache(maxsize=1)
def _engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except Exception:  # pragma: no cover - optional dependency
        return None


def warm() -> None:
    """Load the model off the request path (first load ~4 s)."""
    _engine()


def ocr_blocks(image_data: str | None) -> list[dict]:
    """Text blocks with boxes in crop px: [{text, bbox: {x, y, width, height}, confidence}], reading order as given."""
    if not image_data:
        return []
    engine = _engine()
    if engine is None:
        return []
    try:
        from PIL import Image
        import numpy as np
        raw = base64.b64decode(image_data.split(",", 1)[-1])
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        result, _ = engine(np.array(image))
        blocks = []
        # RapidOCR returns [box (4 corner points), text, score].
        for item in result or []:
            if len(item) < 3:
                continue
            text, score = str(item[1]).strip(), float(item[2])
            if not text or score < 0.4:
                continue
            xs, ys = [float(p[0]) for p in item[0]], [float(p[1]) for p in item[0]]
            blocks.append({"text": text, "confidence": round(score, 3),
                           "bbox": {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}})
        return blocks
    except Exception:
        return []


def ocr_image(image_data: str | None) -> str:
    return "\n".join(block["text"] for block in ocr_blocks(image_data)).strip()
