"""Guests management page: search, list and open guest details."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from app.services import guest_service
from app.ui.dialogs.guest_details_dialog import GuestDetailsDialog
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table, status_item


class GuestsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("Guests")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Manage guest records and booking history.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name or mobile...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(280)
        self.search_edit.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search_edit)
        toolbar.addStretch(1)
        edit_button = QPushButton("Edit Guest")
        edit_button.setObjectName("SecondaryButton")
        edit_button.clicked.connect(self._edit_selected)
        toolbar.addWidget(edit_button)
        new_button = QPushButton("+ New Guest")
        new_button.setObjectName("QuickActionButton")
        new_button.clicked.connect(self._new_guest)
        toolbar.addWidget(new_button)
        layout.addLayout(toolbar)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Guest Name", "Mobile", "City", "ID Type", "Total Bookings", "Last Booking", "Status"],
            resize_to_contents_cols=[0],
        )
        self.table.setSortingEnabled(True)
        self.table.doubleClicked.connect(self._open_selected)
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyState(
            "No guests found", "Try searching by guest name or mobile number.", icon="👤"
        )
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

    def refresh(self) -> None:
        query = self.search_edit.text().strip()
        with self.database.session_scope() as session:
            guests = guest_service.search_guests(session, query)
            rows = []
            for guest in guests:
                history = [b for b in guest.bookings if b.status != BookingStatus.DELETED.value]
                total = len(history)
                last = max((b.check_in_date for b in history), default=None)
                rows.append((guest.id, guest, total, last))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for guest_id, guest, total, last in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(guest.guest_name))
            self.table.setItem(row, 1, QTableWidgetItem(guest.mobile_number))
            self.table.setItem(row, 2, QTableWidgetItem(guest.city or ""))
            self.table.setItem(row, 3, QTableWidgetItem(guest.id_type or ""))
            self.table.setItem(row, 4, QTableWidgetItem(str(total)))
            self.table.setItem(row, 5, QTableWidgetItem(last.strftime("%d %b %Y") if last else "—"))
            self.table.setItem(row, 6, status_item("Active" if guest.is_active else "Inactive",
                                                   "paid" if guest.is_active else "cancelled"))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, guest_id)
        self.table.setSortingEnabled(True)

        has_rows = bool(rows)
        self.table.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)

    def _on_search(self) -> None:
        self.refresh()

    def _new_guest(self) -> None:
        from app.ui.dialogs.guest_form_dialog import GuestFormDialog

        dialog = GuestFormDialog(self.database, parent=self)
        if dialog.exec():
            self.refresh()

    def _edit_selected(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        guest_id = self._selected_guest_id()
        if guest_id is None:
            QMessageBox.information(self, "Select Guest", "Select a guest in the table first.")
            return
        from app.ui.dialogs.guest_form_dialog import GuestFormDialog

        dialog = GuestFormDialog(self.database, guest_id=guest_id, parent=self)
        if dialog.exec():
            QMessageBox.information(self, "Guest Updated", "Guest updated successfully.")
            self.refresh()

    def _selected_guest_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        guest_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return int(guest_id) if guest_id is not None else None

    def _open_selected(self) -> None:
        guest_id = self._selected_guest_id()
        if guest_id is None:
            return
        dialog = GuestDetailsDialog(self.database, guest_id, parent=self)
        dialog.exec()
