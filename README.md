# GET SHIT DONE

A simple, offline invoicing app for small businesses — *an invoicing app for people who don't have time for bullshit.*

It runs as a tiny local web app in your browser. Everything stays on your own PC: a single SQLite database, invoice PDFs, and one-click Excel exports. No accounts, no cloud, no telemetry.

## Features

- **Clients** — searchable, sortable, paged contact list.
- **Invoices** — keyboard-friendly line-item entry with live GST totals, PDF generation, print, and a pre-filled Gmail compose hand-off.
- **Cash sale** — one click to save, mark paid, and print.
- **Outstanding** — sortable list of unpaid invoices with an undoable "paid" tick and overdue highlighting.
- **Dashboard** — business summary (Labour / Parts / Other) over selectable periods, plus a 13-month trend chart.
- **GST aware** — handles registered and non-registered businesses; configurable rate and filing frequency.
- **Editable invoice template** (HTML/CSS) and a fully configurable colour palette.
- **Backups** before every change; Excel export; backend config page.
- **Check for updates** built in (pulls the latest GitHub release).

## Install

Download the latest `GETSHITDONE-Setup-x.xx.exe` from [Releases](../../releases) and run it.

- Installs to `C:\GSD` by default (changeable).
- Data is stored in `C:\GSD\data` by default — point this at a **Google Drive** or **OneDrive** folder during install to back it up to the cloud.
- Optional Desktop / Start Menu / Taskbar shortcuts.

Your data folder is independent of the program, so updates never touch it.

## First run

The app opens with sample business details — set your own in **Settings** (business name, GST number, bank details). Replace the logo in **Settings → Backend Config**.

## Building from source

Requires Python 3.13, [Inno Setup 6](https://jrsoftware.org/isdl.php), and these one-time steps:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

The installer is written to `packaging\Output\`.

## Licence

MIT — see [LICENSE](LICENSE).
