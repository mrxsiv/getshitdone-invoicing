"""SQLite access: connection handling, schema, settings, and safe writes.

Money is computed with Decimal (see money.py) and stored already rounded to two
decimal places. Identifiers (GST number, bank account number, customer codes)
are stored as TEXT and never reformatted.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date

from flask import g

from . import backup, config

# Business defaults seeded on first run (brief 4.1 / 7.6). All editable later.
DEFAULT_SETTINGS = {
    # Generic placeholders for a fresh install. Each user sets their own details
    # in Settings (kept only in their local data folder, never in the code).
    "business_name": "Your Business Name Ltd",
    "owner_name": "Your Name",
    "business_address": "123 Example Street, Your Town",
    "business_phone": "00 000 0000",
    "business_email": "you@example.com",
    "gst_number": "",
    "bank_name": "Your Bank",
    "bank_account_name": "YOUR ACCOUNT NAME",
    "bank_account_number": "00-0000-0000000-00",
    "theme": "dark",
    "gst_rate": "15",
    "gst_frequency": "2 months",
    "starting_invoice_number": "2000",
    "logo_filename": "logo.jpg",
    "default_summary_period": "month-to-date",
    "update_repo": "",  # GitHub owner/name for "Check for updates"
    # Configurable colour palette (Backend Config). Flows through all pages.
    "color_brand": "#c0202a",
    "color_brand_dark": "#8a1620",
    "color_paid": "#1a7f37",
    "color_overdue": "#b3261e",
    "color_sales": "#e0424c",
    "color_labour": "#2e9e5b",
    "color_volume": "#3b7dd8",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    client_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_code TEXT,
    name          TEXT NOT NULL,
    address       TEXT,
    phone         TEXT,
    email         TEXT,
    created_date  TEXT,
    notes         TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_clients_code
    ON clients(customer_code) WHERE customer_code IS NOT NULL AND customer_code <> '';

CREATE TABLE IF NOT EXISTS invoices (
    invoice_number        INTEGER PRIMARY KEY,
    client_id             INTEGER REFERENCES clients(client_id),
    client_name_snapshot  TEXT,
    reference             TEXT,
    invoice_date          TEXT,
    details               TEXT,
    subtotal              REAL,
    gst                   REAL,
    amount_payable        REAL,
    status                TEXT DEFAULT 'Unpaid',
    paid_date             TEXT,
    pdf_filename          TEXT,
    is_historical         TEXT DEFAULT 'No',
    created_date          TEXT,
    last_modified_date    TEXT
);
CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS ix_invoices_client ON invoices(client_id);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number INTEGER REFERENCES invoices(invoice_number) ON DELETE CASCADE,
    line_order     INTEGER,
    type           TEXT,
    description    TEXT,
    quantity       REAL,
    unit_price     REAL,
    line_total     REAL
);
CREATE INDEX IF NOT EXISTS ix_lines_invoice ON invoice_lines(invoice_number);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def get_db() -> sqlite3.Connection:
    """Per-request connection, stored on Flask's `g`."""
    if "db" not in g:
        conn = sqlite3.connect(config.db_path())
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(exc=None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db() -> None:
    """Create tables (if missing) and seed default settings."""
    conn = sqlite3.connect(config.db_path())
    try:
        conn.executescript(SCHEMA)
        existing = {r[0] for r in conn.execute("SELECT key FROM settings")}
        for key, value in DEFAULT_SETTINGS.items():
            if key not in existing:
                conn.execute("INSERT INTO settings(key, value) VALUES (?, ?)", (key, value))
        conn.commit()
    finally:
        conn.close()


# ---- Settings helpers ----

def get_settings() -> dict[str, str]:
    rows = get_db().execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def get_setting(key: str, default: str = "") -> str:
    row = get_db().execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def save_settings(values: dict[str, str]) -> None:
    with writing("Saved settings"):
        db = get_db()
        for key, value in values.items():
            db.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )


@contextmanager
def writing(reason: str = "change"):
    """Back up the database, then run a write inside one transaction.

    Brief 3.2: a timestamped backup is taken before every change. If the write
    fails, the transaction rolls back and the backup remains as a safety net.
    """
    backup.backup_now(reason)
    db = get_db()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def today_iso() -> str:
    return date.today().isoformat()
