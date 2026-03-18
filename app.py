"""
PDF Highlight Extractor — Gradio app (Phase 1).

Features:
- Batch upload: process multiple PDFs at once
- Page range: optionally restrict extraction to a page range
- Color labels: highlight colors shown in output
- Timestamps: sort by page order or annotation timestamp
- Notes: attached and standalone notes included in output
"""

import json
import tempfile
from pathlib import Path

import gradio as gr

from pdf_extractor import extract_highlights, Highlight

# Color emoji for visual labels in the preview
COLOR_EMOJI: dict[str, str] = {
    "yellow": "🟡",
    "green":  "🟢",
    "blue":   "🔵",
    "red":    "🔴",
    "pink":   "🩷",
    "orange": "🟠",
    "purple": "🟣",
    "cyan":   "🩵",
    "":       "⬜",
}


def _color_label(h: Highlight) -> str:
    emoji = COLOR_EMOJI.get(h.color, "⬜")
    return f"{emoji} {h.color.capitalize()}" if h.color else ""


# ── Helpers ───────────────────────────────────────────────────

def _group_by_source(
    entries: list[tuple[str, Highlight]]
) -> tuple[list[str], dict[str, list[Highlight]]]:
    """Return (ordered source list, source→highlights dict)."""
    from collections import defaultdict
    grouped: dict[str, list[Highlight]] = defaultdict(list)
    order: list[str] = []
    for source, h in entries:
        if source not in grouped:
            order.append(source)
        grouped[source].append(h)
    return order, grouped


def _color_meta_txt(h: Highlight) -> str:
    """Left-margin marker line: '▍ yellow · 2024-01-15'"""
    parts = []
    if h.color:
        parts.append(h.color)
    if h.timestamp:
        parts.append(h.timestamp)
    if parts:
        return "▍ " + " · ".join(parts)
    return ""


# ── Formatters ────────────────────────────────────────────────

def to_txt(entries: list[tuple[str, Highlight]]) -> str:
    order, grouped = _group_by_source(entries)
    lines = [
        "Highlights & Notes",
        "=" * 40,
        "",
        f"Total entries: {len(entries)}",
        "",
        "=" * 40,
        "",
    ]
    for source in order:
        doc_highlights = grouped[source]
        title = source if source else "Document"
        lines.append(f"[ {title} ]")
        lines.append("─" * (len(title) + 4))
        lines.append("")
        for h in doc_highlights:
            if h.kind == "note":
                lines.append(f"📝 {h.note} (p. {h.page})")
            else:
                lines.append(f"{h.text} (p. {h.page})")
                if h.note:
                    lines.append(f"  ↳ {h.note}")
            meta = _color_meta_txt(h)
            if meta:
                lines.append(meta)
            lines.append("")
        lines.append("")
    return "\n".join(lines)


def to_markdown(entries: list[tuple[str, Highlight]]) -> str:
    order, grouped = _group_by_source(entries)
    lines = [
        "# Highlights & Notes",
        "",
        f"**Total entries:** {len(entries)}",
        "",
    ]
    for source in order:
        doc_highlights = grouped[source]
        title = source if source else "Document"
        lines.append(f"## {title}")
        lines.append("")
        for h in doc_highlights:
            emoji = COLOR_EMOJI.get(h.color, "")
            if h.kind == "note":
                lines.append(f"> 📝 **Note:** {h.note} *(p. {h.page})*")
            else:
                lines.append(f"> {h.text} *(p. {h.page})*")
                if h.note:
                    lines.append(f">")
                    lines.append(f"> *↳ {h.note}*")
            # Colour + timestamp as a subtle meta line
            meta_parts = []
            if h.color:
                meta_parts.append(f"{emoji} {h.color}")
            if h.timestamp:
                meta_parts.append(h.timestamp)
            if meta_parts:
                lines.append(f"*{' · '.join(meta_parts)}*")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def to_json(entries: list[tuple[str, Highlight]]) -> str:
    order, grouped = _group_by_source(entries)
    data = []
    for source in order:
        doc_entry: dict = {}
        if source:
            doc_entry["document"] = source
        doc_entry["highlights"] = [
            {
                "page": h.page,
                "kind": h.kind,
                "text": h.text,
                "color": h.color,
                "timestamp": h.timestamp,
                "note": h.note,
            }
            for h in grouped[source]
        ]
        data.append(doc_entry)
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Core processing ───────────────────────────────────────────

