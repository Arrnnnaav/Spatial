"""Deterministic generator for labelled resolver eval cases. `intended` is set by construction (the element
the mark was drawn for), never by running the resolver. Re-run to regenerate:  python tests/eval_cases/generate.py"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

OUT = Path(__file__).parent
W, H = 1280, 720
rng = random.Random(20260923)
LOREM = [
    "Gradient descent updates each weight in the direction that lowers the loss.",
    "The learning rate controls how far each update moves the parameters.",
    "Momentum keeps a running average of past gradients to smooth the path.",
    "Batch normalization rescales activations so training stays stable.",
    "Dropout randomly disables units so the network cannot co-adapt.",
    "The validation loss rises when the model starts to overfit.",
]
EQUATIONS = [
    "dy/dx = (2x)/2 = x",
    "L = -Σ y log ŷ",
    "θ ← θ − η ∇L(θ)",
    "σ(z) = 1 / (1 + e^{-z})",
]
CELLS = [
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "$1.2M",
    "$1.5M",
    "$0.9M",
    "$2.1M",
    "+12%",
    "+25%",
    "-40%",
    "+133%",
]


def box(x, y, w, h):
    return {
        "x": round(x, 1),
        "y": round(y, 1),
        "width": round(w, 1),
        "height": round(h, 1),
    }


def anchor(id_, type_, text, b, page=None):
    a = {"id": id_, "type": type_, "text": text, "bbox": b}
    if page is not None:
        a["page"] = page
    return a


def rect_around(b, pad, kind="rectangle", role="reference"):
    return {
        "type": kind,
        "role": role,
        **box(b["x"] - pad, b["y"] - pad, b["width"] + 2 * pad, b["height"] + 2 * pad),
    }


def circle_stroke(b, slack):
    """Closed freehand circle around b; carries the client's bbox (no padding for closed strokes)."""
    cx, cy = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
    rx, ry = b["width"] / 2 + slack, b["height"] / 2 + slack
    pts = [
        [round(cx + rx * math.cos(t)), round(cy + ry * math.sin(t))]
        for t in (i * 2 * math.pi / 40 for i in range(41))
    ]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return {
        "type": "polygon",
        "role": "reference",
        "closed": True,
        "points": pts,
        **box(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)),
    }


