"""Reusable guest entry section for booking forms.

Supports searching for an existing guest and selecting it, or entering a
new guest's details inline. Used by the new-booking and walk-in dialogs.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import guest_service
from app.ui.dialogs.guest_form_dialog import GuestFormDialog


class GuestSection(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.selected_guest_id: int | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QLabel("Guest")
        header.setObjectName("SectionHeading")
        layout.addWidget(header)

        search_row = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name or mobile...")
        search_button = QPushButton("Search")
        search_button.setObjectName("SecondaryButton")
        search_button.clicked.connect(self._search)
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self.result_list = QListWidget()
        self.result_list.setVisible(False)
        self.result_list.setMaximumHeight(110)
        self.result_list.itemClicked.connect(self._select_match)
        layout.addWidget(self.result_list)

        self.guest_name_edit = QLineEdit()
        self.guest_name_edit.setPlaceholderText("Guest Name *")
        layout.addWidget(self.guest_name_edit)

        self.mobile_edit = QLineEdit()
        self.mobile_edit.setPlaceholderText("Mobile Number *")
        layout.addWidget(self.mobile_edit)

        self.alternate_edit = QLineEdit()
        self.alternate_edit.setPlaceholderText("Alternate Number")
        layout.addWidget(self.alternate_edit)

        row = QHBoxLayout()
        self.new_guest_button = QPushButton("+ New Guest")
        self.new_guest_button.setObjectName("SecondaryButton")
        self.new_guest_button.clicked.connect(self._create_new_guest)
        row.addWidget(self.new_guest_button)
        row.addStretch(1)
        layout.addLayout(row)

    def _search(self) -> None:
        query = self.search_edit.text().strip()
        with self.database.session_scope() as session:
            matches = guest_service.search_guests(session, query)
        self.result_list.clear()
        if not matches:
            self.result_list.setVisible(False)
            return
        for guest in matches:
            item = QListWidgetItem(f"{guest.guest_name}  •  {guest.mobile_number}")
            item.setData(Qt.ItemDataRole.UserRole, guest.id)
            self.result_list.addItem(item)
        self.result_list.setVisible(True)

    def _select_match(self, item: QListWidgetItem) -> None:
        guest_id = item.data(Qt.ItemDataRole.UserRole)
        with self.database.session_scope() as session:
            guest = guest_service.get_guest(session, guest_id)
        if guest is None:
            return
        self.selected_guest_id = guest.id
        self.guest_name_edit.setText(guest.guest_name)
        self.mobile_edit.setText(guest.mobile_number)
        self.alternate_edit.setText(guest.alternate_number or "")
        self.guest_name_edit.setReadOnly(True)
        self.mobile_edit.setReadOnly(True)
        self.alternate_edit.setReadOnly(True)
        self.result_list.setVisible(False)

    def _create_new_guest(self) -> None:
        dialog = GuestFormDialog(self.database, parent=self)
        if dialog.exec():
            guest = dialog.created_guest
            if guest is not None:
                self.selected_guest_id = guest.id
                self.guest_name_edit.setText(guest.guest_name)
                self.mobile_edit.setText(guest.mobile_number)
                self.alternate_edit.setText(guest.alternate_number or "")
                self.guest_name_edit.setReadOnly(True)
                self.mobile_edit.setReadOnly(True)
                self.alternate_edit.setReadOnly(True)

    def clear(self) -> None:
        self.selected_guest_id = None
        for edit in (self.guest_name_edit, self.mobile_edit, self.alternate_edit):
            edit.clear()
            edit.setReadOnly(False)
        self.result_list.clear()
        self.result_list.setVisible(False)

    def guest_data(self) -> dict:
        return {
            "guest_name": self.guest_name_edit.text(),
            "mobile_number": self.mobile_edit.text(),
            "alternate_number": self.alternate_edit.text(),
        }

    def resolve_guest_id(self) -> tuple[int | None, str]:
        """Return (guest_id, error_message) resolving the selected/new guest.

        Applies duplicate detection: if the mobile matches an existing guest
        that was not explicitly selected, ask whether to reuse it.
        """
        if self.selected_guest_id is not None:
            return self.selected_guest_id, ""

        name = self.guest_name_edit.text().strip()
        mobile = self.mobile_edit.text().strip()
        if not name:
            return None, "Guest Name is required."
        if not mobile:
            return None, "Mobile Number is required."

        with self.database.session_scope() as session:
            existing = guest_service.find_guest_by_mobile(session, mobile)
            if existing is not None:
                answer = QMessageBox.question(
                    self,
                    "Guest Already Exists",
                    f"A guest already exists with this mobile number:\n\n"
                    f"Name: {existing.guest_name}\nMobile: {existing.mobile_number}\n\n"
                    f"Use the existing guest?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self.selected_guest_id = existing.id
                    return existing.id, ""
            with self.database.session_scope() as session:
                guest = guest_service.create_guest(
                    session,
                    guest_name=name,
                    mobile_number=mobile,
                    alternate_number=self.alternate_edit.text(),
                )
            self.selected_guest_id = guest.id
            return guest.id, ""

    def fill_from_guest(self, guest_id: int) -> None:
        with self.database.session_scope() as session:
            guest = guest_service.get_guest(session, guest_id)
        if guest is None:
            return
        self.selected_guest_id = guest.id
        self.guest_name_edit.setText(guest.guest_name)
        self.mobile_edit.setText(guest.mobile_number)
        self.alternate_edit.setText(guest.alternate_number or "")
        self.guest_name_edit.setReadOnly(True)
        self.mobile_edit.setReadOnly(True)
        self.alternate_edit.setReadOnly(True)
