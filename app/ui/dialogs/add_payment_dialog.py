"""Add Payment dialog: record a payment against a booking."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.constants import DEFAULT_PAYMENT_METHODS
from app.database.database import Database
from app.services import financial_service


class AddPaymentDialog(QDialog):
    def __init__(self, database: Database, booking_id: int, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.booking_id = booking_id

        self.setWindowTitle("Record Payment")
        self.setModal(True)
        self.setMinimumWidth(400)

        self._build_ui()
        self._load_balance()

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        balance_label = QLabel("Balance due")
        balance_label.setProperty("detailLabel", True)
        layout.addWidget(balance_label)
        self.balance_value = QLabel("—")
        self.balance_value.setObjectName("DialogRoomNumber")
        layout.addWidget(self.balance_value)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Amount (₹) *"))
        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.01, 1_000_000)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setGroupSeparatorShown(True)
        row.addWidget(self.amount_spin, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Payment Method"))
        self.method_combo = QComboBox()
        for method in DEFAULT_PAYMENT_METHODS:
            self.method_combo.addItem(method, method.lower())
        row.addWidget(self.method_combo, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Payment Date"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd-MM-yyyy")
        row.addWidget(self.date_edit, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(self._field_label("Reference No."))
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Optional (e.g. UTR no.)")
        row.addWidget(self.reference_edit, 1)
        layout.addLayout(row)

        notes_label = QLabel("Notes")
        notes_label.setProperty("detailLabel", True)
        layout.addWidget(notes_label)
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional")
        layout.addWidget(self.notes_edit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Record Payment")
        save.setObjectName("ActionButton")
        save.clicked.connect(self._save)
        button_row.addWidget(cancel)
        button_row.addWidget(save)
        layout.addLayout(button_row)

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _load_balance(self) -> None:
        with self.database.session_scope() as session:
            summary = financial_service.get_financial_summary(session, self.booking_id)
        from app.ui.formatters import format_money

        self.balance_value.setText(format_money(summary.remaining))

    # -------------------------------------------------------------- save

    def _save(self) -> None:
        amount = self.amount_spin.value()
        qdate = self.date_edit.date()
        payment_date = date(qdate.year(), qdate.month(), qdate.day())
        method = self.method_combo.currentData()

        try:
            with self.database.session_scope() as session:
                financial_service.record_payment(
                    session,
                    booking_id=self.booking_id,
                    amount=amount,
                    payment_method=method,
                    payment_date=payment_date,
                    reference_number=self.reference_edit.text(),
                    notes=self.notes_edit.text(),
                )
        except financial_service.OverPaymentError as exc:
            QMessageBox.warning(self, "Overpayment", str(exc))
            return
        except financial_service.PaymentValidationError as exc:
            QMessageBox.warning(self, "Invalid Payment", str(exc))
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Payment save failed")
            QMessageBox.critical(self, "Error", "Could not record the payment. See logs for details.")
            return

        self.accept()
