"""One-time historical data import for go-live (brief 15).

Reads the bundled `Historical Import Source` (already-normalised CSVs + PDFs),
loads clients and historical invoices, copies the invoice PDFs into the runtime
\\Invoices folder, then reconciles counts and totals against the source. If
anything fails to reconcile, the report says so plainly rather than guessing.

Receipts are deliberately not imported (the app has no receipt function).
"""
from __future__ import annotations

import csv
import re
import shutil

from . import config, db, money
from .utils import parse_nz_date


def _read_csv(path) -> list[dict]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))


def already_imported() -> bool:
    row = db.get_db().execute(
        "SELECT COUNT(*) AS n FROM invoices WHERE is_historical = 'Yes'"
    ).fetchone()
    return row["n"] > 0


def _invoice_number(raw: str) -> int:
    digits = re.sub(r"\D", "", raw or "")
    return int(digits) if digits else 0


def _detail_map() -> dict[int, tuple[float, float]]:
    """{invoice_number: (labour_ex_gst, non_labour_ex_gst)} from Invoices_Detail.csv."""
    src = config.HISTORICAL_SOURCE / "Invoices_Detail.csv"
    out: dict[int, tuple[float, float]] = {}
    if not src.exists():
        return out
    for r in _read_csv(src):
        n = _invoice_number(r.get("InvNumber"))
        if n:
            out[n] = (money.to_float(r.get("Labour (ex GST)") or 0),
                      money.to_float(r.get("Non Labour (ex GST)") or 0))
    return out


def _insert_detail_lines(conn, number: int, labour: float, non_labour: float) -> None:
    """Create Labour / Parts line items for a historical invoice from its detail."""
    order = 1
    if labour:
        conn.execute(
            "INSERT INTO invoice_lines(invoice_number, line_order, type, description, "
            "quantity, unit_price, line_total) VALUES(?,?,?,?,?,?,?)",
            (number, order, "Labour", "Labour", 1, labour, labour))
        order += 1
    if non_labour:
        conn.execute(
            "INSERT INTO invoice_lines(invoice_number, line_order, type, description, "
            "quantity, unit_price, line_total) VALUES(?,?,?,?,?,?,?)",
            (number, order, "Part", "Parts & materials", 1, non_labour, non_labour))


def ingest_detail() -> dict:
    """One-off: add labour/non-labour line items to already-imported historical
    invoices that don't have any yet (req: feed Trends + Business Summary)."""
    detail = _detail_map()
    if not detail:
        return {"status": "error", "message": "Invoices_Detail.csv was not found."}
    added = 0
    skipped = 0
    with db.writing("Ingested invoice labour/parts detail") as conn:
        for number, (labour, non_labour) in detail.items():
            inv = conn.execute(
                "SELECT 1 FROM invoices WHERE invoice_number=? AND is_historical='Yes'",
                (number,)).fetchone()
            if not inv:
                skipped += 1
                continue
            if conn.execute("SELECT 1 FROM invoice_lines WHERE invoice_number=?", (number,)).fetchone():
                skipped += 1
                continue
            _insert_detail_lines(conn, number, labour, non_labour)
            added += 1
    return {"status": "ok", "lines_added_for": added, "skipped": skipped}


