"""Where things live on disk, and first-run folder setup.

The app stores everything under one clearly named root folder (chosen at first
run; default Documents\\GET SHIT DONE). Because the database lives
*inside* that root, the root location itself is remembered in a tiny bootstrap
file in the user's AppData, not in the database.

For development/testing, set the environment variable INVOICING_ROOT to point
the whole app at a throwaway folder.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "GET SHIT DONE"

# Where bundled files live. When frozen by PyInstaller, data is unpacked to
# sys._MEIPASS; in development it's the project folder.
if getattr(sys, "frozen", False):
    PROJECT_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    PROJECT_DIR = Path(__file__).resolve().parent.parent

# Folder that ships with the app, holding the master invoice template + logo.
BUNDLED_TEMPLATES = PROJECT_DIR / "templates"

# Bundled historical data for the one-time go-live import (brief 15).
HISTORICAL_SOURCE = PROJECT_DIR / "Historical Import Source"

# Bootstrap file remembering where the user put their data folder.
_BOOTSTRAP = Path(os.environ.get("APPDATA", Path.home())) / "GetShitDone" / "location.json"

# Set when the user changes the data folder in Settings; takes effect for the
# rest of the running process (so the change is live without a relaunch).
_root_override: Path | None = None


def default_root() -> Path:
    return Path.home() / "Documents" / APP_NAME


def _install_root() -> Path | None:
    """Data path chosen at install time (a file the installer writes next to the
    .exe). Only used when frozen and the user hasn't changed it in the app."""
    if not getattr(sys, "frozen", False):
        return None
    f = Path(sys.executable).parent / "data_location.txt"
    if f.exists():
        try:
            value = f.read_text(encoding="utf-8").strip()
            if value:
                return Path(value)
        except OSError:
            pass
    return None


def get_root() -> Path:
    """Resolve the data root, most specific first:
    live override > env > the user's in-app choice > installer default > Documents."""
    if _root_override is not None:
        return _root_override
    env = os.environ.get("INVOICING_ROOT")
    if env:
        return Path(env)
    if _BOOTSTRAP.exists():
        try:
            saved = json.loads(_BOOTSTRAP.read_text(encoding="utf-8")).get("root")
            if saved:
                return Path(saved)
        except (ValueError, OSError):
            pass
    inst = _install_root()
    if inst:
        return inst
    return default_root()


def set_root(new_root: str | Path) -> Path:
    """Remember a new data-root location and use it for the rest of this run."""
    global _root_override
    root = Path(new_root)
    _BOOTSTRAP.parent.mkdir(parents=True, exist_ok=True)
    _BOOTSTRAP.write_text(json.dumps({"root": str(root)}), encoding="utf-8")
    _root_override = root
    return root


def relocate(new_root: str | Path, copy_existing: bool = True) -> Path:
    """Move the data folder to a new location chosen by the user (brief 7.6).

    Copies the current contents into the new folder (without overwriting files
    already there), then repoints the app. The original is left untouched so
    nothing can be lost; the user can delete it once happy.
    """
    new = Path(new_root)
    old = get_root()
    new.mkdir(parents=True, exist_ok=True)
    if copy_existing and old.exists() and old.resolve() != new.resolve():
        for item in old.iterdir():
            dest = new / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            elif not dest.exists():
                shutil.copy2(item, dest)
    set_root(new)
    ensure_structure()
    return new


# ---- Individual paths within the root ----

def data_dir() -> Path:        return get_root() / "data"
def db_path() -> Path:         return data_dir() / "gsd.db"
def templates_dir() -> Path:   return get_root() / "templates"
def invoices_dir() -> Path:    return get_root() / "Invoices"
def exports_dir() -> Path:     return get_root() / "exports"
def backups_dir() -> Path:     return get_root() / "_backups"
def invoice_template() -> Path: return templates_dir() / "invoice_template.html"


def ensure_structure() -> Path:
    """Create the folder layout on first run and seed the template + logo."""
    root = get_root()
    for d in (data_dir(), templates_dir(), invoices_dir(), exports_dir(), backups_dir()):
        d.mkdir(parents=True, exist_ok=True)

    _migrate_legacy_db()

    # Seed the editable template + logo from the bundled copies, but never
    # overwrite the user's own template once it exists (brief 3.3 / 8).
    _seed("invoice_template.html")
    _seed("logo.jpg")
    return root


def _migrate_legacy_db() -> None:
    """Early builds named the database 'hotrods.db'. If a data folder still has
    that file and no gsd.db yet, adopt it so the data loads after an update."""
    current = db_path()
    legacy = data_dir() / "hotrods.db"
    if legacy.exists() and not current.exists():
        try:
            legacy.rename(current)
        except OSError:
            pass


def _seed(filename: str) -> None:
    src = BUNDLED_TEMPLATES / filename
    dst = templates_dir() / filename
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
