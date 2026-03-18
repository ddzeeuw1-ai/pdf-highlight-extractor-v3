"""
Text cleaning utilities for PDF highlight extraction.
Fixes common issues introduced by PDF encoding: ligatures, merged words,
missing spaces after punctuation.
"""

import re
import unicodedata

LIGATURES: dict[str, str] = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
    "\u0192": "f",
}


def clean_text(text: str) -> str:
    for char, replacement in LIGATURES.items():
        text = text.replace(char, replacement)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"([.!?])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"([,;:])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()