def run_import(copy_pdfs: bool = True) -> dict:
    """Import clients + historical invoices and return a reconciliation report."""
    src = config.HISTORICAL_SOURCE
    if not (src / "Customers.csv").exists() or not (src / "Invoices.csv").exists():
        return {"status": "error",
                "message": "The historical source files could not be found."}

    if already_imported():
        return {"status": "already",
                "message": "Historical data has already been imported. "
                           "Nothing was changed."}

    customers = _read_csv(src / "Customers.csv")
    invoices = _read_csv(src / "Invoices.csv")
    src_invoices_dir = src / "Invoices"

    detail = _detail_map()  # labour / non-labour split per invoice
    clients_added = 0
    invoices_added = 0
    unmatched_client = 0
    pdf_linked = 0
    src_amount_sum = 0.0
    seen_numbers: set[int] = set()

    with db.writing("Imported historical data") as conn:
        # Existing customer_code -> client_id map (usually empty at go-live).
        code_map = {
            r["customer_code"]: r["client_id"]
            for r in conn.execute(
                "SELECT client_id, customer_code FROM clients WHERE customer_code IS NOT NULL"
            ).fetchall()
        }

        for row in customers:
            code = (row.get("CustomerCode") or "").strip()
            name = (row.get("Customer Name") or "").strip()
            if not code or code in code_map:
                continue
            conn.execute(
                "INSERT INTO clients(customer_code, name, address, phone, email, "
                "created_date, notes) VALUES(?,?,?,?,?,?,'')",
                (code, name, (row.get("Address") or "").strip(),
                 (row.get("Phone") or "").strip(), (row.get("Email") or "").strip(),
                 db.today_iso()),
            )
            code_map[code] = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            clients_added += 1

        for row in invoices:
            number = _invoice_number(row.get("InvNumber"))
            if not number or number in seen_numbers:
                continue
            seen_numbers.add(number)

            code = (row.get("CustomerCode") or "").strip()
            name = (row.get("Customer Name") or "").strip()
            client_id = code_map.get(code)
            if not client_id:
                unmatched_client += 1

            amount = money.to_float(row.get("Amount") or 0)
            gst = money.to_float(row.get("GST") or 0)
            subtotal = money.to_float(amount - gst)
            balance = money.to_float(row.get("Balance") or 0)
            status = "Paid" if balance == 0 else "Unpaid"
            date_iso = parse_nz_date(row.get("Date"))

            raw_inv = (row.get("InvNumber") or "").strip()
            pdf_name = f"{raw_inv}.pdf"
            has_pdf = (src_invoices_dir / pdf_name).exists()
            if has_pdf:
                pdf_linked += 1

            src_amount_sum += amount
            conn.execute(
                "INSERT INTO invoices(invoice_number, client_id, client_name_snapshot, "
                "reference, invoice_date, details, subtotal, gst, amount_payable, status, "
                "paid_date, pdf_filename, is_historical, created_date, last_modified_date) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'Yes', ?, ?)",
                (number, client_id, name, None, date_iso, None, subtotal, gst, amount,
                 status, date_iso if status == "Paid" else None,
                 pdf_name if has_pdf else None, db.today_iso(), db.today_iso()),
            )
            if number in detail:
                _insert_detail_lines(conn, number, *detail[number])
            invoices_added += 1

    # ---- Copy the invoice PDFs into the runtime folder (outside the txn) ----
    pdfs_copied = 0
    if copy_pdfs and src_invoices_dir.exists():
        dest = config.invoices_dir()
        for p in src_invoices_dir.glob("*.pdf"):
            target = dest / p.name
            if not target.exists():
                shutil.copy2(p, target)
                pdfs_copied += 1

    # ---- Reconcile against the source (brief 15, mandatory) ----
    conn = db.get_db()
    db_hist_invoices = conn.execute(
        "SELECT COUNT(*) AS n FROM invoices WHERE is_historical = 'Yes'"
    ).fetchone()["n"]
    db_amount_sum = conn.execute(
        "SELECT COALESCE(SUM(amount_payable), 0) AS s FROM invoices WHERE is_historical = 'Yes'"
    ).fetchone()["s"]

    src_invoice_rows = sum(1 for r in invoices if _invoice_number(r.get("InvNumber")))
    src_customer_rows = sum(1 for r in customers if (r.get("CustomerCode") or "").strip())

    counts_ok = (invoices_added == db_hist_invoices == len(seen_numbers))
    amount_ok = abs(round(src_amount_sum, 2) - round(db_amount_sum, 2)) < 0.01
    reconciled = counts_ok and amount_ok

    return {
        "status": "ok" if reconciled else "mismatch",
        "reconciled": reconciled,
        "clients_added": clients_added,
        "source_customer_rows": src_customer_rows,
        "invoices_added": invoices_added,
        "source_invoice_rows": src_invoice_rows,
        "unmatched_client": unmatched_client,
        "pdf_linked": pdf_linked,
        "pdfs_copied": pdfs_copied,
        "source_amount_total": money.money(src_amount_sum),
        "imported_amount_total": money.money(db_amount_sum),
        "amount_ok": amount_ok,
        "counts_ok": counts_ok,
    }
