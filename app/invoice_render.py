"""Fill the editable HTML invoice template with one invoice's data (brief 8).

The template lives at <root>\\templates\\invoice_template.html and is owned by the
user; we only substitute markers. The logo is inlined as a data URI so the PDF
renderer needs no file access or network.
"""
from __future__ import annotations

import base64
import html
import mimetypes
import re

from . import config, db, money, palette
from .utils import nz_date

# The repeating row lives between these comment markers in the template.
_ROW_BLOCK = re.compile(r"<!-- LINE_ITEM_ROW -->(.*?)<!-- /LINE_ITEM_ROW -->", re.DOTALL)


def _block(template: str, name: str, keep: bool) -> str:
    """Keep or strip a <!-- NAME --> ... <!-- END_NAME --> conditional block."""
    pattern = re.compile(rf"<!-- {name} -->(.*?)<!-- END_{name} -->", re.DOTALL)
    return pattern.sub((lambda m: m.group(1)) if keep else "", template)


def _logo_data_uri() -> str:
    name = db.get_setting("logo_filename", "logo.jpg")
    path = config.templates_dir() / name
    if not path.exists():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _esc(value) -> str:
    """HTML-escape a value for safe substitution (None -> empty)."""
    return html.escape("" if value is None else str(value))


def render(invoice: dict, lines: list[dict], settings: dict) -> str:
    """Return the template HTML with all markers filled for this invoice."""
    template = config.invoice_template().read_text(encoding="utf-8")

    # GST registration drives the document layout (req 11).
    try:
        gst_rate = float(settings.get("gst_rate") or 0)
    except ValueError:
        gst_rate = 0.0
    registered = gst_rate > 0
    tax_no = (settings.get("gst_number") or "").strip()
    tax_label = "GST No" if registered else "IRD No"

    # Keep/strip the conditional blocks in the template.
    template = _block(template, "IF_GST", registered)
    template = _block(template, "IF_NOT_GST", not registered)
    template = _block(template, "IF_TAXNO", bool(tax_no))

    doc_type = "TAX INVOICE" if registered else "INVOICE"
    gst_line = "GST Content ({:g}%)".format(gst_rate)
    footer_tax = f" &middot; {tax_label} {tax_no}" if tax_no else ""

    # Build the line-item rows from the template's repeatable block.
    match = _ROW_BLOCK.search(template)
    row_tpl = match.group(1) if match else ""
    rows_html = []
    for ln in lines:
        row = row_tpl
        row = row.replace("{{LineDescription}}", _esc(ln.get("description")))
        row = row.replace("{{LineQuantity}}", _esc(_qty(ln.get("quantity"))))
        row = row.replace("{{LineUnitPrice}}", _esc(money.money(ln.get("unit_price"))))
        row = row.replace("{{LineTotal}}", _esc(money.money(ln.get("line_total"))))
        rows_html.append(row)
    template = _ROW_BLOCK.sub(lambda _m: "".join(rows_html), template)

    values = {
        "BusinessName": settings.get("business_name"),
        "OwnerName": settings.get("owner_name"),
        "BusinessAddress": settings.get("business_address"),
        "BusinessPhone": settings.get("business_phone"),
        "BusinessEmail": settings.get("business_email"),
        "GSTNumber": settings.get("gst_number"),
        "BankName": settings.get("bank_name"),
        "BankAccountName": settings.get("bank_account_name"),
        "BankAccountNumber": settings.get("bank_account_number"),
        "InvoiceNumber": invoice.get("invoice_number"),
        "InvoiceDate": nz_date(invoice.get("invoice_date")),
        "Reference": invoice.get("reference"),
        "DocumentType": doc_type,
        "TaxNumberLabel": tax_label,
        "GSTLine": gst_line,
        "ClientName": invoice.get("client_name_snapshot"),
        "ClientAddress": invoice.get("client_address"),
        "ClientPhone": invoice.get("client_phone"),
        "ClientEmail": invoice.get("client_email"),
        "Details": invoice.get("details"),
        "Subtotal": money.money(invoice.get("subtotal")),
        "GST": money.money(invoice.get("gst")),
        "AmountPayable": money.money(invoice.get("amount_payable")),
    }
    for key, val in values.items():
        template = template.replace("{{" + key + "}}", _esc(val))

    # Raw (already-safe) values that must not be HTML-escaped.
    raw = {
        "FooterTax": footer_tax,
        "BrandColor": palette.get(settings, "color_brand"),
        "BrandDarkColor": palette.get(settings, "color_brand_dark"),
    }
    for key, val in raw.items():
        template = template.replace("{{" + key + "}}", val)

    # Logo is replaced last (its value is a long data URI, not user text).
    template = template.replace("{{Logo}}", _logo_data_uri())
    return template


def _qty(value) -> str:
    """Show 1 not 1.0, but keep 3.5 as 3.5."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    return str(int(f)) if f == int(f) else str(f)
