"""Live reception dashboard.

Shows real, database-backed room status: summary counts, a clickable room
grid with filters/search, quick actions (new booking, walk-in, check-in,
check-out) and a today's activity section. Refreshes are event-driven —
no polling loops.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import APP_NAME, BookingStatus, RoomStatus
from app.database.database import Database
from app.services import (
    analytics_service,
    booking_service,
    financial_service,
    room_service,
    settings_service,
)
from app.ui.dialogs.booking_details_dialog import BookingDetailsDialog
from app.ui.dialogs.room_details_dialog import RoomDetailsDialog
from app.ui.formatters import format_date_time, format_money
from app.ui.widgets.flow_layout import FlowLayout
from app.ui.widgets.room_card import RoomCard
from app.ui.widgets.summary_card import SummaryCard

QUICK_ACTIONS = (
    ("new_booking", "+ New Booking", "primary"),
    ("walkin", "Walk-in", "success"),
    ("checkin", "Check-in", "checkin"),
    ("checkout", "Check-out", "checkout"),
    ("payments", "Payments", "info"),
    ("invoices", "Invoices", "invoice"),
)
_TYPE_FILTERS = (("all", "All Rooms"), ("AC", "AC"), ("Non-AC", "Non-AC"))
_STATUS_FILTERS = (("all", "All Status"),) + tuple(
    (status.value, status.label) for status in RoomStatus
)

_ZERO_COUNTS = {
    "total": 0,
    "vacant": 0,
    "occupied": 0,
    "reserved": 0,
}


class ReceptionDashboardPage(QWidget):
    quick_action_requested = Signal(str)

    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.rooms: list = []
        self.counts: dict[str, int] = dict(_ZERO_COUNTS)
        self.room_occupants: dict[int, str] = {}
        self.type_filter = "all"
        self.status_filter = "all"
        self.search_text = ""

        self._build_ui()
        self._start_clock()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        # The whole page scrolls, so no section can ever be squeezed to an
        # unusable sliver on short screens.
        outer_scroll = QScrollArea()
        outer_scroll.setWidgetResizable(True)
        outer_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(10)

        outer_scroll.setWidget(content)
        page_root = QVBoxLayout(self)
        page_root.setContentsMargins(0, 0, 0, 0)
        page_root.addWidget(outer_scroll)

        # --- header: hotel name + date/time -------------------------------
        header = QHBoxLayout()
        self.hotel_name_label = QLabel(APP_NAME)
        self.hotel_name_label.setObjectName("HotelNameLabel")
        header.addWidget(self.hotel_name_label)

        header.addStretch(1)

        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        self.date_label = QLabel()
        self.date_label.setObjectName("DateLabel")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock_label = QLabel()
        self.clock_label.setObjectName("ClockLabel")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        clock_box.addWidget(self.date_label)
        clock_box.addWidget(self.clock_label)
        header.addLayout(clock_box)
        root.addLayout(header)

        # --- quick actions -------------------------------------------------
        quick_row = QHBoxLayout()
        quick_row.setSpacing(10)
        for key, label, kind in QUICK_ACTIONS:
            button = QPushButton(label)
            button.setObjectName("QuickActionButton")
            button.setProperty("kind", kind)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda checked=False, k=key: self.quick_action_requested.emit(k))
            quick_row.addWidget(button)
        quick_row.addStretch(1)
        root.addLayout(quick_row)

        # --- summary cards ---------------------------------------------------
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

        # --- filters + search ------------------------------------------------
        filter_box = QVBoxLayout()
        filter_box.setSpacing(8)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search room number...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(240)
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_edit)
        search_row.addStretch(1)
        filter_box.addLayout(search_row)

        self.type_group = QButtonGroup(self)
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        for key, label in _TYPE_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)
            button.setProperty("filter_type", key)
            button.clicked.connect(self._on_type_filter)
            self.type_group.addButton(button)
            type_row.addWidget(button)
        type_row.addStretch(1)
        filter_box.addLayout(type_row)

        self.status_group = QButtonGroup(self)
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        for key, label in _STATUS_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterButton")
            button.setCheckable(True)
            button.setProperty("filter_status", key)
            button.clicked.connect(self._on_status_filter)
            self.status_group.addButton(button)
            status_row.addWidget(button)
        status_row.addStretch(1)
        filter_box.addLayout(status_row)

        root.addLayout(filter_box)

        # --- room grid (flows inside the outer page scroll) --------------------
        self.room_grid_container = QWidget()
        self.room_grid = FlowLayout(self.room_grid_container, margin=0, h_spacing=14, v_spacing=14)
        self.room_grid_container.setLayout(self.room_grid)
        self.room_grid_container.setMinimumHeight(190)
        root.addWidget(self.room_grid_container)

        # --- today's activity ---------------------------------------------------
        activity_header = QLabel("Today's Activity")
        activity_header.setObjectName("SectionHeading")
        root.addWidget(activity_header)

        tables_row = QHBoxLayout()
        tables_row.setSpacing(12)
        self.check_ins_table = self._make_activity_table(["Guest", "Room", "Check-in Time"])
        tables_row.addWidget(self.check_ins_table, 1)
        self.check_outs_table = self._make_activity_table(["Guest", "Room", "Check-out Time"])
        tables_row.addWidget(self.check_outs_table, 1)

        summary_box = QVBoxLayout()
        summary_box.setSpacing(10)
        self.collected_card = SummaryCard("Collected Today", "₹0.00", icon="💵", accent="paid")
        self.collected_card.setMinimumWidth(200)
        self.collected_card.setMinimumHeight(96)
        summary_box.addWidget(self.collected_card)
        self.payments_card = SummaryCard("Completed Payments", "0", icon="✅", accent="paid")
        self.payments_card.setMinimumHeight(96)
        summary_box.addWidget(self.payments_card)
        self.outstanding_card = SummaryCard("Outstanding", "₹0.00", icon="⏳", accent="unpaid")
        self.outstanding_card.setMinimumHeight(96)
        summary_box.addWidget(self.outstanding_card)
        summary_box.addStretch(1)
        tables_row.addLayout(summary_box)
        root.addLayout(tables_row)

        upcoming_header = QLabel("Upcoming Bookings (Next 7 Days)")
        upcoming_header.setObjectName("SectionHeading")
        root.addWidget(upcoming_header)

        self.upcoming_table = QTableWidget(0, 6)
        self.upcoming_table.setHorizontalHeaderLabels(
            ["Booking No.", "Guest", "Room", "Check-in", "Check-out", "Status"]
        )
        self.upcoming_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.upcoming_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.upcoming_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.upcoming_table.verticalHeader().setVisible(False)
        header = self.upcoming_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.upcoming_table.setMaximumHeight(170)
        self.upcoming_table.doubleClicked.connect(self._open_upcoming_booking)
        root.addWidget(self.upcoming_table)

    def _make_activity_table(self, headers: list) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table_header = table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setMaximumHeight(170)
        table.doubleClicked.connect(self._open_activity_booking)
        return table

    def _start_clock(self) -> None:
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start()
        self._update_clock()

    def _update_clock(self) -> None:
        now = datetime.now()
        self.date_label.setText(now.strftime("%A, %d %B %Y"))
        self.clock_label.setText(now.strftime("%I:%M:%S %p"))

    # ------------------------------------------------------------ actions

    def open_dialog(self, action: str) -> None:
        """Handle a quick action requested from this page."""
        if action == "new_booking":
            from app.ui.dialogs.booking_form_dialog import BookingFormDialog

            dialog = BookingFormDialog(self.database, on_changed=self.refresh, parent=self)
            if dialog.exec():
                self.refresh()
        elif action == "walkin":
            from app.ui.dialogs.walkin_dialog import WalkInDialog

            dialog = WalkInDialog(self.database, on_changed=self.refresh, parent=self)
            if dialog.exec():
                self.refresh()
        # checkin / checkout are handled by the main window (page navigation).

    # ------------------------------------------------------------ filters

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
        """Reload rooms and counts from the database, then re-render."""
        today = datetime.now().date()
        with self.database.session_scope() as session:
            self.rooms = room_service.get_all_rooms(session)
            self.counts = room_service.get_room_status_counts(session)
            hotel_name = settings_service.get_setting(session, "hotel_name", APP_NAME)
            self.today_check_ins = booking_service.get_today_check_ins(session, today)
            self.today_check_outs = booking_service.get_today_check_outs(session, today)
            self.upcoming_bookings = booking_service.get_upcoming_bookings(session, days=7, today=today)
            collected = financial_service.get_today_payment_total(session, today)
            overview = analytics_service.get_payment_overview(session, today, today)
            self.room_occupants = {}
            for room in self.rooms:
                booking = booking_service.get_active_booking_for_room(session, room.id)
                if booking is not None and booking.guest is not None:
                    self.room_occupants[room.id] = booking.guest.guest_name
        if hotel_name:
            self.hotel_name_label.setText(hotel_name)
        self._render_cards()
        self._render_activity(collected, overview)
        self._render_grid()

    def _render_activity(self, collected, overview) -> None:  # noqa: ANN001
        self.collected_card.set_value(format_money(collected))
        self.collected_card.set_subtext("Completed payments today")
        self.payments_card.set_value(int(overview["paid"]))
        self.payments_card.set_subtext("Bookings fully paid today")
        self.outstanding_card.set_value(format_money(overview["outstanding"]))
        self.outstanding_card.set_subtext("Remaining balance")
        self._render_activity_table(self.check_ins_table, self.today_check_ins, "Check-in Time")
        self._render_activity_table(self.check_outs_table, self.today_check_outs, "Check-out Time")
        self._render_upcoming_table()

    def _render_activity_table(self, table: QTableWidget, bookings: list, time_label: str) -> None:
        table.setRowCount(0)
        for row_index, booking in enumerate(bookings):
            table.insertRow(row_index)
            guest = booking.guest
            room = booking.room
            values = [
                guest.guest_name if guest else "—",
                room.room_number if room else "—",
                format_date_time(booking.check_in_date if time_label == "Check-in Time" else booking.check_out_date,
                                 booking.check_in_time if time_label == "Check-in Time" else booking.check_out_time),
            ]
            for col, value in enumerate(values):
                table.setItem(row_index, col, QTableWidgetItem(value))
            table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, booking.id)

    def _render_upcoming_table(self) -> None:
        self.upcoming_table.setRowCount(0)
        for row_index, booking in enumerate(self.upcoming_bookings):
            self.upcoming_table.insertRow(row_index)
            guest = booking.guest
            room = booking.room
            try:
                status_text = BookingStatus(booking.status).label
            except ValueError:
                status_text = booking.status
            values = [
                booking.booking_number,
                guest.guest_name if guest else "—",
                room.room_number if room else "—",
                format_date_time(booking.check_in_date, booking.check_in_time),
                format_date_time(booking.check_out_date, booking.check_out_time),
                status_text,
            ]
            for col, value in enumerate(values):
                self.upcoming_table.setItem(row_index, col, QTableWidgetItem(value))
            self.upcoming_table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, booking.id)
        if not self.upcoming_bookings:
            self.upcoming_table.setRowCount(1)
            item = QTableWidgetItem("No upcoming bookings in the next 7 days")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.upcoming_table.setItem(0, 0, item)

    def _open_activity_booking(self) -> None:
        booking_id = self._booking_id_from_table(self.sender() if hasattr(self, "sender") else None)
        if booking_id is not None:
            self._open_booking_details(booking_id)

    def _open_upcoming_booking(self) -> None:
        booking_id = self._booking_id_from_table(self.upcoming_table)
        if booking_id is not None:
            self._open_booking_details(booking_id)

    @staticmethod
    def _booking_id_from_table(table) -> int | None:  # noqa: ANN001
        if table is None:
            return None
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        return int(value) if value is not None else None

    def _open_booking_details(self, booking_id: int) -> None:
        dialog = BookingDetailsDialog(
            self.database,
            booking_id,
            on_changed=self.refresh,
            parent=self,
        )
        dialog.exec()
        self.refresh()

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
        while self.room_grid.count():
            item = self.room_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for room in self._filtered_rooms():
            card = RoomCard(room, occupant=self.room_occupants.get(room.id))
            card.clicked.connect(self._open_room_details)
            self.room_grid.addWidget(card)

        self.room_grid_container.adjustSize()

    # ------------------------------------------------------- room details

    def _open_room_details(self, room_id: int) -> None:
        dialog = RoomDetailsDialog(
            self.database,
            room_id,
            on_changed=self.refresh,
            parent=self,
        )
        dialog.exec()
