"""Global reception search (Ctrl+K).

Searches guests and bookings from anywhere in the application. Double
clicking a result opens the relevant details dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.database.database import Database
from app.services import booking_service


class GlobalSearchDialog(QDialog):
    def __init__(self, database: Database, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database

        self.setWindowTitle("Search Guests & Bookings")
        self.setModal(True)
        self.setMinimumSize(560, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, mobile, booking no. or room...")
        self.search_edit.textChanged.connect(self._search)
        layout.addWidget(self.search_edit)

        guests_label = QLabel("Guests")
        guests_label.setObjectName("SectionHeading")
        layout.addWidget(guests_label)
        self.guest_list = QListWidget()
        self.guest_list.itemDoubleClicked.connect(self._open_guest)
        layout.addWidget(self.guest_list, 1)

        bookings_label = QLabel("Bookings")
        bookings_label.setObjectName("SectionHeading")
        layout.addWidget(bookings_label)
        self.booking_list = QListWidget()
        self.booking_list.itemDoubleClicked.connect(self._open_booking)
        layout.addWidget(self.booking_list, 1)

        hint = QLabel("Double-click a result to open it. Guests: name • mobile • city")
        hint.setProperty("detailLabel", True)
        layout.addWidget(hint)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

        self.search_edit.setFocus()

    def set_initial_query(self, query: str) -> None:
        if query:
            self.search_edit.setText(query)
            self._search(query)

    # ------------------------------------------------------------------ ui

    def _search(self, text: str) -> None:
        query = text.strip()
        self.guest_list.clear()
        self.booking_list.clear()
        if not query:
            return
        with self.database.session_scope() as session:
            results = booking_service.search_global(session, query)
        for guest in results["guests"]:
            item = QListWidgetItem(f"{guest.guest_name}  •  {guest.mobile_number}  •  {guest.city or '—'}")
            item.setData(Qt.ItemDataRole.UserRole, guest.id)
            self.guest_list.addItem(item)
        for booking in results["bookings"]:
            room = booking.room
            room_text = f"Room {room.room_number}" if room else "—"
            item = QListWidgetItem(
                f"{booking.booking_number}  •  {booking.guest.guest_name if booking.guest else '—'}  •  {room_text}"
            )
            item.setData(Qt.ItemDataRole.UserRole, booking.id)
            self.booking_list.addItem(item)

    def _open_guest(self, item: QListWidgetItem) -> None:
        guest_id = item.data(Qt.ItemDataRole.UserRole)
        from app.ui.dialogs.guest_details_dialog import GuestDetailsDialog

        dialog = GuestDetailsDialog(self.database, guest_id, parent=self)
        dialog.exec()
        self._search(self.search_edit.text())

    def _open_booking(self, item: QListWidgetItem) -> None:
        booking_id = item.data(Qt.ItemDataRole.UserRole)
        from app.ui.dialogs.booking_details_dialog import BookingDetailsDialog

        dialog = BookingDetailsDialog(self.database, booking_id, parent=self)
        dialog.exec()
        self._search(self.search_edit.text())
