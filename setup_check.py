"""First-run dependency check for the launcher (req 2).

Runs BEFORE the main app is imported, so it must rely only on the Python
standard library (the very thing it checks for might be missing). If anything
the app needs is absent, it serves a small setup page that lists what's missing
with a one-click "Install" button (which fetches the components from the web),
then hands off to the real app.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
REQ_FILE = os.path.join(HERE, "requirements.txt")

# Python packages the app needs, with friendly labels for a non-technical user.
REQUIRED_PACKAGES = [
    ("flask", "Application engine"),
    ("waitress", "Application engine"),
    ("openpyxl", "Excel export component"),
    ("playwright", "PDF engine"),
]


def _chromium_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return True  # playwright package missing is already reported separately
    try:
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:
        return False


def check_dependencies() -> list[dict]:
    """Return a de-duplicated list of {label} for everything that's missing."""
    missing: list[dict] = []
    seen: set[str] = set()
    for module, label in REQUIRED_PACKAGES:
        if importlib.util.find_spec(module) is None and label not in seen:
            missing.append({"label": label})
            seen.add(label)
    if not _chromium_ok():
        label = "PDF engine (browser component)"
        if label not in seen:
            missing.append({"label": label})
    return missing


def install_missing():
    """Install required packages and the Chromium browser. Returns (ok, log)."""
    log: list[str] = []
    steps = [
        ([sys.executable, "-m", "pip", "install", "-r", REQ_FILE], "Downloading and installing components"),
        ([sys.executable, "-m", "playwright", "install", "chromium"], "Installing the PDF engine"),
    ]
    for cmd, desc in steps:
        log.append("== " + desc + " ==")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=HERE)
            if r.stdout:
                log.append(r.stdout[-1500:])
            if r.returncode != 0:
                log.append(r.stderr[-1500:])
                return False, "\n".join(log)
        except Exception as e:  # pragma: no cover - defensive
            log.append(str(e))
            return False, "\n".join(log)
    return True, "\n".join(log)


# ---- Tiny setup web page (stdlib only) -------------------------------------

_STYLE = """
  body{font-family:'Segoe UI',Arial,sans-serif;background:#16181d;color:#e8eaed;
       margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}
  .box{background:#20242b;border:1px solid #333944;border-radius:12px;max-width:560px;
       padding:30px 34px;box-shadow:0 4px 20px rgba(0,0,0,.4)}
  h1{color:#f0555f;margin:0 0 6px;font-size:22px}
  p{color:#9aa0a6;line-height:1.5}
  ul{line-height:1.9} li{color:#e8eaed}
  .btn{display:inline-block;background:#c0202a;color:#fff;border:none;border-radius:8px;
       padding:12px 22px;font-size:16px;font-weight:600;cursor:pointer;text-decoration:none}
  .btn:hover{background:#8a1620}
  pre{background:#16181d;border:1px solid #333944;border-radius:8px;padding:12px;
      max-height:240px;overflow:auto;font-size:12px;color:#9aa0a6;white-space:pre-wrap}
"""


def _page(body: str) -> bytes:
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Setup</title>"
            "<style>" + _STYLE + "</style></head><body><div class='box'>" + body +
            "</div></body></html>").encode("utf-8")


def serve_setup(missing: list[dict], host: str, port: int, url: str) -> bool:
    """Serve the setup page until the user installs and chooses to start.
    Returns True if the app should now launch."""
    state = {"launch": False}

    items = "".join("<li>" + m["label"] + "</li>" for m in missing)
    intro = _page(
        "<h1>One quick setup step</h1>"
        "<p>Before the invoicing app can open, these components need to be installed "
        "(this needs an internet connection and happens once):</p>"
        "<ul>" + items + "</ul>"
        "<form method='post' action='/install'>"
        "<button class='btn' type='submit'>Install now</button></form>")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the console quiet
            pass

        def _send(self, html: bytes, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)

        def do_GET(self):
            if self.path.startswith("/launch"):
                state["launch"] = True
                self._send(_page("<h1>Starting&hellip;</h1>"
                                 "<p>The app is starting. This page will open in a moment.</p>"
                                 "<script>setTimeout(function(){location.href='" + url + "'},3500)</script>"))
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send(intro)

        def do_POST(self):
            if self.path.startswith("/install"):
                ok, log = install_missing()
                if ok:
                    body = ("<h1>All set</h1><p>Everything is installed. "
                            "Click below to open the app.</p>"
                            "<a class='btn' href='/launch'>Start the app</a>")
                else:
                    body = ("<h1>That didn't finish</h1>"
                            "<p>Something went wrong during install. Please check your "
                            "internet connection and try again.</p>"
                            "<form method='post' action='/install'>"
                            "<button class='btn' type='submit'>Try again</button></form>"
                            "<pre>" + log.replace("<", "&lt;") + "</pre>")
                self._send(_page(body))
            else:
                self._send(intro, 404)

    httpd = ThreadingHTTPServer((host, port), Handler)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return state["launch"]
