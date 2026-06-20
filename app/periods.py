"""Business-summary period presets and NZ GST period maths (req 6 / 7).

GST frequency drives the 'This GST period' preset:
- 'monthly'  : the current calendar month.
- '2 months' : Apr-May, Jun-Jul, Aug-Sep, Oct-Nov, Dec-Jan, Feb-Mar.
- '6 monthly': Apr-Sep, Oct-Mar.
'This year' is the NZ income-tax year, 1 April - 31 March.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

# (key, label) for the dropdown. Order matters for display.
PRESETS = [
    ("last-7", "Last 7 days"),
    ("month-to-date", "Month to date"),
    ("last-30", "Last 30 days"),
    ("this-gst-period", "This GST period"),
    ("this-year", "This year (1 Apr–31 Mar)"),
    ("all-of-time", "All of time"),
]
PRESET_KEYS = {k for k, _ in PRESETS}


def _eom(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def gst_period(today: date, frequency: str) -> tuple[date, date]:
    m, y = today.month, today.year
    if frequency == "monthly":
        return date(y, m, 1), _eom(y, m)

    if frequency == "6 monthly":
        if 4 <= m <= 9:
            return date(y, 4, 1), _eom(y, 9)
        if m >= 10:
            return date(y, 10, 1), _eom(y + 1, 3)
        return date(y - 1, 10, 1), _eom(y, 3)  # Jan-Mar

    # default: 2 months
    pairs = [(4, 5), (6, 7), (8, 9), (10, 11), (12, 1), (2, 3)]
    for a, b in pairs:
        if m in (a, b):
            if (a, b) == (12, 1):
                start_year = y if m == 12 else y - 1
                return date(start_year, 12, 1), _eom(start_year + 1, 1)
            return date(y, a, 1), _eom(y, b)
    return date(y, m, 1), _eom(y, m)  # safety fallback


def tax_year(today: date) -> tuple[date, date]:
    """NZ income-tax year containing today: 1 Apr - 31 Mar."""
    if today.month >= 4:
        return date(today.year, 4, 1), date(today.year + 1, 3, 31)
    return date(today.year - 1, 4, 1), date(today.year, 3, 31)


def resolve(preset: str, today: date, gst_frequency: str) -> tuple[str, str]:
    """Return (from_iso, to_iso) for a preset key."""
    if preset == "last-7":
        return (today - timedelta(days=6)).isoformat(), today.isoformat()
    if preset == "last-30":
        return (today - timedelta(days=29)).isoformat(), today.isoformat()
    if preset == "this-gst-period":
        s, e = gst_period(today, gst_frequency)
        return s.isoformat(), e.isoformat()
    if preset == "this-year":
        s, e = tax_year(today)
        return s.isoformat(), e.isoformat()
    if preset == "all-of-time":
        return "1900-01-01", today.isoformat()
    # month-to-date (default)
    return date(today.year, today.month, 1).isoformat(), today.isoformat()
