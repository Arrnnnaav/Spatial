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


def ocr_image(image_data: str | None) -> str:
    if not image_data:
        return ""
    engine = _engine()
    if engine is None:
        return ""
    try:
        from PIL import Image
        raw = base64.b64decode(image_data.split(",", 1)[-1])
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        import numpy as np
        result, _ = engine(np.array(image))
        if not result:
            return ""
        # RapidOCR returns [box, text, score]; keep reading order as given and join lines.
        return "\n".join(str(item[1]).strip() for item in result if len(item) > 1 and float(item[2]) >= 0.4).strip()
    except Exception:
        return ""
