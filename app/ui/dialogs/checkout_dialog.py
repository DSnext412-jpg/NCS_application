"""Check-out dialog.

Shows the financial summary before confirming a check-out. A booking with a
remaining balance cannot be checked out (the payment must be collected first).
The actual check-out time is recorded, and a default late check-out charge
(editable) is auto-applied when the guest checks out several hours after the
scheduled check-out time.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime, timedelta

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
)

from app.core.config import KEY_LATE_CHECKOUT_CHARGE, KEY_LATE_CHECKOUT_GRACE_HOURS
from app.database.database import Database
from app.services import booking_service, financial_service, invoice_service, settings_service
from app.ui.formatters import format_date_time, format_money
from app.ui.widgets.financial_summary import FinancialSummaryWidget

logger = logging.getLogger(__name__)

_DEFAULT_CHECKOUT_TIME = dtime(11, 0)


class CheckOutDialog(QDialog):
    def __init__(self, database: Database, booking_id: int, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.booking_id = booking_id

        self.setWindowTitle("Check Out")
        self.setModal(True)
        self.setMinimumWidth(520)

        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        self.booking_label = QLabel()
        self.booking_label.setObjectName("DialogRoomNumber")
        self.booking_label.setWordWrap(True)
        layout.addWidget(self.booking_label)

        self.summary_widget = FinancialSummaryWidget()
        layout.addWidget(self.summary_widget)

        self.balance_warning = QLabel()
        self.balance_warning.setWordWrap(True)
        self.balance_warning.setStyleSheet(
            "color: #b91c1c; background: #fee2e2; border: 1px solid #fecaca;"
            " border-radius: 6px; padding: 8px; font-weight: 600;"
        )
        self.balance_warning.hide()
        layout.addWidget(self.balance_warning)

        row = QHBoxLayout()
        time_label = QLabel("Actual check-out time")
        time_label.setProperty("detailLabel", True)
        row.addWidget(time_label)
        self.time_edit = QTimeEdit(QTime.currentTime())
        self.time_edit.setDisplayFormat("h:mm AP")
        row.addWidget(self.time_edit, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        late_label = QLabel("Late check-out charge (₹)")
        late_label.setProperty("detailLabel", True)
        row.addWidget(late_label)
        self.late_spin = QDoubleSpinBox()
        self.late_spin.setRange(0, 1_000_000)
        self.late_spin.setDecimals(2)
        self.late_spin.setGroupSeparatorShown(True)
        row.addWidget(self.late_spin, 1)
        layout.addLayout(row)

        self.late_note = QLabel()
        self.late_note.setProperty("detailLabel", True)
        self.late_note.setWordWrap(True)
        self.late_note.hide()
        layout.addWidget(self.late_note)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        self.collect_btn = QPushButton("Collect Payment")
        self.collect_btn.setObjectName("ActionButton")
        self.collect_btn.clicked.connect(self._collect_payment)
        self.collect_btn.hide()
        button_row.addWidget(self.collect_btn)
        self.confirm_btn = QPushButton("Confirm Check-out")
        self.confirm_btn.setObjectName("ActionButton")
        self.confirm_btn.clicked.connect(self._confirm)
        button_row.addWidget(cancel)
        button_row.addWidget(self.confirm_btn)
        layout.addLayout(button_row)

    # ---------------------------------------------------------------- load

    def _load(self) -> None:
        with self.database.session_scope() as session:
            booking = booking_service.get_booking(session, self.booking_id)
            summary = financial_service.get_financial_summary(session, self.booking_id)
            self._grace_hours = float(
                settings_service.get_setting(session, KEY_LATE_CHECKOUT_GRACE_HOURS, "4") or "4"
            )
            self._default_charge = float(
                settings_service.get_setting(session, KEY_LATE_CHECKOUT_CHARGE, "300") or "300"
            )
        if booking is None:
            self.reject()
            return
        self._booking = booking

        guest_name = booking.guest.guest_name if booking.guest else ""
        room_number = booking.room.room_number if booking.room else ""
        self.booking_label.setText(
            f"{guest_name} • Room {room_number} • {booking.booking_number}"
        )
        self.summary_widget.load(summary)

        if summary.remaining > 0:
            self.balance_warning.setText(
                f"Cannot check out: this booking has a remaining balance of "
                f"{format_money(summary.remaining)}. Collect the payment to continue."
            )
            self.balance_warning.show()
            self.late_spin.setValue(0)
            self.confirm_btn.setEnabled(False)
            self.collect_btn.show()
            return

        self.collect_btn.hide()
        self.confirm_btn.setEnabled(True)
        self.balance_warning.hide()

        scheduled = datetime.combine(
            booking.check_out_date,
            booking.check_out_time or _DEFAULT_CHECKOUT_TIME,
        )
        qtime = self.time_edit.time()
        actual = datetime.combine(date.today(), dtime(qtime.hour(), qtime.minute()))
        is_late = actual >= scheduled + timedelta(hours=self._grace_hours)
        if is_late:
            self.late_spin.setValue(self._default_charge)
            self.late_note.setText(
                f"Guest is checking out more than {self._grace_hours:g} hours after the "
                f"scheduled check-out ({format_date_time(booking.check_out_date, booking.check_out_time)}). "
                f"Default late charge {format_money(self._default_charge)} applied — edit above if needed."
            )
            self.late_note.show()
        else:
            self.late_spin.setValue(0)
            self.late_note.hide()

    # -------------------------------------------------------------- action

    def _collect_payment(self) -> None:
        from app.ui.dialogs.add_payment_dialog import AddPaymentDialog

        dialog = AddPaymentDialog(self.database, self.booking_id, parent=self)
        if dialog.exec():
            self._load()

    def _confirm(self) -> None:
        qtime = self.time_edit.time()
        actual = datetime.combine(date.today(), dtime(qtime.hour(), qtime.minute()))
        try:
            with self.database.session_scope() as session:
                booking_service.update_booking(
                    session,
                    self.booking_id,
                    late_check_out_charge=self.late_spin.value(),
                )
                booking_service.check_out_booking(
                    session,
                    self.booking_id,
                    actual_check_out_at=actual,
                )
                invoice_service.ensure_invoice_for_checkout(session, self.booking_id)
        except Exception:
            logger.exception("Check-out failed")
            QMessageBox.critical(self, "Error", "Check-out failed. See logs for details.")
            return
        self.accept()
