"""Settings: business details, branding, preferences (brief 7.6).

The technical/dangerous functions (backups, data folder, import, palette, logo,
reset) live behind the Backend Config page instead.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from .. import db, updater

bp = Blueprint("settings", __name__, url_prefix="/settings")

EDITABLE = [
    "business_name", "owner_name", "business_address", "business_phone",
    "business_email", "gst_number", "bank_name", "bank_account_name",
    "bank_account_number", "theme", "gst_rate", "gst_frequency",
    "starting_invoice_number",
]


@bp.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        values = {k: (request.form.get(k) or "").strip() for k in EDITABLE if k in request.form}
        db.save_settings(values)
        return redirect(url_for("settings.index", saved="1"))
    return render_template("settings.html", saved=request.args.get("saved") == "1")


@bp.route("/updates/check")
def updates_check():
    return jsonify(updater.check())


@bp.route("/updates/apply", methods=["POST"])
def updates_apply():
    return jsonify(updater.start_download())


@bp.route("/updates/progress")
def updates_progress():
    return jsonify(updater.download_state())
