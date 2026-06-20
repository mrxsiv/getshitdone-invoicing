"""Timestamped database backups taken before every write (brief 3.2).

Keeps the most recent 30 backups in the hidden-ish `_backups` folder. On a
damaged database, `latest_backup()` lets the app offer to restore rather than
crash.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime

from . import config

KEEP = 30


def backup_now(reason: str = "change") -> None:
    """Copy the live database to a timestamped file, then prune old ones."""
    src = config.db_path()
    if not src.exists():
        return  # nothing to back up yet (first ever write)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    dst = config.backups_dir() / f"gsd_{stamp}.db"
    shutil.copy2(src, dst)
    _prune()


def _prune() -> None:
    backups = sorted(config.backups_dir().glob("gsd_*.db"))
    for old in backups[:-KEEP]:
        try:
            old.unlink()
        except OSError:
            pass


def latest_backup():
    backups = sorted(config.backups_dir().glob("gsd_*.db"))
    return backups[-1] if backups else None


def _label(name: str) -> str:
    """gsd_20260620_153915_768.db -> '20 Jun 2026, 3:39 pm'."""
    m = re.search(r"(\d{8})_(\d{6})", name)
    if m:
        try:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return dt.strftime("%d %b %Y, %I:%M %p")
        except ValueError:
            pass
    return name


def list_backups() -> list[dict]:
    """Newest-first list of on-disk backups for the restore dropdown."""
    out = []
    for f in sorted(config.backups_dir().glob("gsd_*.db"), reverse=True):
        out.append({"name": f.name, "label": _label(f.name),
                    "size_kb": round(f.stat().st_size / 1024, 1)})
    return out


def _is_sqlite(path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(16).startswith(b"SQLite format 3")
    except OSError:
        return False


def restore_latest() -> bool:
    """Restore the most recent backup over the live database."""
    latest = latest_backup()
    return restore_file(latest) if latest else False


def restore_named(name: str) -> bool:
    """Restore a specific on-disk backup chosen by filename (no path traversal)."""
    if name not in {b["name"] for b in list_backups()}:
        return False
    return restore_file(config.backups_dir() / name)


def restore_file(path) -> bool:
    """Restore from any SQLite database file (e.g. an offsite copy). Backs up
    the current database first so a wrong restore is itself recoverable."""
    if not path or not _is_sqlite(path):
        return False
    backup_now("Before restore")
    shutil.copy2(path, config.db_path())
    return True
