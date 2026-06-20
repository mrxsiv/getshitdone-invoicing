"""Outstanding: every unpaid invoice, with a paid tick, sorting and paging (brief 7.4)."""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, jsonify, render_template, request

from .. import db, money
from ..utils import nz_date

bp = Blueprint("outstanding", __name__, url_prefix="/outstanding")

SORTS = {
    "date": "invoice_date",
    "client": "client_name_snapshot COLLATE NOCASE",
    "number": "invoice_number",
    "amount": "amount_payable",
}
PAGE_SIZES = (10, 20, 50, 100)


@bp.route("/")
def index():
    conn = db.get_db()
    week_ago = (date.today() - timedelta(days=7)).isoformat()

    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "date"
    direction = "desc" if request.args.get("dir") == "desc" else "asc"
    order = f"ORDER BY {SORTS[sort]} {direction.upper()}"

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

    total = conn.execute("SELECT COUNT(*) n FROM invoices WHERE status='Unpaid'").fetchone()["n"]
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    offset = (page - 1) * per_page

    rows = conn.execute(
        "SELECT invoice_number, client_name_snapshot, invoice_date, amount_payable "
        "FROM invoices WHERE status = 'Unpaid' " + order + " LIMIT ? OFFSET ?",
        (per_page, offset),
    ).fetchall()
    invoices = [{
        "invoice_number": r["invoice_number"],
        "client": r["client_name_snapshot"] or "",
        "date": nz_date(r["invoice_date"]),
        "amount": money.money(r["amount_payable"]),
        "overdue": bool(r["invoice_date"]) and r["invoice_date"] < week_ago,
    } for r in rows]

    return render_template(
        "outstanding.html", invoices=invoices, sort=sort, dir=direction,
        page=page, pages=pages, per_page=per_page, page_sizes=PAGE_SIZES,
        total=total, start=(offset + 1 if total else 0), end=min(offset + per_page, total),
    )


@bp.route("/<int:number>/paid", methods=["POST"])
def mark_paid(number):
    with db.writing("Marked an invoice paid") as conn:
        conn.execute(
            "UPDATE invoices SET status = 'Paid', paid_date = ? WHERE invoice_number = ?",
            (db.today_iso(), number),
        )
    return jsonify(ok=True, invoice_number=number)


@bp.route("/<int:number>/unpaid", methods=["POST"])
def mark_unpaid(number):
    """Undo: put the invoice back to unpaid and clear the paid date."""
    with db.writing("Undid a paid mark") as conn:
        conn.execute(
            "UPDATE invoices SET status = 'Unpaid', paid_date = NULL WHERE invoice_number = ?",
            (number,),
        )
    return jsonify(ok=True, invoice_number=number)
