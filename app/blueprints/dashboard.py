"""Dashboard: at-a-glance numbers, a period summary, and a trend chart (brief 7.1)."""
from __future__ import annotations

from datetime import date, timedelta

from flask import Blueprint, render_template, request

from .. import db, money, periods
from ..utils import nz_date, parse_nz_date

bp = Blueprint("dashboard", __name__)

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@bp.route("/")
def home():
    conn = db.get_db()
    today = date.today()
    week_ago = (today - timedelta(days=7)).isoformat()

    unpaid = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(amount_payable), 0) total "
        "FROM invoices WHERE status = 'Unpaid'"
    ).fetchone()

    # --- Period summary (req 5/6/8): presets + custom range ---
    gst_freq = db.get_setting("gst_frequency", "2 months")
    default_period = db.get_setting("default_summary_period", "month-to-date")
    raw_from = request.args.get("from")
    raw_to = request.args.get("to")
    preset = request.args.get("period")
    if raw_from or raw_to:  # custom range from the date pickers
        from_iso = parse_nz_date(raw_from) if raw_from else today.replace(day=1).isoformat()
        to_iso = parse_nz_date(raw_to) if raw_to else today.isoformat()
        sel_preset = "custom"
    else:
        sel_preset = preset if preset in periods.PRESET_KEYS else default_period
        from_iso, to_iso = periods.resolve(sel_preset, today, gst_freq)
    period = _period_summary(conn, from_iso, to_iso)

    # --- Overdue list (req 8: clickable through to the invoice) ---
    overdue_rows = conn.execute(
        "SELECT invoice_number, client_name_snapshot, invoice_date, amount_payable "
        "FROM invoices WHERE status = 'Unpaid' AND invoice_date < ? ORDER BY invoice_date ASC",
        (week_ago,),
    ).fetchall()
    overdue = [{
        "invoice_number": r["invoice_number"],
        "client": r["client_name_snapshot"],
        "date": nz_date(r["invoice_date"]),
        "amount": money.money(r["amount_payable"]),
    } for r in overdue_rows]

    # --- Trend chart (req 6): 13 months, selectable year ---
    years = _available_years(conn, today)
    try:
        sel_year = int(request.args.get("year") or today.year)
    except ValueError:
        sel_year = today.year
    series = _trend_series(conn, sel_year, today)

    return render_template(
        "dashboard.html",
        unpaid_count=unpaid["n"],
        unpaid_total=money.money(unpaid["total"]),
        period=period,
        from_iso=from_iso, to_iso=to_iso,
        presets=periods.PRESETS, sel_preset=sel_preset,
        overdue=overdue,
        years=years, sel_year=sel_year, series=series,
    )


def _period_summary(conn, from_iso: str, to_iso: str) -> dict:
    """Volume and ex-GST money totals for invoices dated within [from, to]."""
    count = conn.execute(
        "SELECT COUNT(*) n FROM invoices WHERE invoice_date BETWEEN ? AND ?",
        (from_iso, to_iso),
    ).fetchone()["n"]

    # Labour / Part / Other split comes from line items (ex-GST line totals).
    by_type = {"Labour": 0.0, "Part": 0.0, "Other": 0.0}
    rows = conn.execute(
        "SELECT l.type AS t, COALESCE(SUM(l.line_total), 0) AS s "
        "FROM invoice_lines l JOIN invoices i ON i.invoice_number = l.invoice_number "
        "WHERE i.invoice_date BETWEEN ? AND ? GROUP BY l.type",
        (from_iso, to_iso),
    ).fetchall()
    for r in rows:
        if r["t"] in by_type:
            by_type[r["t"]] += r["s"]

    # Total ex-GST uses the invoice subtotal, so historical invoices (which have
    # no line items) still contribute to the total even though they can't be split.
    total_ex = conn.execute(
        "SELECT COALESCE(SUM(subtotal), 0) s FROM invoices WHERE invoice_date BETWEEN ? AND ?",
        (from_iso, to_iso),
    ).fetchone()["s"]

    # Anything not in a line-item category (i.e. older imported invoices) so the
    # figures always add up to the total. Shrinks to ~$0 as new invoices replace old.
    unitemised = max(0.0, total_ex - sum(by_type.values()))

    return {
        "count": count,
        "labour": money.money(by_type["Labour"]),
        "parts": money.money(by_type["Part"]),
        "other": money.money(by_type["Other"]),
        "unitemised": money.money(unitemised),
        "has_unitemised": unitemised > 0.005,
        "total_ex_gst": money.money(total_ex),
    }


def _available_years(conn, today: date) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT substr(invoice_date, 1, 4) y FROM invoices "
        "WHERE invoice_date <> '' ORDER BY y DESC"
    ).fetchall()
    years = {int(r["y"]) for r in rows if (r["y"] or "").isdigit()}
    years.add(today.year)
    return sorted(years, reverse=True)


def _trend_series(conn, year: int, today: date) -> list[dict]:
    """13 consecutive months ending in the selected year (so a full year is
    always visible alongside the same month a year earlier)."""
    end_year, end_month = (today.year, today.month) if year == today.year else (year, 12)

    # Walk back 12 months to get the 13-month window start.
    months: list[tuple[int, int]] = []
    y, m = end_year, end_month
    for _ in range(13):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()

    start_iso = f"{months[0][0]:04d}-{months[0][1]:02d}-01"
    # End bound: first day of the month after the last one.
    ey, em = months[-1]
    nm_y, nm_m = (ey + 1, 1) if em == 12 else (ey, em + 1)
    end_iso = f"{nm_y:04d}-{nm_m:02d}-01"

    vol_sales = {r["ym"]: r for r in conn.execute(
        "SELECT substr(invoice_date,1,7) ym, COUNT(*) n, COALESCE(SUM(subtotal),0) s "
        "FROM invoices WHERE invoice_date >= ? AND invoice_date < ? GROUP BY ym",
        (start_iso, end_iso),
    ).fetchall()}
    labour = {r["ym"]: r["s"] for r in conn.execute(
        "SELECT substr(i.invoice_date,1,7) ym, COALESCE(SUM(l.line_total),0) s "
        "FROM invoice_lines l JOIN invoices i ON i.invoice_number = l.invoice_number "
        "WHERE l.type = 'Labour' AND i.invoice_date >= ? AND i.invoice_date < ? GROUP BY ym",
        (start_iso, end_iso),
    ).fetchall()}

    series = []
    for (yy, mm) in months:
        key = f"{yy:04d}-{mm:02d}"
        vs = vol_sales.get(key)
        series.append({
            "label": _MONTHS[mm - 1],
            "year": yy,
            "volume": vs["n"] if vs else 0,
            "sales": round(vs["s"], 2) if vs else 0.0,
            "labour": round(labour.get(key, 0.0), 2),
        })
    return series
