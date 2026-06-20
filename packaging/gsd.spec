# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for GET SHIT DONE (onedir, no console).

Build:  python -m PyInstaller packaging/gsd.spec --noconfirm
Result: dist/GETSHITDONE/GETSHITDONE.exe  (+ _internal). The Chromium browser
used for PDF output is shipped separately by the installer into
<installdir>/browsers (see packaging/build.ps1 + installer.iss).
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)  # project root (parent of packaging/)


def p(*parts):
    return os.path.join(ROOT, *parts)


datas = [
    (p("app", "web", "templates"), "app/web/templates"),
    (p("app", "web", "static"), "app/web/static"),
    (p("templates", "invoice_template.html"), "templates"),
    (p("requirements.txt"), "."),
]
datas += collect_data_files("playwright")   # the playwright driver

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("waitress")
    + ["PIL", "PIL.Image", "openpyxl", "playwright", "playwright.sync_api"]
)

a = Analysis(
    [p("run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="GETSHITDONE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,            # no console window (brief 3.1)
    icon=os.path.join(SPECPATH, "GSD.ico"),
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="GETSHITDONE",
)
