"""Backend Config: a deliberately technical, non-user-friendly page.

Holds diagnostics, raw settings, the colour palette (req 9), default summary
period (req 8), logo upload (req 12), backups / restore / export / import / data
folder, and a final 'burn it all' reset.
"""
from __future__ import annotations

import io
import platform
import sys

from flask import (Blueprint, redirect, render_template, request, url_for)

from .. import (backup, config, db, exports, importer, invoice_service, palette,
                periods, version)

bp = Blueprint("config", __name__, url_prefix="/config")

# Garbage sample values used by 'burn it all' (req 3).
SAMPLE = {
    "business_name": "ACME Sample Workshop Ltd", "owner_name": "Sample Owner",
    "business_address": "123 Example Road, Nowhere", "business_phone": "00 000 0000",
    "business_email": "sample@example.com", "gst_number": "000-000-000",
    "bank_name": "Sample Bank", "bank_account_name": "SAMPLE ACCOUNT",
    "bank_account_number": "00-0000-0000000-00",
}

# How each setting key is edited in the backend table.
_DROPDOWNS = {
    "theme": ["light", "dark"],
    "gst_frequency": ["monthly", "2 months", "6 monthly"],
    "default_summary_period": [k for k, _ in periods.PRESETS],
}


@bp.route("/")
def index():
    return render_template(
        "config.html",
        diag=_diagnostics(),
        settings=_settings_rows(),
        dropdowns=_DROPDOWNS,
        palette_warnings=palette.warnings(db.get_settings(), db.get_setting("theme", "dark")),
        saved=request.args.get("saved"),
    )


def _settings_rows():
    rows = db.get_db().execute("SELECT key, value FROM settings ORDER BY key").fetchall()
    out = []
    for r in rows:
        key = r["key"]
        kind = "color" if key.startswith("color_") else ("select" if key in _DROPDOWNS else "text")
        out.append({"key": key, "value": r["value"], "kind": kind,
                    "options": _DROPDOWNS.get(key, [])})
    return out


def _diagnostics():
    conn = db.get_db()
    root = config.get_root()
    db_file = config.db_path()
    logo = config.templates_dir() / db.get_setting("logo_filename", "logo.jpg")
    n_inv = conn.execute("SELECT COUNT(*) c FROM invoices").fetchone()["c"]
    n_hist = conn.execute("SELECT COUNT(*) c FROM invoices WHERE is_historical='Yes'").fetchone()["c"]
    n_cli = conn.execute("SELECT COUNT(*) c FROM clients").fetchone()["c"]
    max_inv = conn.execute("SELECT MAX(invoice_number) m FROM invoices").fetchone()["m"]
    return {
        "App version": version.VERSION,
        "Published": version.PUBLICATION_DATE,
        "Program folder": str(config.PROJECT_DIR),
        "Update source (repo)": db.get_setting("update_repo") or "(not set)",
        "Data folder": str(root),
        "Database file": str(db_file),
        "Database size (KB)": round(db_file.stat().st_size / 1024, 1) if db_file.exists() else 0,
        "Invoice template": str(config.invoice_template()),
        "Template exists": config.invoice_template().exists(),
        "Logo file": str(logo),
        "Logo exists": logo.exists(),
        "Clients": n_cli,
        "Invoices (total)": n_inv,
        "Invoices (historical)": n_hist,
        "Invoices (new)": n_inv - n_hist,
        "Highest invoice number": max_inv if max_inv is not None else "—",
        "Next invoice number": invoice_service.next_invoice_number(conn),
        "Starting number setting": db.get_setting("starting_invoice_number"),
        "GST rate (%)": db.get_setting("gst_rate"),
        "GST frequency": db.get_setting("gst_frequency"),
        "Backups kept": len(list(config.backups_dir().glob("gsd_*.db"))),
        "Latest backup": (backup.latest_backup().name if backup.latest_backup() else "none"),
        "Exports folder": str(config.exports_dir()),
        "App theme": db.get_setting("theme"),
        "Python": sys.version.split()[0],
        "Platform": platform.platform(),
    }


# ---- Settings + palette + default period (one save) ----

@bp.route("/save-settings", methods=["POST"])
def save_settings():
    values = {k[2:]: (v or "").strip() for k, v in request.form.items() if k.startswith("s_")}
    if values:
        db.save_settings(values)
    return redirect(url_for("config.index", saved="settings"))


# ---- Data functions ----

@bp.route("/backup", methods=["POST"])
def backup_now():
    backup.backup_now("Manual backup")
    return redirect(url_for("config.index", saved="backup"))


@bp.route("/restore", methods=["POST"])
def restore():
    backup.restore_latest()
    return redirect(url_for("config.index", saved="restore"))


@bp.route("/export", methods=["POST"])
def export_excel():
    exports.export_all()
    return redirect(url_for("config.index", saved="export"))


@bp.route("/datafolder", methods=["POST"])
def change_data_folder():
    new_path = (request.form.get("data_folder") or "").strip()
    if new_path:
        try:
            config.relocate(new_path, copy_existing=True)
            db.init_db()
        except OSError:
            return render_template("error.html",
                                   message="That folder could not be used. Check the path "
                                           "and your permissions, then try again.")
    return redirect(url_for("config.index", saved="moved"))


@bp.route("/import", methods=["GET", "POST"])
def import_historical():
    if request.method == "POST":
        report = importer.run_import(copy_pdfs=True)
        return render_template("import.html", report=report)
    return render_template("import.html", report=None, already=importer.already_imported())


# ---- Logo upload (req 12) ----

@bp.route("/logo", methods=["POST"])
def upload_logo():
    file = request.files.get("logo")
    if not file or not file.filename:
        return redirect(url_for("config.index", saved="logo-none"))
    err = _save_logo(file)
    return redirect(url_for("config.index", saved=("logo-ok" if err is None else "logo-bad")))


def _save_logo(file) -> str | None:
    """Validate an uploaded image and save a copy to the data folder."""
    from PIL import Image

    data = file.read()
    if len(data) > 5 * 1024 * 1024:
        return "too big"
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
    except Exception:
        return "not an image"
    fmt = (img.format or "").upper()
    exts = {"PNG": "png", "JPEG": "jpg", "GIF": "gif", "WEBP": "webp", "BMP": "bmp"}
    if fmt not in exts:
        return "unsupported"
    w, h = img.size
    if w < 40 or h < 40 or w > 4000 or h > 4000:
        return "bad dimensions"
    if not (0.1 <= w / h <= 12):
        return "bad ratio"
    name = "logo." + exts[fmt]
    (config.templates_dir() / name).write_bytes(data)
    db.save_settings({"logo_filename": name})
    return None


# ---- Burn it all to the ground (req 3) ----

@bp.route("/reset", methods=["POST"])
def burn_it_all():
    with db.writing("Reset everything (burn it all)") as conn:
        conn.execute("DELETE FROM invoice_lines")
        conn.execute("DELETE FROM invoices")
        conn.execute("DELETE FROM clients")
        for key, value in {**SAMPLE, **palette.DEFAULTS}.items():
            conn.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    return redirect(url_for("config.index", saved="burned"))
