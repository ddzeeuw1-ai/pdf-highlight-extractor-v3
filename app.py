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


# ── Formatters ────────────────────────────────────────────────

def _entry_txt(i: int, h: Highlight, source: str = "") -> str:
    header_parts = [f"[{i}] Page {h.page}"]
    if source:
        header_parts.append(f"— {source}")
    if h.color:
        header_parts.append(f"[{h.color}]")
    if h.timestamp:
        header_parts.append(f"@ {h.timestamp}")
    lines = [" ".join(header_parts)]
    if h.kind == "note":
        lines.append(f"Note: {h.note}")
    else:
        lines.append(h.text)
        if h.note:
            lines.append(f"↳ Note: {h.note}")
    return "\n".join(lines)


def to_txt(entries: list[tuple[str, Highlight]]) -> str:
    lines = ["Highlights & Notes", "=" * 40, "",
             f"Total entries: {len(entries)}", "", "=" * 40, ""]
    for i, (source, h) in enumerate(entries, 1):
        lines.append(_entry_txt(i, h, source))
        lines.append("")
    return "\n".join(lines)


def to_markdown(entries: list[tuple[str, Highlight]]) -> str:
    lines = ["# Highlights & Notes", "",
             f"**Total entries:** {len(entries)}", "", "---", ""]
    for i, (source, h) in enumerate(entries, 1):
        label = _color_label(h)
        meta_parts = [f"Page {h.page}"]
        if source:
            meta_parts.append(source)
        if label:
            meta_parts.append(label)
        if h.timestamp:
            meta_parts.append(h.timestamp)
        lines.append(f"## [{i}] {' · '.join(meta_parts)}")
        lines.append("")
        if h.kind == "note":
            lines.append(f"*Note:* {h.note}")
        else:
            lines.append(h.text)
            if h.note:
                lines.append("")
                lines.append(f"> **Note:** {h.note}")
        lines.append("")
    return "\n".join(lines)


def to_json(entries: list[tuple[str, Highlight]]) -> str:
    data = []
    for source, h in entries:
        entry = {
            "page": h.page,
            "kind": h.kind,
            "text": h.text,
            "color": h.color,
            "timestamp": h.timestamp,
            "note": h.note,
        }
        if source:
            entry["source"] = source
        data.append(entry)
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
    page_range = None
    if start_page or end_page:
        s = int(start_page) if start_page else 1
        e = int(end_page) if end_page else 99999
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

    # Preview (first 5 entries)
    preview_lines = [
        f"Found {len(all_entries)} entry/entries across {len(pdf_files)} file(s).\n"
    ]
    if errors:
        preview_lines.append("⚠ Errors: " + "; ".join(errors) + "\n")

    for i, (source, h) in enumerate(all_entries[:5], 1):
        label = _color_label(h)
        header = f"[{i}] Page {h.page}"
        if source:
            header += f" — {source}"
        if label:
            header += f"  {label}"
        if h.timestamp:
            header += f"  {h.timestamp}"
        preview_lines.append(header)
        if h.kind == "note":
            preview_lines.append(f"  📝 {h.note}")
        else:
            preview_lines.append(f"  {h.text}")
            if h.note:
                preview_lines.append(f"  ↳ {h.note}")
        preview_lines.append("")

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
                    minimum=1,
                    value=None,
                )
                end_page = gr.Number(
                    label="End page (optional)",
                    precision=0,
                    minimum=1,
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
