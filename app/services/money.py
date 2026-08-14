"""Money helpers.

Money is always handled as ``Decimal`` to avoid floating-point errors.
The booking model stores amounts in ``Numeric(10, 2)`` columns, which
SQLAlchemy returns as ``Decimal`` — this module is the single source of
truth for converting, rounding and adding money.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

_CENTS = Decimal("0.01")
_ZERO = Decimal("0")


def to_decimal(value: Any) -> Decimal:
    """Convert any reasonable input to a 2-decimal Decimal (never raises).

    ``None``, empty strings and invalid values become ``0``.
    """
    if value is None:
        return _ZERO
    if isinstance(value, Decimal):
        return value.quantize(_CENTS, rounding=ROUND_HALF_UP)
    try:
        text = str(value).strip().replace(",", "")
        if text in ("", "-", "NaN", "Infinity"):
            return _ZERO
        return Decimal(text).quantize(_CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, AttributeError):
        return _ZERO


def to_paise(value: Any) -> int:
    """Money as an integer count of paise (1/100 of a rupee).

    The deterministic integer form is useful for exact comparisons.
    """
    return int((to_decimal(value) * 100).to_integral_value())


def from_paise(paise: int) -> Decimal:
    """Reconstruct a Decimal from an integer paise count."""
    return (Decimal(int(paise)) / 100).quantize(_CENTS, rounding=ROUND_HALF_UP)


def add(*values: Any) -> Decimal:
    """Sum any number of money values."""
    total = _ZERO
    for value in values:
        total += to_decimal(value)
    return total.quantize(_CENTS, rounding=ROUND_HALF_UP)
