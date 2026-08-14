"""Add Charge dialog: add a manual charge (extra mattress / misc / other / room)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from app.core.constants import ChargeType
from app.database.database import Database
from app.services import financial_service

# Manual charge types reception can add from the charges table.
ADDABLE_CHARGE_TYPES = (
    ChargeType.EXTRA_MATTRESS,
    ChargeType.MISCELLANEOUS,
    ChargeType.OTHER,
    ChargeType.ROOM,
)


class AddChargeDialog(QDialog):
    def __init__(self, database: Database, booking_id: int, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.booking_id = booking_id

        self.setWindowTitle("Add Charge")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._build_ui()

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Charge Type"))
        self.type_combo = QComboBox()
        for charge_type in ADDABLE_CHARGE_TYPES:
            self.type_combo.addItem(charge_type.label, charge_type.value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        row.addWidget(self.type_combo, 1)
        layout.addLayout(row)

        self.desc_label = QLabel("Description *")
        self.desc_label.setProperty("detailLabel", True)
        layout.addWidget(self.desc_label)
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("e.g. Extra mattress")
        layout.addWidget(self.desc_edit)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Quantity"))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 100)
        self.quantity_spin.setValue(1)
        row.addWidget(self.quantity_spin)
        row.addSpacing(12)
        row.addWidget(self._field_label("Unit Amount (₹)"))
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0, 1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setGroupSeparatorShown(True)
        row.addWidget(self.amount_spin, 1)
        layout.addLayout(row)

        self.total_label = QLabel("Total: ₹0.00")
        self.total_label.setProperty("detailValue", True)
        layout.addWidget(self.total_label)

        self.amount_spin.valueChanged.connect(self._update_total)
        self.quantity_spin.valueChanged.connect(self._update_total)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Add Charge")
        save.setObjectName("ActionButton")
        save.clicked.connect(self._save)
        button_row.addWidget(cancel)
        button_row.addWidget(save)
        layout.addLayout(button_row)

        self._on_type_changed()

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _on_type_changed(self) -> None:
        charge_type = self.current_type()
        if charge_type == ChargeType.ROOM:
            self.desc_edit.setPlaceholderText("e.g. Same-day room charge")
        elif charge_type == ChargeType.EXTRA_MATTRESS:
            self.desc_edit.setPlaceholderText("e.g. Extra mattress")
        elif charge_type == ChargeType.MISCELLANEOUS:
            self.desc_edit.setPlaceholderText("e.g. Laundry, meals")
        else:
            self.desc_edit.setPlaceholderText("Description of the charge")

    def _update_total(self) -> None:
        total = self.quantity_spin.value() * self.amount_spin.value()
        self.total_label.setText(f"Total: ₹{total:,.2f}")

    def current_type(self) -> ChargeType:
        return ChargeType(self.type_combo.currentData())

    # -------------------------------------------------------------- save

    def _save(self) -> None:
        try:
            with self.database.session_scope() as session:
                financial_service.add_charge(
                    session,
                    booking_id=self.booking_id,
                    description=self.desc_edit.text(),
                    charge_type=self.current_type(),
                    quantity=self.quantity_spin.value(),
                    unit_amount=self.amount_spin.value(),
                )
        except financial_service.ChargeValidationError as exc:
            QMessageBox.warning(self, "Invalid Charge", str(exc))
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Charge save failed")
            QMessageBox.critical(self, "Error", "Could not add the charge. See logs for details.")
            return

        self.accept()
