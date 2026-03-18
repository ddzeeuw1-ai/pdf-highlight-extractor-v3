"""
PDF highlight and note extraction.
Extracts highlight annotations with their text, color, timestamp,
and any attached notes. Also captures standalone text notes.
"""

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
import pdfplumber

from text_cleaner import clean_text

warnings.filterwarnings("ignore")


@dataclass
class Highlight:
    page: int
    text: str
    color: str = ""        # e.g. "yellow", "green", "blue"
    timestamp: str = ""    # "YYYY-MM-DD HH:MM"
    note: str = ""         # attached or standalone text note
    kind: str = "highlight"  # "highlight" or "note"


# ── Color mapping ─────────────────────────────────────────────

# Named color centroids in RGB 0-1 space
_COLOR_CENTROIDS: dict[str, tuple[float, float, float]] = {
    "yellow":  (1.00, 0.95, 0.00),
    "green":   (0.00, 0.90, 0.00),
    "blue":    (0.00, 0.45, 1.00),
    "red":     (1.00, 0.10, 0.10),
    "pink":    (1.00, 0.50, 0.75),
    "orange":  (1.00, 0.60, 0.00),
    "purple":  (0.55, 0.00, 0.55),
    "cyan":    (0.00, 0.90, 0.90),
}


def _rgb_to_color_name(rgb) -> str:
    """Map an RGB triplet (floats 0-1) to the nearest named color."""
    if not rgb or len(rgb) < 3:
        return ""
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])

    def dist(centroid):
        return ((r - centroid[0]) ** 2 + (g - centroid[1]) ** 2 + (b - centroid[2]) ** 2) ** 0.5

    return min(_COLOR_CENTROIDS, key=lambda name: dist(_COLOR_CENTROIDS[name]))


# ── Timestamp parsing ─────────────────────────────────────────

def _parse_timestamp(raw) -> str:
    """Parse PDF date string (D:YYYYMMDDHHmmSS...) into YYYY-MM-DD HH:MM."""
    s = str(raw)
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)} {m.group(4)}:{m.group(5)}"
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


# ── Annotation helpers ────────────────────────────────────────

def _get_annotations(reader: PdfReader, page_range: tuple[int, int] | None) -> list[dict]:
    """
    Collect all highlight and standalone note annotations,
    optionally filtered to a 1-based page range (start, end) inclusive.
    """
    annotations = []
    for page_num, page in enumerate(reader.pages):
        # Apply page range filter (convert to 0-based)
        if page_range:
            start, end = page_range
            if not (start - 1 <= page_num <= end - 1):
                continue

        if "/Annots" not in page:
            continue

        for annot in page["/Annots"]:
            obj = annot.get_object()
            subtype = obj.get("/Subtype", "")
            color = _rgb_to_color_name(obj.get("/C", []))
            timestamp = _parse_timestamp(obj.get("/M", ""))
            contents = str(obj.get("/Contents", "") or "").strip()

            if subtype == "/Highlight":
                quads = obj.get("/QuadPoints")
                if quads:
                    annotations.append({
                        "kind": "highlight",
                        "page": page_num,
                        "quads": list(quads),
                        "color": color,
                        "timestamp": timestamp,
                        "note": contents,
                    })

            elif subtype == "/Text":
                # Standalone text note (not attached to a highlight)
                if contents:
                    annotations.append({
                        "kind": "note",
                        "page": page_num,
                        "quads": None,
                        "color": color,
                        "timestamp": timestamp,
                        "note": contents,
                    })

    # Sort by page then by vertical position on page (top-to-bottom)
    annotations.sort(key=lambda a: (
        a["page"],
        -a["quads"][1] if a["quads"] else 0
    ))
    return annotations


def _quads_to_bboxes(quads: list[float]) -> list[tuple]:
    bboxes = []
    for i in range(0, len(quads), 8):
        q = quads[i : i + 8]
        xs = [q[j] for j in range(0, 8, 2)]
        ys = [q[j] for j in range(1, 8, 2)]
        bboxes.append((min(xs), min(ys), max(xs), max(ys)))
    return bboxes


# ── Public API ────────────────────────────────────────────────

def extract_highlights(
    pdf_path: Path,
    page_range: tuple[int, int] | None = None,
) -> list[Highlight]:
    """
    Extract all highlighted text and standalone notes from a PDF.

    Args:
        pdf_path:   Path to the PDF file.
        page_range: Optional (start, end) tuple with 1-based page numbers (inclusive).

    Returns:
        List of Highlight objects sorted by page and position.
    """
    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc

    total_pages = len(reader.pages)

    # Validate and clamp page range
    if page_range:
        start = max(1, page_range[0])
        end = min(total_pages, page_range[1])
        if start > end:
            raise ValueError(
                f"Invalid page range {page_range[0]}–{page_range[1]} "
                f"(PDF has {total_pages} pages)."
            )
        page_range = (start, end)

    annotation_data = _get_annotations(reader, page_range)
    if not annotation_data:
        return []

    results: list[Highlight] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for ann in annotation_data:
            page_index = ann["page"]

            if ann["kind"] == "note":
                # Standalone note — no text extraction needed
                results.append(Highlight(
                    page=page_index + 1,
                    text="",
                    color=ann["color"],
                    timestamp=ann["timestamp"],
                    note=ann["note"],
                    kind="note",
                ))
                continue

            # Highlight — extract text from page coordinates
            page = pdf.pages[page_index]
            ph = page.height
            word_parts: list[str] = []

            for x0, y0p, x1, y1p in _quads_to_bboxes(ann["quads"]):
                top = ph - y1p
                bottom = ph - y0p
                crop = page.within_bbox(
                    (x0 - 2, top - 2, x1 + 2, bottom + 2),
                    strict=False,
                )
                word_parts.extend(w["text"] for w in crop.extract_words())

            text = clean_text(" ".join(word_parts))
            if text:
                results.append(Highlight(
                    page=page_index + 1,
                    text=text,
                    color=ann["color"],
                    timestamp=ann["timestamp"],
                    note=ann["note"],
                    kind="highlight",
                ))

    return results
