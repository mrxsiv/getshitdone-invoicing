"""Saving invoices: the number rule, line handling, and PDF generation.

This is the heart of the app, so the data-safety rules from the brief live here:
- the next number is the larger of the configured start and (highest + 1),
  issued inside one transaction so it can never duplicate (brief 6.5);
- a backup is taken before the write (via db.writing);
- the PDF on disk always reflects the current invoice, renamed if the
  Reference changed (brief 7.3).
"""
from __future__ import annotations

from pathlib import Path

from . import config, db, invoice_render, money, pdf
from .utils import parse_nz_date, safe_filename_part


def next_invoice_number(conn) -> int:
    start = int(db.get_setting("starting_invoice_number", "1") or "1")
    highest = conn.execute("SELECT MAX(invoice_number) AS m FROM invoices").fetchone()["m"] or 0
    return max(start, highest + 1)


def build_filename(number: int, reference: str | None) -> str:
    ref = safe_filename_part(reference)
    return f"Inv {number} - {ref}.pdf" if ref else f"Inv {number}.pdf"


def _clean_lines(raw_lines) -> list[dict]:
    """Drop blank rows; compute each line total at 2dp."""
    cleaned = []
    for ln in raw_lines or []:
        desc = (ln.get("description") or "").strip()
        qty = ln.get("quantity")
        price = ln.get("unit_price")
        if not desc and not qty and not price:
            continue
        q = money.to_float(qty or 0)
        p = money.to_float(price or 0)
        cleaned.append({
            "type": (ln.get("type") or "Labour").strip() or "Labour",
            "description": desc,
            "quantity": q,
            "unit_price": p,
            "line_total": money.to_float(money.line_total(q, p)),
        })
    return cleaned


def load_invoice(number: int):
    """Return (invoice dict incl. current client contact, lines) or (None, [])."""
    conn = db.get_db()
    inv = conn.execute(
        "SELECT i.*, c.address AS client_address, c.phone AS client_phone, "
        "       c.email AS client_email, c.customer_code AS client_code "
        "FROM invoices i LEFT JOIN clients c ON c.client_id = i.client_id "
        "WHERE i.invoice_number = ?",
        (number,),
    ).fetchone()
    if not inv:
        return None, []
    lines = conn.execute(
        "SELECT type, description, quantity, unit_price, line_total "
        "FROM invoice_lines WHERE invoice_number = ? ORDER BY line_order",
        (number,),
    ).fetchall()
    return dict(inv), [dict(r) for r in lines]


def save_invoice(payload: dict) -> dict:
    """Create or update an invoice, then (re)generate its PDF on disk.

    Returns {invoice_number, pdf_filename, is_historical}.
    """
    number = payload.get("invoice_number")
    client_id = payload.get("client_id") or None
    invoice_date = parse_nz_date(payload.get("invoice_date"))
    reference = (payload.get("reference") or "").strip()
    details = (payload.get("details") or "").strip()
    lines = _clean_lines(payload.get("lines"))

    gst_rate = db.get_setting("gst_rate", "15") or "15"
    t = money.totals([ln["line_total"] for ln in lines], gst_rate)
    subtotal, gst, amount = (money.to_float(t["subtotal"]),
                             money.to_float(t["gst"]),
                             money.to_float(t["amount_payable"]))

    stale_pdf: Path | None = None

    with db.writing("Saved an invoice") as conn:
        # Snapshot the client's name as it is right now.
        snapshot = (payload.get("client_name") or "").strip()
        if client_id and not snapshot:
            row = conn.execute("SELECT name FROM clients WHERE client_id = ?", (client_id,)).fetchone()
            snapshot = row["name"] if row else ""

        if not number:  # new invoice
            number = next_invoice_number(conn)
            filename = build_filename(number, reference)
            conn.execute(
                "INSERT INTO invoices(invoice_number, client_id, client_name_snapshot, "
                "reference, invoice_date, details, subtotal, gst, amount_payable, "
                "status, pdf_filename, is_historical, created_date, last_modified_date) "
                "VALUES(?,?,?,?,?,?,?,?,?,'Unpaid',?, 'No', ?, ?)",
                (number, client_id, snapshot, reference, invoice_date, details,
                 subtotal, gst, amount, filename, db.today_iso(), db.today_iso()),
            )
        else:  # edit existing
            old = conn.execute(
                "SELECT pdf_filename FROM invoices WHERE invoice_number = ?", (number,)
            ).fetchone()
            old_filename = old["pdf_filename"] if old else None
            filename = build_filename(number, reference)
            if old_filename and old_filename != filename:
                stale_pdf = config.invoices_dir() / old_filename
            conn.execute(
                "UPDATE invoices SET client_id=?, client_name_snapshot=?, reference=?, "
                "invoice_date=?, details=?, subtotal=?, gst=?, amount_payable=?, "
                "pdf_filename=?, last_modified_date=? WHERE invoice_number=?",
                (client_id, snapshot, reference, invoice_date, details, subtotal,
                 gst, amount, filename, db.today_iso(), number),
            )
            conn.execute("DELETE FROM invoice_lines WHERE invoice_number = ?", (number,))

        for order, ln in enumerate(lines, start=1):
            conn.execute(
                "INSERT INTO invoice_lines(invoice_number, line_order, type, "
                "description, quantity, unit_price, line_total) VALUES(?,?,?,?,?,?,?)",
                (number, order, ln["type"], ln["description"], ln["quantity"],
                 ln["unit_price"], ln["line_total"]),
            )

    # ---- After the transaction commits: tidy the old file and write the PDF ----
    if stale_pdf and stale_pdf.exists():
        try:
            stale_pdf.unlink()
        except OSError:
            pass

    inv, line_rows = load_invoice(number)
    html = invoice_render.render(inv, line_rows, db.get_settings())
    pdf.html_to_pdf(html, config.invoices_dir() / filename)

    return {"invoice_number": number, "pdf_filename": filename, "is_historical": "No"}
