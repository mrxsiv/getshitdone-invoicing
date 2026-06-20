"""Timestamped database backups taken before every write (brief 3.2).

Keeps the most recent 30 backups in the hidden-ish `_backups` folder. On a
damaged database, `latest_backup()` lets the app offer to restore rather than
crash.
"""
from __future__ import annotations

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


def restore_latest() -> bool:
    """Restore the most recent backup over the live database."""
    latest = latest_backup()
    if not latest:
        return False
    shutil.copy2(latest, config.db_path())
    return True
