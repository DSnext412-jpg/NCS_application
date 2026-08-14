"""Clickable room card for the reception dashboard and rooms page."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.core.constants import RoomStatus
from app.database.models import Room
from app.ui.widgets.status_badge import make_status_badge


class RoomCard(QFrame):
    clicked = Signal(int)

    def __init__(
        self,
        room: Room,
        occupant: str | None = None,
        detail: str | None = None,
        available: bool | None = None,
        blocked_by: str | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.room_id = room.id
        self.room_number = room.room_number

        self.setObjectName("RoomCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(184, 134)
        self.setToolTip(f"Room {room.room_number} — {self._status_text(room.status)}")

        if available is not None:
            self.setProperty("availability", "free" if available else "blocked")
            self.setProperty("class", "AvailabilityRoomCard")
            self.style().unpolish(self)
            self.style().polish(self)
            self.setToolTip(
                f"Room {room.room_number} — {'Available' if available else f'Blocked: {blocked_by or "busy"}'}"
            )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)

        # Top row: "ROOM" at top-left + status badge top-right.
        top = QHBoxLayout()
        top.setSpacing(8)
        prefix_label = QLabel("ROOM")
        prefix_label.setProperty("roomNumberPrefix", True)
        top.addWidget(prefix_label)
        top.addStretch(1)
        if available is not None:
            badge = QLabel("FREE" if available else "BLOCKED")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                "background: #16A34A; color: #FFFFFF; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700;"
                if available
                else "background: #DC2626; color: #FFFFFF; border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700;"
            )
            top.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        else:
            badge = make_status_badge(room.status, compact=True)
            top.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        # Room number row, centered across the full card width.
        number_row = QHBoxLayout()
        number_row.setSpacing(2)
        number_label = QLabel(room.room_number)
        number_label.setProperty("roomNumber", True)
        number_row.addStretch(1)
        number_row.addWidget(number_label)
        number_row.addStretch(1)
        layout.addLayout(number_row)

        # Guest first name, centered directly below the room number.
        if occupant:
            first_name = occupant.split()[0] if occupant.split() else occupant
            guest_row = QHBoxLayout()
            guest_label = QLabel(first_name)
            guest_label.setProperty("roomGuestName", True)
            guest_label.setToolTip(occupant)
            guest_row.addStretch(1)
            guest_row.addWidget(guest_label)
            guest_row.addStretch(1)
            layout.addLayout(guest_row)

        layout.addStretch(1)

        if detail:
            detail_label = QLabel(detail)
            detail_label.setProperty("roomOccupantDetail", True)
            detail_label.setToolTip(detail)
            layout.addWidget(detail_label)

        type_label = QLabel(room.room_type)
        type_label.setProperty("roomType", True)
        type_row = QHBoxLayout()
        type_row.addWidget(type_label)
        type_row.addStretch(1)
        layout.addLayout(type_row)

    @staticmethod
    def _status_text(status: str) -> str:
        try:
            return RoomStatus(status).label
        except ValueError:
            return str(status)

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.room_id)
        super().mousePressEvent(event)