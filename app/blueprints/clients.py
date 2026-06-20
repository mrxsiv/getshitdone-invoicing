"""Clients: a searchable contact list with add / edit / delete (brief 7.2)."""
from __future__ import annotations

import re

from flask import Blueprint, redirect, render_template, request, url_for

from .. import db, money
from ..utils import nz_date

bp = Blueprint("clients", __name__, url_prefix="/clients")


SORTS = {
    "name": "name COLLATE NOCASE",
    "phone": "phone COLLATE NOCASE",
    "email": "email COLLATE NOCASE",
}
PAGE_SIZES = (10, 20, 50, 100)
INVOICE_SORTS = {
    "number": "invoice_number",
    "date": "invoice_date",
    "reference": "reference COLLATE NOCASE",
    "amount": "amount_payable",
    "status": "status",
}


@bp.route("/")
def index():
    q = (request.args.get("q") or "").strip()
    conn = db.get_db()
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "name"
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

    where, params = "", ()
    if q:
        like = f"%{q}%"
        where = "WHERE name LIKE ? OR phone LIKE ? OR customer_code LIKE ? OR email LIKE ? "
        params = (like, like, like, like)

    total = conn.execute("SELECT COUNT(*) n FROM clients " + where, params).fetchone()["n"]
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    offset = (page - 1) * per_page

    rows = conn.execute(
        "SELECT client_id, customer_code, name, phone, email FROM clients " + where
        + order + " LIMIT ? OFFSET ?",
        params + (per_page, offset),
    ).fetchall()
    return render_template(
        "clients_list.html", clients=rows, q=q, sort=sort, dir=direction,
        page=page, pages=pages, per_page=per_page, page_sizes=PAGE_SIZES,
        total=total, start=(offset + 1 if total else 0), end=min(offset + per_page, total),
    )


@bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        return _save(None)
    return render_template("client_form.html", client=None, invoices=[])


@bp.route("/<int:client_id>", methods=["GET", "POST"])
def edit(client_id):
    conn = db.get_db()
    if request.method == "POST":
        return _save(client_id)
    client = conn.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()
    if not client:
        return render_template("error.html", message="That client could not be found."), 404

    # Past invoices: sortable + paged, future-proofed for prolific clients.
    sort = request.args.get("sort") if request.args.get("sort") in INVOICE_SORTS else "number"
    direction = "desc" if request.args.get("dir", "desc") == "desc" else "asc"
    order = f"ORDER BY {INVOICE_SORTS[sort]} {direction.upper()}"
    try:
        per_page = int(request.args.get("per_page", 10))
    except ValueError:
        per_page = 10
    if per_page not in PAGE_SIZES:
        per_page = 10
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1

    total = conn.execute("SELECT COUNT(*) n FROM invoices WHERE client_id = ?", (client_id,)).fetchone()["n"]
    pages = max(1, -(-total // per_page))
    page = min(page, pages)
    offset = (page - 1) * per_page

    inv_rows = conn.execute(
        "SELECT invoice_number, invoice_date, reference, amount_payable, status "
        "FROM invoices WHERE client_id = ? " + order + " LIMIT ? OFFSET ?",
        (client_id, per_page, offset),
    ).fetchall()
    invoices = [{
        "invoice_number": r["invoice_number"],
        "date": nz_date(r["invoice_date"]),
        "reference": r["reference"] or "",
        "amount": money.money(r["amount_payable"]),
        "status": r["status"],
    } for r in inv_rows]
    return render_template(
        "client_form.html", client=client, invoices=invoices,
        sort=sort, dir=direction, page=page, pages=pages, per_page=per_page,
        page_sizes=PAGE_SIZES, total=total,
        start=(offset + 1 if total else 0), end=min(offset + per_page, total),
    )


@bp.route("/<int:client_id>/delete", methods=["POST"])
def delete(client_id):
    # Historic invoices keep their client_name_snapshot, so deleting a client
    # never breaks them; we just unlink (brief 7.2).
    with db.writing("Deleted a client") as conn:
        conn.execute("UPDATE invoices SET client_id = NULL WHERE client_id = ?", (client_id,))
        conn.execute("DELETE FROM clients WHERE client_id = ?", (client_id,))
    return redirect(url_for("clients.index"))


def _save(client_id):
    f = request.form
    name = (f.get("name") or "").strip()
    if not name:
        return render_template(
            "client_form.html", client=dict(f), invoices=[],
            error="Please enter the client's name.",
        )
    code = (f.get("customer_code") or "").strip()
    fields = {
        "customer_code": code,
        "name": name,
        "address": (f.get("address") or "").strip(),
        "phone": (f.get("phone") or "").strip(),
        "email": (f.get("email") or "").strip(),
        "notes": (f.get("notes") or "").strip(),
    }
    with db.writing("Saved a client") as conn:
        if client_id is None:
            if not code:
                fields["customer_code"] = _generate_code(conn, name)
            conn.execute(
                "INSERT INTO clients(customer_code, name, address, phone, email, "
                "created_date, notes) VALUES(?,?,?,?,?,?,?)",
                (fields["customer_code"], name, fields["address"], fields["phone"],
                 fields["email"], db.today_iso(), fields["notes"]),
            )
            client_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
        else:
            conn.execute(
                "UPDATE clients SET customer_code=?, name=?, address=?, phone=?, "
                "email=?, notes=? WHERE client_id=?",
                (fields["customer_code"], name, fields["address"], fields["phone"],
                 fields["email"], fields["notes"], client_id),
            )
    return redirect(url_for("clients.edit", client_id=client_id))


def _generate_code(conn, name: str) -> str:
    """Auto-generate a short, unique customer code from the name."""
    base = re.sub(r"[^A-Z]", "", name.upper())[:6] or "CLIENT"
    code, n = base, 1
    while conn.execute("SELECT 1 FROM clients WHERE customer_code = ?", (code,)).fetchone():
        n += 1
        code = f"{base}{n}"
    return code
