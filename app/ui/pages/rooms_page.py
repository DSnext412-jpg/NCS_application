"""Rooms status board page.

A reception-facing overview of every room: status, current occupant and
stay dates. Clicking a room opens the room details dialog with context
actions (view the active booking, walk-in check-in).
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import RoomStatus
from app.database.database import Database
from app.services import booking_service, room_service
from app.ui.dialogs.room_details_dialog import RoomDetailsDialog
from app.ui.formatters import format_date_time
from app.ui.widgets.flow_layout import FlowLayout
from app.ui.widgets.room_card import RoomCard
from app.ui.widgets.summary_card import SummaryCard

_TYPE_FILTERS = (("all", "All Rooms"), ("AC", "AC"), ("Non-AC", "Non-AC"))
_STATUS_FILTERS = (("all", "All Status"),) + tuple(
    (status.value, status.label) for status in RoomStatus
)


class RoomsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.rooms: list = []
        self.occupants: dict[int, object] = {}
        self.type_filter = "all"
        self.status_filter = "all"
        self.search_text = ""
        self.availability_mode = False
        self.availability: dict[int, tuple[bool, object]] = {}

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Rooms")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("Live room availability and status. Pick dates to see free rooms.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self.cards = {
            "total": SummaryCard("Total Rooms", icon="🏨", accent="reserved"),
            "vacant": SummaryCard("Available", icon="✅", accent="vacant"),
            "occupied": SummaryCard("Occupied", icon="🛏️", accent="occupied"),
            "reserved": SummaryCard("Reserved", icon="📅", accent="reserved"),
            "cleaning": SummaryCard("Cleaning", icon="🧹", accent="cleaning"),
        }
        for card in self.cards.values():
            card.setMinimumWidth(130)
            card.setMinimumHeight(92)
            summary_row.addWidget(card, 1)
        root.addLayout(summary_row)

        # Availability bar: dates + legend.
        self.avail_bar = QWidget()
        avail_layout = QHBoxLayout(self.avail_bar)
        avail_layout.setContentsMargins(0, 0, 0, 0)
        avail_layout.setSpacing(8)
        avail_label = QLabel("Check availability:")
        avail_label.setProperty("detailLabel", True)
        avail_layout.addWidget(avail_label)
        self.check_in_edit = QDateEdit(QDate.currentDate())
        self.check_in_edit.setCalendarPopup(True)
        self.check_in_edit.setDisplayFormat("dd-MM-yyyy")
        avail_layout.addWidget(self.check_in_edit)
        avail_layout.addWidget(self._legend_dot("→"))
        self.check_out_edit = QDateEdit(QDate.currentDate().addDays(1))
        self.check_out_edit.setCalendarPopup(True)
        self.check_out_edit.setDisplayFormat("dd-MM-yyyy")
        avail_layout.addWidget(self.check_out_edit)
        self.apply_button = QPushButton("Show Free Rooms")
        self.apply_button.setObjectName("ActionButton")
        self.apply_button.clicked.connect(self._on_apply_availability)
        avail_layout.addWidget(self.apply_button)
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("SecondaryButton")
        self.clear_button.clicked.connect(self._on_clear_availability)
        avail_layout.addWidget(self.clear_button)
        avail_layout.addSpacing(18)
        avail_layout.addWidget(self._legend_dot("green", "Free"))
        avail_layout.addWidget(self._legend_dot("red", "Blocked"))
        avail_layout.addStretch(1)
        root.addWidget(self.avail_bar)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search room number...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit)
        search_row.addStretch(1)
        root.addLayout(search_row)

        self.type_group = QButtonGroup(self)
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        for key, label in _TYPE_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("filter_type", key)
            button.clicked.connect(self._on_type_filter)
            self.type_group.addButton(button)
            type_row.addWidget(button)
        type_row.addStretch(1)
        root.addLayout(type_row)

        self.status_group = QButtonGroup(self)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        for key, label in _STATUS_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("filter_status", key)
            button.clicked.connect(self._on_status_filter)
            self.status_group.addButton(button)
            status_row.addWidget(button)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self.grid_container = QWidget()
        self.grid = FlowLayout(self.grid_container, margin=0, h_spacing=14, v_spacing=14)
        self.grid_container.setLayout(self.grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self.grid_container)
        root.addWidget(scroll, 1)

    # ------------------------------------------------------------ filters

    def _legend_dot(self, color: str, text: str = "") -> QWidget:
        dot_color = "#16A34A" if color == "green" else "#DC2626"
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 16px;")
        label = QLabel(text)
        label.setStyleSheet("color: #334155; font-weight: 600;")
        wrapper = QHBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(4)
        wrapper.addWidget(dot)
        wrapper.addWidget(label)
        container = QWidget()
        container.setLayout(wrapper)
        return container

    def _on_apply_availability(self) -> None:
        check_in = self.check_in_edit.date().toPython()
        check_out = self.check_out_edit.date().toPython()
        if check_out <= check_in:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Invalid Dates", "Check-out must be after check-in.")
            return
        check_in_time = None
        check_out_time = None
        room_ids = [room.id for room in self.rooms]
        with self.database.session_scope() as session:
            self.availability = booking_service.check_rooms_availability(
                session,
                room_ids,
                check_in,
                check_in_time,
                check_out,
                check_out_time,
            )
        for room in self.rooms:
            if room.status == RoomStatus.MAINTENANCE.value:
                self.availability[room.id] = (False, None)
        self.availability_mode = True
        self.status_filter = "all"
        for button in self.status_group.buttons():
            button.setChecked(button.property("filter_status") == "all")
        self._render_grid()

    def _on_clear_availability(self) -> None:
        self.availability_mode = False
        self.availability = {}
        self._render_grid()

    def _on_type_filter(self) -> None:
        button = self.sender()
        if button is not None and button.isChecked():
            self.type_filter = button.property("filter_type")
        self._render_grid()

    def _on_status_filter(self) -> None:
        button = self.sender()
        if button is not None and button.isChecked():
            self.status_filter = button.property("filter_status")
        self._render_grid()

    def _on_search_changed(self, text: str) -> None:
        self.search_text = text.strip()
        self._render_grid()

    # --------------------------------------------------------------- data

    def refresh(self) -> None:
        with self.database.session_scope() as session:
            self.rooms = room_service.get_all_rooms(session)
            self.counts = room_service.get_room_status_counts(session)
            self.occupants = {}
            for room in self.rooms:
                booking = booking_service.get_active_booking_for_room(session, room.id)
                self.occupants[room.id] = booking
        self._render_cards()
        self._render_grid()

    def _render_cards(self) -> None:
        subtexts = {
            "total": "All rooms in property",
            "vacant": "Ready for check-in",
            "occupied": "Currently occupied",
            "reserved": "Upcoming bookings",
            "cleaning": "Awaiting cleaning",
        }
        for key, card in self.cards.items():
            card.set_value(self.counts.get(key, 0))
            card.set_subtext(subtexts.get(key, ""))

    def _filtered_rooms(self) -> list:
        rooms = self.rooms
        if self.type_filter != "all":
            rooms = [room for room in rooms if room.room_type == self.type_filter]
        if self.status_filter != "all":
            rooms = [room for room in rooms if room.status == self.status_filter]
        if self.search_text:
            needle = self.search_text.lower()
            rooms = [room for room in rooms if needle in room.room_number.lower()]
        return rooms

    def _render_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for room in self._filtered_rooms():
            booking = self.occupants.get(room.id)
            occupant = detail = None
            if booking is not None and booking.guest is not None:
                occupant = booking.guest.guest_name
                detail = f"{format_date_time(booking.check_in_date, booking.check_in_time)} → {format_date_time(booking.check_out_date, booking.check_out_time)}"
            avail, blocker = self.availability.get(room.id, (None, None)) if self.availability_mode else (None, None)
            card = RoomCard(
                room,
                occupant=occupant,
                detail=detail,
                available=avail,
                blocked_by=blocker.booking_number if blocker is not None else None,
            )
            card.clicked.connect(self._open_room_details)
            self.grid.addWidget(card)

        self.grid_container.adjustSize()

    # ------------------------------------------------------- room details

    def _open_room_details(self, room_id: int) -> None:
        dialog = RoomDetailsDialog(
            self.database,
            room_id,
            on_changed=self.refresh,
            parent=self,
        )
        dialog.exec()
        self.refresh()
