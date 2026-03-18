---
title: PDF Highlight Extractor
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "5.0.0"
app_file: app.py
pinned: false
license: mit
---

# PDF Highlight Extractor

Extract highlighted text, colors, timestamps, and notes from PDF files.
Built for academics and researchers.

## Features

- **Batch upload** — process multiple PDFs at once
- **Page range** — optionally restrict extraction to specific pages
- **Color labels** — shows the highlight color (yellow, green, blue, etc.)
- **Timestamps** — sort highlights by page order or annotation timestamp
- **Notes** — extracts text notes attached to highlights, and standalone notes

## How to use

1. Upload one or more PDF files
2. Optionally set a start and end page to restrict extraction
3. Choose sort order (page number or timestamp)
4. Choose export format (Plain Text, Markdown, or JSON)
5. Click **Extract highlights**
6. Preview results and download the file

Highlights must be annotation-based — created with a PDF reader such as
Preview, Adobe Acrobat, Zotero, or similar. Visually coloured text without
annotations will not be detected.

## Deploy yourself

### Hugging Face Spaces (recommended, free)

1. Create a new Space at huggingface.co → choose **Gradio** as the SDK
2. Clone the Space and copy in the four files:
   `app.py`, `pdf_extractor.py`, `text_cleaner.py`, `requirements.txt`
3. Push — it builds and deploys automatically

### Render

1. New Web Service → connect GitHub repo
2. Build command: `pip install -r requirements.txt`
3. Start command: `python app.py`
4. Add env variable: `PORT=7860`

Update `demo.launch()` in `app.py` to:
```python
import os
demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get("PORT", 7860)))
```

### Run locally

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:7860
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio UI, formatters, and processing logic |
| `pdf_extractor.py` | PDF annotation extraction (highlights, colors, timestamps, notes) |
| `text_cleaner.py` | Fixes ligatures and missing spaces from PDF encoding |
| `requirements.txt` | Python dependencies |

## License

MIT
