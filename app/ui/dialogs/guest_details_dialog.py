"""Guest details dialog: guest information + booking history."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.core.constants import BookingStatus
from app.database.database import Database
from app.services import guest_service
from app.ui.formatters import format_datetime, mask_id_number
from app.ui.widgets.status_badge import make_status_badge

_STATUS_LABELS = {status.value: status.label for status in BookingStatus}


class GuestDetailsDialog(QDialog):
    def __init__(self, database: Database, guest_id: int, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.guest_id = guest_id

        self.setWindowTitle("Guest Details")
        self.setModal(True)
        self.setMinimumSize(640, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        with self.database.session_scope() as session:
            guest = guest_service.get_guest(session, guest_id)
            if guest is None:
                self.reject()
                return
            history = guest_service.get_guest_booking_history(session, guest_id)
            self.guest = guest

        name_label = QLabel(guest.guest_name)
        name_label.setObjectName("DialogRoomNumber")
        layout.addWidget(name_label)

        info_card = QFrame()
        info_card.setObjectName("DetailsCard")
        grid = QGridLayout(info_card)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)

        rows = (
            ("Mobile", guest.mobile_number or "—"),
            ("Alternate", guest.alternate_number or "—"),
            ("Address", guest.address or "—"),
            ("City", guest.city or "—"),
            ("State", guest.state or "—"),
            ("Country", guest.country or "—"),
            ("ID Type", guest.id_type or "—"),
            ("ID Number", mask_id_number(guest.id_number)),
            ("Adults / Children", f"{guest.adults} / {guest.children}"),
            ("Created", format_datetime(guest.created_at)),
            ("Last Updated", format_datetime(guest.updated_at)),
        )
        for row, (title, value) in enumerate(rows):
            label = QLabel(title)
            label.setProperty("detailLabel", True)
            grid.addWidget(label, row, 0)
            value_label = QLabel(value)
            value_label.setProperty("detailValue", True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(value_label, row, 1)
        layout.addWidget(info_card)

        if guest.special_notes:
            notes = QLabel(f"Notes: {guest.special_notes}")
            notes.setWordWrap(True)
            notes.setProperty("detailLabel", True)
            layout.addWidget(notes)

        history_header = QLabel("Booking History")
        history_header.setObjectName("SectionHeading")
        layout.addWidget(history_header)

        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["Booking No.", "Room", "Check-in", "Check-out", "Status"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setFixedHeight(220)

        for booking in history:
            row_index = table.rowCount()
            table.insertRow(row_index)
            table.setItem(row_index, 0, QTableWidgetItem(booking.booking_number))
            table.setItem(row_index, 1, QTableWidgetItem(booking.room.room_number if booking.room else "—"))
            table.setItem(row_index, 2, QTableWidgetItem(self._format(booking.check_in_date, booking.check_in_time)))
            table.setItem(row_index, 3, QTableWidgetItem(self._format(booking.check_out_date, booking.check_out_time)))
            status_text = _STATUS_LABELS.get(booking.status, booking.status.title())
            status_item = QTableWidgetItem(status_text)
            table.setItem(row_index, 4, status_item)
        if not history:
            table.setRowCount(1)
            item = QTableWidgetItem("No bookings yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            table.setItem(0, 0, item)
        layout.addWidget(table)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        edit_button = QPushButton("Edit Guest")
        edit_button.setObjectName("ActionButton")
        edit_button.clicked.connect(self._edit_guest)
        close_row.addWidget(edit_button)
        close_button = QPushButton("Close")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _edit_guest(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from app.ui.dialogs.guest_form_dialog import GuestFormDialog

        dialog = GuestFormDialog(self.database, guest_id=self.guest_id, parent=self)
        if dialog.exec():
            QMessageBox.information(self, "Guest Updated", "Guest updated successfully.")
            self.accept()

    @staticmethod
    def _format(day, t) -> str:  # noqa: ANN001
        from app.ui.formatters import format_date_time

        return format_date_time(day, t)
