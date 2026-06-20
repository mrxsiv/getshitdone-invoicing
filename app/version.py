"""Single source of truth for the app version.

Bump VERSION (and PUBLICATION_DATE) when cutting a new GitHub release; the
"Check for updates" feature compares this against the latest release tag, and
the sidebar + Backend Config show it. Kept in code (not a DB setting) so an
update automatically reports the new version.
"""
from __future__ import annotations

VERSION = "1.00"
PUBLICATION_DATE = "20 Jun 2026"

# GitHub repo to check for updates (owner/name). Overridable in Backend Config.
DEFAULT_UPDATE_REPO = "mrxsiv/getshitdone-invoicing"


def version_label() -> str:
    return f"Version {VERSION} - {PUBLICATION_DATE}"
