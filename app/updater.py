"""Check GitHub Releases for a newer version and (on request) apply it.

Uses the public GitHub Releases API over HTTPS (no extra tools needed). The
check runs only when the Settings page loads or the button is clicked - never
constantly. Applying an update downloads the release's installer asset and runs
it; the installer updates the program in place and leaves the data folder alone.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request

from . import db, version

_API = "https://api.github.com/repos/{repo}/releases/latest"


def repo() -> str:
    return (db.get_setting("update_repo", "") or version.DEFAULT_UPDATE_REPO).strip()


def _parts(tag: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", tag or "")
    return tuple(int(n) for n in nums) or (0,)


def check(timeout: float = 6.0) -> dict:
    """Return {status, current, latest, message, url, asset}.
    status: unconfigured | error | current | update."""
    r = repo()
    current = version.VERSION
    if not r:
        return {"status": "unconfigured", "current": current,
                "message": "No update source is configured yet."}
    try:
        req = urllib.request.Request(
            _API.format(repo=r),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GSD-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return {"status": "error", "current": current,
                "message": "Couldn't reach GitHub. Check your internet connection."}

    tag = data.get("tag_name") or ""
    asset = None
    for a in (data.get("assets") or []):
        if (a.get("name") or "").lower().endswith(".exe"):
            asset = a.get("browser_download_url")
            break

    if _parts(tag) > _parts(current):
        return {"status": "update", "current": current, "latest": tag,
                "url": data.get("html_url"), "asset": asset,
                "message": f"Update available: {tag} (you have {current})."}
    return {"status": "current", "current": current, "latest": tag or current,
            "message": f"You're on the latest version ({current})."}


# ---- Background download with progress (so the UI can show a bar) ----

_dl = {"status": "idle", "downloaded": 0, "total": 0, "error": None}
_dl_lock = threading.Lock()


def download_state() -> dict:
    with _dl_lock:
        s = dict(_dl)
    s["pct"] = int(s["downloaded"] * 100 / s["total"]) if s["total"] else 0
    s["downloaded_mb"] = round(s["downloaded"] / 1048576, 1)
    s["total_mb"] = round(s["total"] / 1048576, 1)
    return s


def start_download() -> dict:
    """Begin downloading the latest installer in the background (non-blocking)."""
    with _dl_lock:
        if _dl["status"] in ("downloading", "launching"):
            return {"status": _dl["status"]}
        _dl.update(status="downloading", downloaded=0, total=0, error=None)
    threading.Thread(target=_download_worker, daemon=True).start()
    return {"status": "downloading"}


def _download_worker() -> None:
    try:
        info = check()
        if info.get("status") != "update" or not info.get("asset"):
            with _dl_lock:
                _dl.update(status="error", error="No update is available to download.")
            return
        dest = os.path.join(tempfile.gettempdir(), "GSD_update_setup.exe")
        req = urllib.request.Request(info["asset"], headers={"User-Agent": "GSD-Updater"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            with _dl_lock:
                _dl["total"] = total
            done = 0
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                with _dl_lock:
                    _dl["downloaded"] = done
        with _dl_lock:
            _dl.update(status="launching")
        subprocess.Popen([dest])              # installer runs (UAC will prompt)
        # Give the browser a moment to show the "installer opening" message, then
        # quit so the running .exe doesn't lock the files the installer replaces.
        threading.Timer(4.0, lambda: os._exit(0)).start()
    except Exception:
        with _dl_lock:
            _dl.update(status="error", error="The update could not be downloaded.")
