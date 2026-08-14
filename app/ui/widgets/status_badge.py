"""Status badge widget: a colored pill with the status text always visible.

Supports room statuses, booking statuses and payment statuses.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.core.constants import (
    BookingStatus,
    PaymentStatus,
    RoomStatus,
)
from app.ui.styles import status_badge_stylesheet


def _label_for(status: str) -> str:
    try:
        return RoomStatus(status).label
    except ValueError:
        pass
    try:
        return BookingStatus(status).label
    except ValueError:
        pass
    try:
        return PaymentStatus(status).label
    except ValueError:
        return str(status)


def make_status_badge(status: str, compact: bool = False) -> QLabel:
    badge = QLabel(_label_for(status))
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setStyleSheet(status_badge_stylesheet(status, compact=compact))
    return badge
