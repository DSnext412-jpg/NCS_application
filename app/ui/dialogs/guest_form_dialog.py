"""Guest create/edit dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
)

from app.core.constants import DEFAULT_CITY, DEFAULT_COUNTRY, DEFAULT_STATE, ID_TYPES
from app.database.database import Database
from app.services import guest_service


class GuestFormDialog(QDialog):
    def __init__(self, database: Database, guest_id: int | None = None, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.guest_id = guest_id
        self.created_guest = None
        self._guest = None

        self.setWindowTitle("Edit Guest" if guest_id else "New Guest")
        self.setModal(True)
        self.setMinimumWidth(460)

        form = QFormLayout(self)
        form.setVerticalSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Guest Name *")
        form.addRow("Name *", self.name_edit)

        self.mobile_edit = QLineEdit()
        self.mobile_edit.setPlaceholderText("Mobile Number *")
        form.addRow("Mobile *", self.mobile_edit)

        self.alternate_edit = QLineEdit()
        form.addRow("Alternate", self.alternate_edit)

        self.address_edit = QLineEdit()
        form.addRow("Address", self.address_edit)

        self.city_edit = QLineEdit(DEFAULT_CITY)
        form.addRow("City", self.city_edit)

        self.state_edit = QLineEdit(DEFAULT_STATE)
        form.addRow("State", self.state_edit)

        self.country_edit = QLineEdit(DEFAULT_COUNTRY)
        form.addRow("Country", self.country_edit)

        self.id_type_combo = QComboBox()
        self.id_type_combo.addItem("", "")
        for id_type in ID_TYPES:
            self.id_type_combo.addItem(id_type, id_type)
        form.addRow("ID Type", self.id_type_combo)

        self.id_number_edit = QLineEdit()
        form.addRow("ID Number", self.id_number_edit)

        self.adults_spin = QSpinBox()
        self.adults_spin.setRange(0, 50)
        self.adults_spin.setValue(1)
        form.addRow("Adults", self.adults_spin)

        self.children_spin = QSpinBox()
        self.children_spin.setRange(0, 50)
        self.children_spin.setValue(0)
        form.addRow("Children", self.children_spin)

        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(70)
        form.addRow("Special Notes", self.notes_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        if guest_id:
            self._load(guest_id)

    def _load(self, guest_id: int) -> None:
        with self.database.session_scope() as session:
            guest = guest_service.get_guest(session, guest_id)
        if guest is None:
            self.reject()
            return
        self._guest = guest
        self.name_edit.setText(guest.guest_name)
        self.mobile_edit.setText(guest.mobile_number)
        self.alternate_edit.setText(guest.alternate_number or "")
        self.address_edit.setText(guest.address or "")
        self.city_edit.setText(guest.city or DEFAULT_CITY)
        self.state_edit.setText(guest.state or DEFAULT_STATE)
        self.country_edit.setText(guest.country or DEFAULT_COUNTRY)
        index = self.id_type_combo.findData(guest.id_type)
        if index >= 0:
            self.id_type_combo.setCurrentIndex(index)
        self.id_number_edit.setText(guest.id_number or "")
        self.adults_spin.setValue(int(guest.adults or 0))
        self.children_spin.setValue(int(guest.children or 0))
        self.notes_edit.setPlainText(guest.special_notes or "")

    def _save(self) -> None:
        data = dict(
            guest_name=self.name_edit.text(),
            mobile_number=self.mobile_edit.text(),
            alternate_number=self.alternate_edit.text(),
            address=self.address_edit.text(),
            city=self.city_edit.text(),
            state=self.state_edit.text(),
            country=self.country_edit.text(),
            id_type=self.id_type_combo.currentData() or "",
            id_number=self.id_number_edit.text(),
            adults=self.adults_spin.value(),
            children=self.children_spin.value(),
            special_notes=self.notes_edit.toPlainText(),
        )

        try:
            with self.database.session_scope() as session:
                if self._guest is not None:
                    guest = guest_service.update_guest(session, self._guest.id, **data)
                else:
                    existing = guest_service.find_guest_by_mobile(session, data["mobile_number"])
                    if existing is not None:
                        answer = QMessageBox.question(
                            self,
                            "Duplicate Guest",
                            f"A guest already exists with this mobile number:\n\n"
                            f"Name: {existing.guest_name}\nMobile: {existing.mobile_number}\n\n"
                            f"Create a new guest anyway?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                            QMessageBox.StandardButton.No,
                        )
                        if answer != QMessageBox.StandardButton.Yes:
                            return
                    guest = guest_service.create_guest(session, **data)
        except guest_service.GuestValidationError as exc:
            QMessageBox.warning(self, "Invalid Guest Details", str(exc))
            return
        except Exception:
            QMessageBox.critical(self, "Error", "Could not save the guest. See logs for details.")
            import logging

            logging.getLogger(__name__).exception("Guest save failed")
            return

        self.created_guest = guest
        self.accept()