def underline_stroke(b):
    """Open stroke under a line of text, padded like geometry.js::strokeToMark (8..40 px, 15% of diagonal)."""
    y = b["y"] + b["height"] + 4
    pts = [[round(b["x"] + i * b["width"] / 10), round(y + (i % 2))] for i in range(11)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    pad = max(8, min(40, math.hypot(w, h) * 0.15))
    return {
        "type": "polygon",
        "role": "reference",
        "closed": False,
        "points": pts,
        **box(max(0, min(xs) - pad), max(0, min(ys) - pad), w + 2 * pad, h + 2 * pad),
    }


def case(
    name,
    category,
    description,
    question,
    marks,
    anchors,
    intended,
    surface="web",
    ambiguous=False,
):
    (OUT / f"{name}.json").write_text(
        json.dumps(
            {
                "description": description,
                "category": category,
                "question": question,
                "surface": surface,
                "canvas": {"width": W, "height": H},
                "marks": marks,
                "anchors": anchors,
                "intended": intended,
                "ambiguous": ambiguous,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def paragraphs(n, top=80, x=120, w=640, h=52, gap=14):
    return [
        anchor(f"p{i}", "p", LOREM[i % len(LOREM)], box(x, top + i * (h + gap), w, h))
        for i in range(n)
    ]


def web_cases():
    for i in range(5):  # sloppy rectangle around one paragraph in a column
        ps = paragraphs(rng.randint(4, 6))
        k = rng.randrange(len(ps))
        case(
            f"web_paragraph_{i}",
            "web",
            "rectangle around one paragraph, padding 2-14 px, may touch neighbours",
            "explain this",
            [rect_around(ps[k]["bbox"], rng.randint(2, 14))],
            ps,
            [ps[k]["id"]],
        )
    for i in range(4):  # nested: section container + heading + paragraphs + inline link
        sec = box(100, 100, 700, 320)
        head = anchor("h", "h2", "Optimisers", box(120, 115, 300, 36))
        p1 = anchor(
            "p1", "p", LOREM[0] + " See Adam for details.", box(120, 165, 660, 70)
        )
        link = anchor("link", "a", "Adam", box(560, 190, 52, 20))
        p2 = anchor("p2", "p", LOREM[2], box(120, 250, 660, 70))
        section = anchor(
            "section", "section", " ".join(a["text"] for a in (head, p1, p2)), sec
        )
        items = [section, head, p1, link, p2]
        if i < 2:
            case(
                f"web_nested_link_{i}",
                "web",
                "tight box around an inline link inside a paragraph inside a section",
                "what is this?",
                [rect_around(link["bbox"], rng.randint(2, 5))],
                items,
                ["link"],
            )
        else:
            case(
                f"web_nested_section_{i}",
                "web",
                "loose circle around a whole section",
                "summarize this",
                [circle_stroke(sec, rng.randint(10, 25))],
                items,
                ["section"],
            )
    for i in range(3):  # table cell
        cells = [
            anchor(
                f"c{r}{c}",
                "td",
                CELLS[r * 4 + c],
                box(150 + c * 140, 200 + r * 44, 140, 44),
            )
            for r in range(3)
            for c in range(4)
        ]
        k = rng.randrange(len(cells))
        case(
            f"web_table_cell_{i}",
            "web",
            "box around one table cell",
            "why is this negative?",
            [rect_around(cells[k]["bbox"], rng.randint(1, 6))],
            cells,
            [cells[k]["id"]],
        )
    for i in range(3):  # point on a button that sits inside a toolbar container
        bar = anchor("toolbar", "div", "File Edit View Run Help", box(0, 0, W, 48))
        buttons = [
            anchor(f"b{j}", "button", name, box(20 + j * 90, 8, 80, 32))
            for j, name in enumerate(["File", "Edit", "View", "Run", "Help"])
        ]
        k = rng.randrange(len(buttons))
        b = buttons[k]["bbox"]
        point = {
            "type": "point",
            "role": "reference",
            "x": b["x"] + b["width"] / 2,
            "y": b["y"] + b["height"] / 2,
        }
        case(
            f"web_point_button_{i}",
            "web",
            "point mark on a toolbar button (container also contains the point)",
            "what does this do?",
            [point],
            [bar, *buttons],
            [buttons[k]["id"]],
        )


def pdf_cases():
    for i in range(6):  # merged block + glyph fragments
        blocks = [
            anchor(
                f"pdf-{i}-{j}",
                "pdf-text",
                LOREM[(i + j) % len(LOREM)],
                box(140, 120 + j * 110, 620, 90),
                page=i + 1,
            )
            for j in range(4)
        ]
        k = rng.randrange(len(blocks))
        tb = blocks[k]["bbox"]
        frags = [
            anchor(
                f"frag-{j}",
                "span",
                LOREM[(i + k) % len(LOREM)].split()[j],
                box(tb["x"] + 10 + j * 70, tb["y"] + 8, 60, 18),
                page=i + 1,
            )
            for j in range(3)
        ]
        case(
            f"pdf_block_{i}",
            "pdf",
            "sloppy circle around one merged PDF block; glyph spans inside it",
            "explain this paragraph",
            [circle_stroke(tb, rng.randint(4, 30))],
            blocks + frags,
            [blocks[k]["id"]],
            surface="pdf",
        )
    for i in range(3):  # equation line among text lines
        lines = [
            anchor(
                f"l{j}", "pdf-text", LOREM[j], box(140, 150 + j * 40, 620, 28), page=3
            )
            for j in range(5)
        ]
        eq = anchor(
            "eq", "pdf-text", EQUATIONS[i], box(300, 150 + 5 * 40, 260, 30), page=3
        )
        case(
            f"pdf_equation_{i}",
            "pdf",
            "tight circle around an equation line",
            "why this step?",
            [circle_stroke(eq["bbox"], rng.randint(3, 10))],
            [*lines, eq],
            ["eq"],
            surface="pdf",
        )
    for i in range(3):  # underline
        lines = [
            anchor(
                f"l{j}",
                "pdf-text",
                LOREM[(i + j) % len(LOREM)],
                box(140, 150 + j * 34, 620, 24),
                page=2,
            )
            for j in range(6)
        ]
        k = rng.randrange(1, 5)
        case(
            f"pdf_underline_{i}",
            "pdf",
            "open stroke drawn under one line of text",
            "what does this mean?",
            [underline_stroke(lines[k]["bbox"])],
            lines,
            [lines[k]["id"]],
            surface="pdf",
        )


def ambiguous_cases():
    for i in range(4):  # straddle two paragraphs equally
        ps = paragraphs(4)
        k = rng.randrange(3)
        a = ps[k]["bbox"]
        mid = a["y"] + a["height"] + 7
        mark = {
            "type": "rectangle",
            "role": "reference",
            **box(a["x"] + 40, mid - 40, 400, 80),
        }
        case(
            f"ambiguous_between_{i}",
            "ambiguous",
            "box straddling two paragraphs equally",
            "explain this",
            [mark],
            ps,
            [ps[k]["id"], ps[k + 1]["id"]],
            ambiguous=True,
        )
    for i in range(2):  # two table cells
        cells = [
            anchor(f"c{c}", "td", CELLS[c + 4], box(150 + c * 140, 240, 140, 44))
            for c in range(4)
        ]
        k = rng.randrange(3)
        mark = {
            "type": "rectangle",
            "role": "reference",
            **box(150 + k * 140 + 70, 244, 140, 36),
        }
        case(
            f"ambiguous_cells_{i}",
            "ambiguous",
            "box half over two adjacent cells",
            "why is this higher?",
            [mark],
            cells,
            [cells[k]["id"], cells[k + 1]["id"]],
            ambiguous=True,
        )
    for i in range(2):  # image + caption
        img = anchor("img", "img", "Loss curve", box(200, 120, 480, 280))
        cap = anchor(
            "caption",
            "figcaption",
            "Figure 2: training and validation loss per epoch",
            box(200, 410, 480, 30),
        )
        case(
            f"ambiguous_figure_{i}",
            "ambiguous",
            "circle around a figure and its caption",
            "what does this show?",
            [circle_stroke(box(200, 120, 480, 320), rng.randint(5, 15))],
            [img, cap],
            ["img", "caption"],
            ambiguous=True,
        )


def ocr_cases():
    labels = [
        ("title", "Revenue by quarter", box(420, 110, 300, 30)),
        ("legend0", "2025", box(900, 160, 60, 20)),
        ("legend1", "2026", box(900, 190, 60, 20)),
        ("xlabel", "Quarter", box(560, 640, 100, 22)),
        ("ylabel", "USD (millions)", box(150, 360, 130, 22)),
        ("peak", "2.1", box(760, 230, 40, 20)),
        ("note", "Source: internal finance report", box(400, 675, 320, 18)),
        ("q3", "Q3", box(640, 610, 30, 20)),
    ]
    for i, (key, text, b) in enumerate(labels):
        chart = anchor("chart", "canvas", "", box(140, 100, 900, 580))
        ocr = [anchor(f"ocr-{j}", "ocr", t, bb) for j, (_, t, bb) in enumerate(labels)]
        case(
            f"ocr_chart_{key}",
            "ocr",
            "canvas chart: only OCR blocks carry text; box around one label",
            "what does this mean?",
            [rect_around(b, rng.randint(3, 10))],
            [chart, *ocr],
            [f"ocr-{i}"],
        )


if __name__ == "__main__":
    for old in OUT.glob("*.json"):
        old.unlink()
    web_cases()
    pdf_cases()
    ambiguous_cases()
    ocr_cases()
    print(len(list(OUT.glob("*.json"))), "cases")