def process_pdfs(
    pdf_files,
    start_page,
    end_page,
    sort_by: str,
    export_format: str,
) -> tuple[str, str | None]:
    if not pdf_files:
        return "Please upload at least one PDF file.", None

    # Normalise: Gradio 5 may pass a single item for single uploads
    if not isinstance(pdf_files, list):
        pdf_files = [pdf_files]

    # Validate page range
    # Gradio 5 sends 0 for empty number fields, treat 0/None as "no filter"
    start_page = int(start_page) if start_page and int(start_page) > 0 else None
    end_page = int(end_page) if end_page and int(end_page) > 0 else None
    page_range = None
    if start_page or end_page:
        s = start_page if start_page else 1
        e = end_page if end_page else 99999
        if s > e:
            return f"Start page ({s}) cannot be greater than end page ({e}).", None
        page_range = (s, e)

    # Extract from each PDF
    all_entries: list[tuple[str, Highlight]] = []
    errors: list[str] = []

    for f in pdf_files:
        path = Path(f if isinstance(f, str) else f.name)
        source = path.stem if len(pdf_files) > 1 else ""
        try:
            highlights = extract_highlights(path, page_range=page_range)
            for h in highlights:
                all_entries.append((source, h))
        except ValueError as e:
            errors.append(f"{path.name}: {e}")

    if not all_entries and errors:
        return "Errors:\n" + "\n".join(errors), None

    if not all_entries:
        msg = "No highlights or notes found in the uploaded PDF(s)."
        if page_range:
            msg += f" (searched pages {page_range[0]}–{page_range[1]})"
        return msg, None

    # Sort
    if sort_by == "Timestamp":
        all_entries.sort(key=lambda x: (x[1].timestamp or "0000", x[1].page))
    else:
        all_entries.sort(key=lambda x: (x[0], x[1].page))

    # Preview (first 5 entries, grouped by source)
    preview_lines = [
        f"Found {len(all_entries)} entry/entries across {len(pdf_files)} file(s).\n"
    ]
    if errors:
        preview_lines.append("⚠ Errors: " + "; ".join(errors) + "\n")

    prev_source = object()  # sentinel
    shown = 0
    for source, h in all_entries:
        if shown >= 5:
            break
        # Print document header once per source
        if source != prev_source:
            title = source if source else "Document"
            preview_lines.append(f"[ {title} ]")
            preview_lines.append("─" * (len(title) + 4))
            prev_source = source
        if h.kind == "note":
            preview_lines.append(f"📝 {h.note} (p. {h.page})")
        else:
            preview_lines.append(f"{h.text} (p. {h.page})")
            if h.note:
                preview_lines.append(f"  ↳ {h.note}")
        meta = _color_meta_txt(h)
        if meta:
            preview_lines.append(meta)
        preview_lines.append("")
        shown += 1

    if len(all_entries) > 5:
        preview_lines.append(
            f"… and {len(all_entries) - 5} more. Download the file to see all."
        )

    # Build export file
    if export_format == "Plain Text":
        content = to_txt(all_entries)
        ext = "txt"
    elif export_format == "Markdown":
        content = to_markdown(all_entries)
        ext = "md"
    else:
        content = to_json(all_entries)
        ext = "json"

    first_stem = Path(
        pdf_files[0] if isinstance(pdf_files[0], str) else pdf_files[0].name
    ).stem

    tmp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=f".{ext}",
        mode="w",
        encoding="utf-8",
        prefix=f"{first_stem}_highlights_",
    )
    tmp.write(content)
    tmp.close()

    return "\n".join(preview_lines), tmp.name


# ── Gradio UI ─────────────────────────────────────────────────

with gr.Blocks(title="PDF Highlight Extractor") as demo:
    gr.Markdown("# PDF Highlight Extractor")
    gr.Markdown(
        "Extract highlighted text, colors, timestamps, and notes from PDF files. "
        "Supports batch processing of multiple PDFs at once."
    )

    with gr.Row():
        with gr.Column(scale=2):
            pdf_input = gr.File(
                label="Upload PDF(s)",
                file_types=[".pdf"],
                file_count="multiple",
            )
            with gr.Row():
                start_page = gr.Number(
                    label="Start page (optional)",
                    precision=0,
                    value=None,
                )
                end_page = gr.Number(
                    label="End page (optional)",
                    precision=0,
                    value=None,
                )
            sort_by = gr.Radio(
                choices=["Page number", "Timestamp"],
                value="Page number",
                label="Sort by",
            )
            export_format = gr.Radio(
                choices=["Plain Text", "Markdown", "JSON"],
                value="Plain Text",
                label="Export format",
            )
            run_btn = gr.Button("Extract highlights", variant="primary")

        with gr.Column(scale=3):
            preview_out = gr.Textbox(
                label="Preview",
                lines=24,
                interactive=False,
            )
            file_out = gr.File(label="Download")

    run_btn.click(
        fn=process_pdfs,
        inputs=[pdf_input, start_page, end_page, sort_by, export_format],
        outputs=[preview_out, file_out],
    )

    gr.Markdown(
        "_PDFs are processed in memory and not stored. "
        "Highlights must be annotation-based (created in Preview, Adobe, Zotero, etc.)._"
    )

if __name__ == "__main__":
    demo.launch()
