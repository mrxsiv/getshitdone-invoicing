"""Start the invoicing app and open it in the default browser.

Double-clicking the desktop icon runs this (via pythonw, so no console window).
If the app is already running, this just reopens the browser tab instead of
starting a second copy (brief 3.1). On first run, if anything the app needs is
missing, a small setup page offers to install it (req 2).
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

# When frozen by PyInstaller, the Chromium browser used for PDF generation is
# shipped alongside the .exe (the installer puts it in <installdir>\browsers).
if getattr(sys, "frozen", False):
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH", str(Path(sys.executable).parent / "browsers"))

HOST = "127.0.0.1"
PORT = 5000
URL = f"http://localhost:{PORT}/"


def _already_running() -> bool:
    """True if something is already listening on our port (our own instance)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((HOST, PORT)) == 0


def _start_app() -> None:
    from waitress import serve

    from app import create_app

    application = create_app()
    threading.Timer(1.0, lambda: webbrowser.open(URL)).start()
    serve(application, host=HOST, port=PORT, threads=8)


def main() -> None:
    if _already_running():
        webbrowser.open(URL)
        return

    # First-run dependency check (stdlib only, so it works before installs).
    import setup_check

    missing = setup_check.check_dependencies()
    if missing:
        if not setup_check.serve_setup(missing, HOST, PORT, URL):
            return  # user closed the setup page without installing

    _start_app()


if __name__ == "__main__":
    main()
