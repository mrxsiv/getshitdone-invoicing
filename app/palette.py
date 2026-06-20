"""Configurable colour palette that flows through every page (req 9).

Named colours are stored in settings as hex values and injected as CSS variables
on top of the base stylesheet. Text colour on coloured backgrounds (e.g. the
primary button, the TAX INVOICE box) is chosen automatically for readability,
and Backend Config can warn when two key colours are too similar to tell apart.
"""
from __future__ import annotations

# Editable colours, with friendly labels and sensible defaults.
COLOURS = [
    ("color_brand", "Brand / primary (red)", "#c0202a"),
    ("color_brand_dark", "Brand dark (hover)", "#8a1620"),
    ("color_paid", "Paid / success (green)", "#1a7f37"),
    ("color_overdue", "Overdue / warning", "#b3261e"),
    ("color_sales", "Trend: sales line", "#e0424c"),
    ("color_labour", "Trend: labour line", "#2e9e5b"),
    ("color_volume", "Trend: volume line", "#3b7dd8"),
]
DEFAULTS = {key: default for key, _label, default in COLOURS}

# Surface colours per theme (not user-editable; the light/dark toggle owns them).
_SURFACE = {
    "light": {"bg": "#f5f6f8", "panel": "#ffffff"},
    "dark": {"bg": "#16181d", "panel": "#20242b"},
}


def _rgb(hex_str: str) -> tuple[int, int, int]:
    h = (hex_str or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


def _hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in rgb))


def _rel_lum(hex_str: str) -> float:
    def chan(c):
        c /= 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(hex_str)
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _rel_lum(a), _rel_lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def on_color(bg: str) -> str:
    """Readable text colour (near-black or white) for a coloured background."""
    return "#ffffff" if contrast_ratio(bg, "#ffffff") >= contrast_ratio(bg, "#1c1c1c") else "#1c1c1c"


def mix(a: str, b: str, t: float) -> str:
    """Blend: t of colour a, (1-t) of colour b."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(ra[i] * t + rb[i] * (1 - t) for i in range(3)))


def get(settings: dict, key: str) -> str:
    return settings.get(key) or DEFAULTS[key]


def css(settings: dict, theme: str) -> str:
    """Generate the :root override block for the active theme."""
    theme = "dark" if theme == "dark" else "light"
    surface = _SURFACE[theme]
    panel = surface["panel"]

    brand = get(settings, "color_brand")
    brand_dk = get(settings, "color_brand_dark")
    paid = get(settings, "color_paid")
    overdue = get(settings, "color_overdue")

    vars_ = {
        "--brand": brand,
        "--brand-dk": brand_dk,
        "--on-brand": on_color(brand),
        "--on-paid": on_color(paid),
        "--ok": paid,
        "--warn": overdue,
        "--ok-bg": mix(paid, panel, 0.16),
        "--warn-bg": mix(overdue, panel, 0.16),
        "--chart-sales": get(settings, "color_sales"),
        "--chart-labour": get(settings, "color_labour"),
        "--chart-volume": get(settings, "color_volume"),
    }
    body = ";".join(f"{k}:{v}" for k, v in vars_.items())
    return ":root{" + body + "}"


def warnings(settings: dict, theme: str) -> list[str]:
    """Human-readable readability warnings for Backend Config."""
    theme = "dark" if theme == "dark" else "light"
    bg = _SURFACE[theme]["bg"]
    panel = _SURFACE[theme]["panel"]
    out = []
    checks = [
        ("Brand", get(settings, "color_brand")),
        ("Paid", get(settings, "color_paid")),
        ("Overdue", get(settings, "color_overdue")),
        ("Sales line", get(settings, "color_sales")),
        ("Labour line", get(settings, "color_labour")),
        ("Volume line", get(settings, "color_volume")),
    ]
    for name, hexv in checks:
        if contrast_ratio(hexv, panel) < 1.6 and contrast_ratio(hexv, bg) < 1.6:
            out.append(f"{name} colour is very close to the {theme} background and may be hard to see.")
    return out
