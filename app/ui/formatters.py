"""Small display formatters shared across the UI."""

from __future__ import annotations

from datetime import date, datetime, time as dtime

from app.core.constants import DEFAULT_CURRENCY
from app.services.money import to_decimal


def _indian_grouping(digits: str) -> str:
    """Group a plain digit string using Indian numbering (12,34,567)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups + [tail])


def format_money(value) -> str:  # noqa: ANN001
    """Format an amount in rupees with Indian digit grouping (₹1,82,500.00)."""
    amount = to_decimal(value)
    sign = "-" if amount < 0 else ""
    text = f"{abs(amount):.2f}"
    whole, frac = text.split(".")
    return f"{sign}{DEFAULT_CURRENCY}{_indian_grouping(whole)}.{frac}"


def format_date(day: date | None) -> str:
    return day.strftime("%d %b %Y") if day else "—"


def format_time(t: dtime | None) -> str:
    return t.strftime("%I:%M %p") if t else "—"


def format_datetime(value: datetime | None) -> str:
    return value.strftime("%d %b %Y, %I:%M %p") if value else "—"


def format_date_time(day: date | None, t: dtime | None) -> str:
    if day is None:
        return "—"
    if t is None:
        return format_date(day)
    return f"{format_date(day)} {format_time(t)}"


def mask_id_number(value: str | None) -> str:
    """Mask a guest ID document number, keeping the last four digits.

    Displaying full identity documents on screen is a privacy risk.
    ``Aadhaar 1234 5678 9012`` → ``XXXX XXXX 9012``. Short values are
    returned with all but the last character masked.
    """
    if not value:
        return "—"
    compact = "".join(ch for ch in value if ch.isalnum())
    if not compact:
        return "—"
    if len(compact) <= 4:
        return "X" * (len(compact) - 1) + compact[-1]
    return "X" * (len(compact) - 4) + " " + compact[-4:]
