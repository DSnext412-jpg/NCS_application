"""Bookings management page: search, filter, list and open booking details."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import BookingStatus
from app.database.database import Database
from app.services import booking_service, financial_service
from app.ui.dialogs.booking_details_dialog import BookingDetailsDialog
from app.ui.formatters import format_date_time, format_money
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table, money_item, status_item

_STATUS_NAMES = {status.value: status.label for status in BookingStatus}


class BookingsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._status_filter: str | None = None
        self._period_filter: str = "all"

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("Bookings")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Manage reservations, stays and booking history.")
        subtitle.setObjectName("PageSubtitle")
        self.subtitle = subtitle
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by booking no., guest or mobile...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(300)
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        new_booking = QPushButton("+ New Booking")
        new_booking.setObjectName("QuickActionButton")
        new_booking.clicked.connect(self._new_booking)
        toolbar.addWidget(new_booking)

        walk_in = QPushButton("Walk-in")
        walk_in.setObjectName("SecondaryButton")
        walk_in.clicked.connect(self._walk_in)
        toolbar.addWidget(walk_in)
        layout.addLayout(toolbar)

        # Status filter row.
        self._status_buttons = QButtonGroup(self)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._add_status_button(status_row, "All", None)
        for status in BookingStatus:
            self._add_status_button(status_row, status.label, status.value)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        # Period filter row.
        self._period_buttons = QButtonGroup(self)
        period_row = QHBoxLayout()
        period_row.setSpacing(6)
        period_label = QLabel("Period:")
        period_label.setProperty("detailLabel", True)
        period_row.addWidget(period_label)
        for key, label in (("all", "All"), ("today", "Today"), ("upcoming", "Upcoming"), ("past", "Past")):
            self._add_period_button(period_row, label, key)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Booking No.", "Guest", "Room", "Room Type", "Check-in", "Check-out", "Source", "Balance", "Payment", "Status", "Action"],
            resize_to_contents_cols=[10],
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._open_selected)
        self.table.horizontalHeader().sortIndicatorChanged.connect(self._apply_row_buttons)
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "No bookings found",
            "There are no bookings matching the selected filters.",
            icon="📅",
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

    def _add_status_button(self, layout: QHBoxLayout, label: str, value: str | None) -> None:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setObjectName("FilterChip")
        button.setProperty("filterValue", value or "__all__")
        if value is None:
            button.setChecked(True)
        self._status_buttons.addButton(button)
        self._status_buttons.buttonClicked.connect(self._on_status_filter)
        layout.addWidget(button)

    def _add_period_button(self, layout: QHBoxLayout, label: str, value: str) -> None:
        button = QPushButton(label)
        button.setCheckable(True)
        button.setObjectName("FilterChip")
        button.setProperty("filterValue", value)
        if value == "all":
            button.setChecked(True)
        self._period_buttons.addButton(button)
        self._period_buttons.buttonClicked.connect(self._on_period_filter)
        layout.addWidget(button)

    # ------------------------------------------------------------- filters

    def _on_status_filter(self, button: QPushButton) -> None:
        self._status_filter = button.property("filterValue")
        if self._status_filter == "__all__":
            self._status_filter = None
        self.refresh()

    def _on_period_filter(self, button: QPushButton) -> None:
        self._period_filter = button.property("filterValue")
        self.refresh()

    def set_status_filter(self, status: BookingStatus | None) -> None:
        """Route the page to a specific status filter (sidebar quick links)."""
        target = status.value if status is not None else "__all__"
        for button in self._status_buttons.buttons():
            if button.property("filterValue") == target:
                button.setChecked(True)
        self._status_filter = status.value if status is not None else None
        if status == BookingStatus.RESERVED:
            self.subtitle.setText("Bookings waiting to check in — show this list from the Check-in link.")
        elif status == BookingStatus.CHECKED_IN:
            self.subtitle.setText("Bookings ready to check out — show this list from the Check-out link.")
        else:
            self.subtitle.setText("Manage reservations, stays and booking history.")
        self.refresh()

    # ----------------------------------------------------------------- data

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        status = self._status_filter
        period = self._period_filter

        today = date.today()
        with self.database.session_scope() as session:
            bookings = booking_service.filter_bookings(
                session,
                query=query,
                status=status,
                today=today,
                period=period,
            )
            rows = []
            for booking in bookings:
                guest = booking.guest
                room = booking.room
                source = booking.source
                summary = financial_service.get_financial_summary(session, booking.id)
                rows.append(
                    (
                        booking.booking_number,
                        guest.guest_name if guest else "—",
                        room.room_number if room else "—",
                        room.room_type if room else "—",
                        format_date_time(booking.check_in_date, booking.check_in_time),
                        format_date_time(booking.check_out_date, booking.check_out_time),
                        source.name if source else "—",
                        format_money(summary.remaining),
                        format_money(summary.total_paid),
                        booking.status,
                        booking.id,
                    )
                )
        self._rows_status = {row[0]: row[9] for row in rows}
        self._rows_ids = {row[0]: row[10] for row in rows}
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_index, values in enumerate(rows):
            self.table.insertRow(row_index)
            for col in range(10):
                if col == 8:
                    item = money_item(values[8])
                elif col == 9:
                    status_value = values[9]
                    item = status_item(
                        _STATUS_NAMES.get(status_value, status_value.title()), status_value
                    )
                elif col == 7:
                    item = money_item(values[col])
                else:
                    item = QTableWidgetItem(values[col])
                self.table.setItem(row_index, col, item)
        self.table.setSortingEnabled(True)
        self._apply_row_buttons()

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

    def _apply_row_buttons(self) -> None:
        """Place a Check-out and/or Delete button on each booking row."""
        for row in range(self.table.rowCount()):
            self.table.removeCellWidget(row, 10)
            number_item = self.table.item(row, 0)
            if number_item is None:
                continue
            booking_number = number_item.text()
            booking_status = self._rows_status.get(booking_number)
            if booking_status == BookingStatus.DELETED.value:
                continue
            button_row = QWidget()
            button_layout = QHBoxLayout(button_row)
            button_layout.setContentsMargins(4, 0, 4, 0)
            button_layout.setSpacing(6)
            if booking_status == BookingStatus.CHECKED_IN.value:
                check_out = QPushButton("Check-out")
                check_out.setObjectName("SmallActionButton")
                check_out.clicked.connect(
                    lambda checked=False, bid=self._rows_ids.get(booking_number): self._check_out_booking(bid)
                )
                button_layout.addWidget(check_out)
            delete_button = QPushButton("Delete")
            delete_button.setObjectName("DangerSmallButton")
            delete_button.clicked.connect(
                lambda checked=False, bid=self._rows_ids.get(booking_number): self._delete_booking(bid)
            )
            button_layout.addWidget(delete_button)
            button_layout.addStretch(1)
            self.table.setCellWidget(row, 10, button_row)

    # ------------------------------------------------------------- actions

    def _new_booking(self) -> None:
        from app.ui.dialogs.booking_form_dialog import BookingFormDialog

        dialog = BookingFormDialog(self.database, on_changed=self.refresh, parent=self)
        if dialog.exec():
            self.refresh()

    def _walk_in(self) -> None:
        from app.ui.dialogs.walkin_dialog import WalkInDialog

        dialog = WalkInDialog(self.database, on_changed=self.refresh, parent=self)
        if dialog.exec():
            self.refresh()

    def _selected_booking_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        booking_number = self.table.item(row, 0).text()
        with self.database.session_scope() as session:
            booking = booking_service.get_booking_by_number(session, booking_number)
            return booking.id if booking else None

    def _open_selected(self) -> None:
        booking_id = self._selected_booking_id()
        if booking_id is None:
            return
        dialog = BookingDetailsDialog(self.database, booking_id, on_changed=self.refresh, parent=self)
        dialog.exec()
        self.refresh()

    def _delete_booking(self, booking_id: int | None) -> None:
        if booking_id is None:
            return
        from PySide6.QtWidgets import QMessageBox

        from app.ui.dialogs.reason_dialog import ReasonPromptDialog

        with self.database.session_scope() as session:
            booking = booking_service.get_booking(session, booking_id)
        if booking is None or booking.status == BookingStatus.DELETED.value:
            return
        label = f"Booking {booking.booking_number}"
        if booking.guest is not None:
            label += f" — {booking.guest.guest_name}"
        dialog = ReasonPromptDialog(
            "Delete Booking",
            f"{label}\n\n"
            "The booking will be removed from all reports, payment counts and "
            "dashboards. It will remain only in the deleted-booking history.",
        )
        if not dialog.exec():
            return
        try:
            with self.database.session_scope() as session:
                booking_service.delete_booking(session, booking_id, dialog.reason())
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Booking deletion failed")
            QMessageBox.critical(self, "Error", "Could not delete the booking. See logs for details.")
            return
        self.refresh()

    def _check_out_booking(self, booking_id: int | None) -> None:
        if booking_id is None:
            return
        from app.ui.dialogs.checkout_dialog import CheckOutDialog

        dialog = CheckOutDialog(self.database, booking_id, parent=self)
        if dialog.exec():
            self.refresh()
