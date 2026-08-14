"""Invoices page: invoice history with search, status and date filters.

Reads invoice records only (never their PDFs), so the list stays fast even
on a low-RAM reception computer. Opening an invoice loads its frozen
snapshot.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
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
    InvoiceStatus,
    PaymentStatus,
)
from app.database.database import Database
from app.database.models import Invoice
from app.services import invoice_service
from app.ui.dialogs.invoice_dialog import InvoiceDialog
from app.ui.formatters import format_money
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table, money_item, status_item

_PAYMENT_FILTERS = (("all", "All"),) + tuple((status.value, status.label) for status in PaymentStatus)
_INVOICE_FILTERS = (("all", "All"),) + tuple((status.value, status.label) for status in InvoiceStatus)
_PERIOD_FILTERS = (
    ("all", "All"),
    ("today", "Today"),
    ("week", "This Week"),
    ("month", "This Month"),
    ("custom", "Custom"),
)

_STATUS_LABELS = {status.value: status.label for status in InvoiceStatus}
_PAYMENT_LABELS = {status.value: status.label for status in PaymentStatus}


class InvoicesPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._payment_filter: str | None = None
        self._invoice_filter: str | None = None
        self._period_filter: str = "all"

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("Invoices")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Invoice history and payment tracking.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by invoice no., guest, mobile or room...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(320)
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        # Payment status filter.
        self._payment_buttons = QButtonGroup(self)
        payment_row = QHBoxLayout()
        payment_row.setSpacing(6)
        payment_label = QLabel("Payment:")
        payment_label.setProperty("detailLabel", True)
        payment_row.addWidget(payment_label)
        for key, label in _PAYMENT_FILTERS:
            self._add_chip(payment_row, self._payment_buttons, label, key, self._on_payment_filter)
        payment_row.addStretch(1)
        layout.addLayout(payment_row)

        # Invoice status filter.
        self._invoice_buttons = QButtonGroup(self)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_label = QLabel("Invoice:")
        status_label.setProperty("detailLabel", True)
        status_row.addWidget(status_label)
        for key, label in _INVOICE_FILTERS:
            self._add_chip(status_row, self._invoice_buttons, label, key, self._on_invoice_filter)
        status_row.addStretch(1)
        layout.addLayout(status_row)

        # Date period filter.
        self._period_buttons = QButtonGroup(self)
        period_row = QHBoxLayout()
        period_row.setSpacing(6)
        period_label = QLabel("Date:")
        period_label.setProperty("detailLabel", True)
        period_row.addWidget(period_label)
        for key, label in _PERIOD_FILTERS:
            self._add_chip(period_row, self._period_buttons, label, key, self._on_period_filter)
        period_row.addSpacing(12)
        self.date_from_edit = QDateEdit(QDate(date.today().replace(day=1)))
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_from_edit.setEnabled(False)
        self.date_to_edit = QDateEdit(QDate.currentDate())
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_to_edit.setEnabled(False)
        period_row.addWidget(self.date_from_edit)
        period_row.addWidget(self.date_to_edit)
        self.date_from_edit.dateChanged.connect(self.refresh)
        self.date_to_edit.dateChanged.connect(self.refresh)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Invoice No.", "Date", "Guest", "Room", "Total", "Paid", "Remaining", "Payment", "Invoice Status"],
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._view_selected)
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "No invoices found", "Try adjusting the search or filters.", icon="🧾"
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        view_row = QHBoxLayout()
        view_button = QPushButton("View Invoice")
        view_button.setObjectName("ActionButton")
        view_button.clicked.connect(self._view_selected)
        view_row.addWidget(view_button)
        view_row.addStretch(1)
        layout.addLayout(view_row)

    def _add_chip(self, layout: QHBoxLayout, group: QButtonGroup, label: str, key: str, handler) -> None:  # noqa: ANN001
        button = QPushButton(label)
        button.setCheckable(True)
        button.setObjectName("FilterChip")
        button.setProperty("filterValue", key)
        if key == "all":
            button.setChecked(True)
        group.addButton(button)
        group.buttonClicked.connect(handler)
        layout.addWidget(button)

    # ------------------------------------------------------------- filters

    def _on_payment_filter(self, button: QPushButton) -> None:
        value = button.property("filterValue")
        self._payment_filter = None if value == "all" else value
        self.refresh()

    def _on_invoice_filter(self, button: QPushButton) -> None:
        value = button.property("filterValue")
        self._invoice_filter = None if value == "all" else value
        self.refresh()

    def _on_period_filter(self, button: QPushButton) -> None:
        self._period_filter = button.property("filterValue")
        custom = self._period_filter == "custom"
        self.date_from_edit.setEnabled(custom)
        self.date_to_edit.setEnabled(custom)
        self.refresh()

    def _qdate(self, widget: QDateEdit) -> date:
        qdate = widget.date()
        return date(qdate.year(), qdate.month(), qdate.day())

    # ---------------------------------------------------------------- data

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        today = date.today()
        date_from = None
        date_to = None
        if self._period_filter == "custom":
            start, end = self._qdate(self.date_from_edit), self._qdate(self.date_to_edit)
            if start > end:
                start, end = end, start
            date_from, date_to = start, end

        with self.database.session_scope() as session:
            invoices: list[Invoice] = invoice_service.filter_invoices(
                session,
                query=query,
                payment_status=self._payment_filter,
                invoice_status=self._invoice_filter,
                period=self._period_filter,
                today=today,
                date_from=date_from,
                date_to=date_to,
            )
            rows = []
            for invoice in invoices:
                booking = invoice.booking
                guest = booking.guest if booking else None
                room = booking.room if booking else None
                rows.append(
                    (
                        invoice.invoice_number,
                        invoice.invoice_date,
                        guest.guest_name if guest else "—",
                        room.room_number if room else "—",
                        invoice.grand_total,
                        invoice.total_paid,
                        invoice.remaining_amount,
                        invoice.payment_status,
                        invoice.status,
                    )
                )

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_index, values in enumerate(rows):
            self.table.insertRow(row_index)
            for col in range(9):
                if col == 7:
                    payment_value = values[7]
                    item = status_item(
                        _PAYMENT_LABELS.get(payment_value, payment_value.title()), payment_value
                    )
                elif col == 8:
                    status_value = values[8]
                    item = status_item(
                        _STATUS_LABELS.get(status_value, status_value.title()), status_value
                    )
                elif col in (4, 5, 6):
                    item = money_item(format_money(values[col]))
                elif col == 1:
                    item = QTableWidgetItem(values[col].strftime("%d %b %Y"))
                else:
                    item = QTableWidgetItem(str(values[col]))
                self.table.setItem(row_index, col, item)
        self.table.setSortingEnabled(True)

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

    # ------------------------------------------------------------- actions

    def _selected_invoice_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        invoice_number = self.table.item(row, 0).text()
        with self.database.session_scope() as session:
            invoice = invoice_service.get_invoice_by_number(session, invoice_number)
            return invoice.id if invoice else None

    def _view_selected(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            return
        dialog = InvoiceDialog(self.database, invoice_id, on_changed=self.refresh, parent=self)
        dialog.exec()
        self.refresh()
