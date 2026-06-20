"""Silent HTML -> PDF using a headless Chromium (Playwright).

Plain "Save" must drop a finished PDF into \\Invoices with no dialog, so we
render the filled invoice template through Chromium's own print engine. The
visible browser print dialog is reserved for "Save & Print" / Ctrl+P.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def html_to_pdf(html: str, out_path: Path) -> Path:
    """Render an HTML string to a PDF file at out_path."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            # The template embeds the logo as a data URI, so there is nothing to
            # fetch over the network; "load" is enough to wait for.
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(out_path),
                print_background=True,
                prefer_css_page_size=True,  # honour the template's @page A4 + margins
            )
        finally:
            browser.close()
    return out_path
