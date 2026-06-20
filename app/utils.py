"""Small shared helpers: NZ date handling and safe filenames."""
from __future__ import annotations

import re
from datetime import date, datetime

# Characters Windows forbids in filenames (brief 5).
_FORBIDDEN = r'[\\/:*?"<>|]'


def nz_date(iso: str | None) -> str:
    """ISO yyyy-mm-dd -> DD/MM/YYYY for display. Pass other text through."""
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def parse_nz_date(text: str | None) -> str:
    """DD/MM/YYYY (or yyyy-mm-dd) -> ISO yyyy-mm-dd. Empty -> today."""
    if not text or not text.strip():
        return date.today().isoformat()
    text = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text  # leave as-is rather than lose what was typed


def safe_filename_part(text: str | None) -> str:
    """Strip Windows-forbidden characters for use in a PDF filename."""
    if not text:
        return ""
    cleaned = re.sub(_FORBIDDEN, "", text).strip()
    return re.sub(r"\s+", " ", cleaned)
