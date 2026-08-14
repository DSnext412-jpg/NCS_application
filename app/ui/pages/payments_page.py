"""Payments page: filterable history of every recorded payment."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
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

from app.core.constants import (
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
)
from app.database.database import Database
from app.services import financial_service
from app.ui.dialogs.booking_details_dialog import BookingDetailsDialog
from app.ui.formatters import format_date, format_money
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table, money_item, status_item

_PERIOD_FILTERS = (
    ("all", "All Time"),
    ("today", "Today"),
    ("7d", "Last 7 Days"),
    ("30d", "Last 30 Days"),
)
_STATUS_FILTERS = (("all", "All"),) + tuple(
    (status.value, status.label) for status in PaymentRecordStatus
)


class PaymentsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._period = "all"
        self._status_filter = None
        self._rows: list[tuple] = []

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(14)

        title = QLabel("Payments")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("All recorded payments and collections.")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by booking no., guest or mobile...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(300)
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)

        self.total_card_label = QLabel()
        self.total_card_label.setProperty("detailValue", True)
        toolbar.addWidget(self.total_card_label)
        root.addLayout(toolbar)

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._label("Period:"))
        self._period_group = QButtonGroup(self)
        for key, label in _PERIOD_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("period", key)
            if key == "all":
                button.setChecked(True)
            self._period_group.addButton(button)
            self._period_group.buttonClicked.connect(self._on_period_filter)
            row.addWidget(button)
        row.addSpacing(18)
        row.addWidget(self._label("Status:"))
        self._status_group = QButtonGroup(self)
        for key, label in _STATUS_FILTERS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("status", key)
            if key == "all":
                button.setChecked(True)
            self._status_group.addButton(button)
            self._status_group.buttonClicked.connect(self._on_status_filter)
            row.addWidget(button)
        row.addStretch(1)
        root.addLayout(row)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Date", "Booking No.", "Guest", "Room", "Method", "Amount", "Ref. No.", "Status"],
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._open_booking)
        root.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "No payments found", "Try adjusting the filters or search.", icon="💳"
        )
        self.empty_state.setVisible(False)
        root.addWidget(self.empty_state)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    # ------------------------------------------------------------ filters

    def _on_period_filter(self, button: QPushButton) -> None:
        self._period = button.property("period")
        self.refresh()

    def _on_status_filter(self, button: QPushButton) -> None:
        value = button.property("status")
        self._status_filter = None if value == "all" else value
        self.refresh()

    # --------------------------------------------------------------- data

    def _date_range(self) -> tuple[date | None, date | None]:
        today = date.today()
        if self._period == "today":
            return today, today
        if self._period == "7d":
            return today - timedelta(days=6), today
        if self._period == "30d":
            return today - timedelta(days=29), today
        return None, None

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        date_from, date_to = self._date_range()

        rows: list[tuple] = []
        total = None
        with self.database.session_scope() as session:
            payments = financial_service.list_payments(
                session,
                query=query,
                status=self._status_filter,
                date_from=date_from,
                date_to=date_to,
            )
            if self._status_filter in (None, PaymentRecordStatus.COMPLETED.value):
                total = financial_service.get_payment_period_total(
                    session, date_from, date_to
                )
            for payment in payments:
                booking = payment.booking
                guest = booking.guest if booking else None
                room = booking.room if booking else None
                try:
                    method_label = PaymentMethod(payment.payment_method).label
                except ValueError:
                    method_label = payment.payment_method
                booking_status = "unpaid"
                if booking is not None:
                    booking_status = financial_service.get_financial_summary(
                        session, booking.id
                    ).payment_status.value
                rows.append(
                    (
                        format_date(payment.payment_date),
                        booking.booking_number if booking else "—",
                        guest.guest_name if guest else "—",
                        f"Room {room.room_number}" if room else "—",
                        method_label,
                        format_money(payment.amount),
                        payment.reference_number or "—",
                        booking_status,
                        payment.id,
                    )
                )
        self._rows = rows
        if total is not None:
            self.total_card_label.setText(f"Collected (filtered period): {format_money(total)}")
        else:
            self.total_card_label.setText("")

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_index, values in enumerate(rows):
            self.table.insertRow(row_index)
            for col in range(8):
                if col == 7:
                    record_status = values[7]
                    try:
                        item = status_item(PaymentStatus(record_status).label, record_status)
                    except ValueError:
                        item = QTableWidgetItem(record_status)
                elif col == 5:
                    item = money_item(values[col])
                else:
                    item = QTableWidgetItem(values[col])
                self.table.setItem(row_index, col, item)
            self.table.item(row_index, 0).setData(Qt.ItemDataRole.UserRole, values[8])
        self.table.setSortingEnabled(True)

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

    # ----------------------------------------------------------- actions

    def _open_booking(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        payment_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        booking_id = self._booking_id_for_payment(payment_id)
        if booking_id is None:
            return
        dialog = BookingDetailsDialog(self.database, booking_id, on_changed=self.refresh, parent=self)
        dialog.exec()
        self.refresh()

    def _booking_id_for_payment(self, payment_id: int) -> int | None:
        from app.database.models import Payment

        with self.database.session_scope() as session:
            payment = session.get(Payment, payment_id)
            return payment.booking_id if payment else None
