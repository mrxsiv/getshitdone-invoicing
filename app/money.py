"""Money maths and formatting (brief 9 - be exact).

Unit prices are GST-exclusive. Subtotal is the GST-exclusive sum of line items;
GST = Subtotal x rate; Amount Payable = Subtotal + GST. Components are rounded to
two decimal places first, then Amount Payable is the sum of those displayed
figures so the printed numbers always add up.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

TWO = Decimal("0.01")


def _d(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def q2(value) -> Decimal:
    """Round to 2 decimal places, standard (half-up) rounding."""
    return _d(value).quantize(TWO, rounding=ROUND_HALF_UP)


def line_total(quantity, unit_price) -> Decimal:
    return q2(_d(quantity) * _d(unit_price))


def totals(line_totals, gst_rate=15) -> dict[str, Decimal]:
    """Subtotal / GST / Amount Payable from a list of (already 2dp) line totals."""
    subtotal = q2(sum((_d(lt) for lt in line_totals), Decimal("0")))
    gst = q2(subtotal * _d(gst_rate) / Decimal("100"))
    amount = q2(subtotal + gst)
    return {"subtotal": subtotal, "gst": gst, "amount_payable": amount}


def money(value) -> str:
    """Format as NZ dollars with a $ sign and thousands separators."""
    return "${:,.2f}".format(q2(value))


def to_float(value) -> float:
    """Store-ready float, rounded to 2dp."""
    return float(q2(value))
