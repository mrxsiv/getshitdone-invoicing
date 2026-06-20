"""Invoices: create, edit, save, PDF and email hand-off (brief 7.3 / 10)."""
from __future__ import annotations

from datetime import date

from flask import (Blueprint, abort, jsonify, render_template, request,
                   send_from_directory)

from .. import config, db, invoice_service, money
from ..utils import nz_date

bp = Blueprint("invoices", __name__, url_prefix="/invoices")


PAGE_SIZES = (10, 20, 50, 100)
SORTS = {
    "number": "invoice_number",
    "date": "invoice_date",
    "client": "client_name_snapshot COLLATE NOCASE",
    "reference": "reference COLLATE NOCASE",
    "amount": "amount_payable",
    "status": "status",
}


@bp.route("/")
def index():
    conn = db.get_db()
    try:
        per_page = int(request.args.get("per_page", 50))
    except ValueError:
        per_page = 50
    if per_page not in PAGE_SIZES:
        per_page = 50
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "number"
    direction = "asc" if request.args.get("dir") == "asc" else "desc"
    order = f"ORDER BY {SORTS[sort]} {direction.upper()}, invoice_number DESC"

    total = conn.execute("SELECT COUNT(*) n FROM invoices").fetchone()["n"]
    pages = max(1, -(-total // per_page))  # ceil division
    page = min(page, pages)
    offset = (page - 1) * per_page

    rows = conn.execute(
        "SELECT invoice_number, client_name_snapshot, invoice_date, reference, "
        "amount_payable, status FROM invoices " + order + " LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    invoices = [{
        "invoice_number": r["invoice_number"],
        "client": r["client_name_snapshot"],
        "date": nz_date(r["invoice_date"]),
        "reference": r["reference"] or "",
        "amount": money.money(r["amount_payable"]),
        "status": r["status"],
    } for r in rows]
    return render_template(
        "invoices_list.html", invoices=invoices,
        page=page, pages=pages, per_page=per_page, page_sizes=PAGE_SIZES,
        total=total, start=(offset + 1 if total else 0), end=min(offset + per_page, total),
        sort=sort, dir=direction,
    )


def _clients_for_picker():
    rows = db.get_db().execute(
        "SELECT client_id, customer_code, name, address, phone, email "
        "FROM clients ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [{
        "id": r["client_id"], "code": r["customer_code"] or "", "name": r["name"],
        "address": r["address"] or "", "phone": r["phone"] or "", "email": r["email"] or "",
    } for r in rows]


@bp.route("/new")
def new():
    return render_template(
        "invoice_form.html",
        invoice=None, lines=[], clients=_clients_for_picker(),
        today=date.today().strftime("%d/%m/%Y"),
    )


@bp.route("/<int:number>")
def edit(number):
    inv, lines = invoice_service.load_invoice(number)
    if not inv:
        return render_template("error.html", message="That invoice could not be found."), 404

    # Historical imported invoices are totals + original PDF only: show read-only.
    if inv.get("is_historical") == "Yes":
        return render_template("invoice_view.html", inv={
            "invoice_number": inv["invoice_number"],
            "client": inv["client_name_snapshot"],
            "date": nz_date(inv["invoice_date"]),
            "reference": inv["reference"] or "",
            "amount": money.money(inv["amount_payable"]),
            "gst": money.money(inv["gst"]),
            "subtotal": money.money(inv["subtotal"]),
            "status": inv["status"],
            "pdf_filename": inv["pdf_filename"],
        })

    form_inv = {
        "invoice_number": inv["invoice_number"],
        "client_id": inv["client_id"],
        "client_name": inv["client_name_snapshot"],
        "invoice_date": nz_date(inv["invoice_date"]),
        "reference": inv["reference"] or "",
        "details": inv["details"] or "",
        "status": inv["status"],
    }
    form_lines = [{
        "type": l["type"] or "Labour",
        "description": l["description"] or "",
        "quantity": l["quantity"],
        "unit_price": l["unit_price"],
    } for l in lines]
    return render_template(
        "invoice_form.html",
        invoice=form_inv, lines=form_lines, clients=_clients_for_picker(),
        today=date.today().strftime("%d/%m/%Y"),
    )


@bp.route("/save", methods=["POST"])
def save():
    payload = request.get_json(silent=True) or {}
    result = invoice_service.save_invoice(payload)
    return jsonify({"ok": True, **result})


@bp.route("/<int:number>/toggle-status", methods=["POST"])
def toggle_status(number):
    """Flip an invoice between Paid and Unpaid (req: clickable status)."""
    conn = db.get_db()
    row = conn.execute("SELECT status FROM invoices WHERE invoice_number = ?", (number,)).fetchone()
    if not row:
        return jsonify(ok=False), 404
    new_status = "Unpaid" if row["status"] == "Paid" else "Paid"
    paid_date = db.today_iso() if new_status == "Paid" else None
    with db.writing("Changed an invoice's paid status") as c:
        c.execute("UPDATE invoices SET status = ?, paid_date = ? WHERE invoice_number = ?",
                  (new_status, paid_date, number))
    return jsonify(ok=True, invoice_number=number, status=new_status)


@bp.route("/<int:number>/delete", methods=["POST"])
def delete(number):
    """Delete an incorrect invoice and its PDF file."""
    conn = db.get_db()
    row = conn.execute("SELECT pdf_filename FROM invoices WHERE invoice_number = ?", (number,)).fetchone()
    if not row:
        return jsonify(ok=False), 404
    pdf_name = row["pdf_filename"]
    with db.writing("Deleted an invoice") as c:
        c.execute("DELETE FROM invoice_lines WHERE invoice_number = ?", (number,))
        c.execute("DELETE FROM invoices WHERE invoice_number = ?", (number,))
    if pdf_name:
        pdf_path = config.invoices_dir() / pdf_name
        if pdf_path.exists():
            try:
                pdf_path.unlink()
            except OSError:
                pass
    return jsonify(ok=True)


@bp.route("/<int:number>/pdf")
def pdf_file(number):
    row = db.get_db().execute(
        "SELECT pdf_filename FROM invoices WHERE invoice_number = ?", (number,)
    ).fetchone()
    if not row or not row["pdf_filename"]:
        abort(404)
    as_download = request.args.get("download") == "1"
    return send_from_directory(
        config.invoices_dir(), row["pdf_filename"],
        as_attachment=as_download, download_name=row["pdf_filename"],
    )
