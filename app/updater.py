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


def apply() -> dict:
    """Download the latest installer and launch it. Returns a status dict."""
    info = check()
    if info.get("status") != "update":
        return info
    asset = info.get("asset")
    if not asset:
        return {"status": "manual", "url": info.get("url"),
                "message": "An update exists but no installer was attached. "
                           "Please download it from the releases page."}
    try:
        dest = os.path.join(tempfile.gettempdir(), "GSD_update_setup.exe")
        urllib.request.urlretrieve(asset, dest)
        subprocess.Popen([dest])  # the installer updates the app in place
        return {"status": "updating",
                "message": "The updater is starting in a new window. Follow its "
                           "prompts, then reopen the app."}
    except Exception:
        return {"status": "error", "message": "The update could not be downloaded."}
