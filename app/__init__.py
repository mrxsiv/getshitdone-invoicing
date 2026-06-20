"""GET SHIT DONE - offline invoicing app.

Small local Flask web server.
"""
from __future__ import annotations

from flask import Flask, abort, render_template, send_from_directory

from . import config, db, palette, version


def create_app() -> Flask:
    """Build and configure the Flask application."""
    root = config.ensure_structure()

    app = Flask(
        __name__,
        template_folder="web/templates",
        static_folder="web/static",
    )
    app.config["INVOICING_ROOT"] = str(root)
    # Roomy upload limit for a future logo replace; plenty for this app.
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    db.init_db()

    # Make the database available per-request and closed cleanly afterwards.
    app.teardown_appcontext(db.close_db)

    # Blueprints (each screen is its own module).
    from .blueprints import (clients, config_page, dashboard, invoices,
                             outstanding, settings as settings_bp)

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(invoices.bp)
    app.register_blueprint(outstanding.bp)
    app.register_blueprint(settings_bp.bp)
    app.register_blueprint(config_page.bp)

    # Serve the business logo (used on the sidebar) from the data folder.
    @app.route("/logo")
    def logo():
        name = db.get_setting("logo_filename", "logo.jpg")
        if not (config.templates_dir() / name).exists():
            abort(404)
        return send_from_directory(config.templates_dir(), name)

    # Calm, friendly error page instead of a raw stack trace / error code.
    @app.errorhandler(500)
    def _internal_error(e):  # pragma: no cover - defensive
        return render_template("error.html",
                               message="Something went wrong while doing that. "
                                       "Your data is safe. Please try again."), 500

    @app.errorhandler(404)
    def _not_found(e):
        return render_template("error.html",
                               message="That page could not be found."), 404

    # Expose business settings + the colour palette CSS to every template.
    @app.context_processor
    def _inject_settings():
        settings = db.get_settings()
        return {
            "biz": settings,
            "palette_css": palette.css(settings, settings.get("theme", "dark")),
            "logo_filename": settings.get("logo_filename", "logo.jpg"),
            "app_version": version.VERSION,
            "publication_date": version.PUBLICATION_DATE,
            "version_label": version.version_label(),
        }

    return app
