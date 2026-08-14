"""Booking details dialog.

Shows every booking field and offers status-appropriate actions:
Reserved -> Check-in / Cancel / No-show / Edit
Checked-in -> Check-out (with financial summary)
View-only otherwise. Also shows the full Charges & Payments section
(payments, manual charges, discount) for every booking.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time as dtime
from typing import Callable

from PySide6.QtCore import QTime, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import BookingStatus
from app.database.database import Database
from app.database.models import BookingCharge
from app.services import booking_service, financial_service, invoice_service
from app.ui.formatters import format_datetime, format_date_time, format_money
from app.ui.widgets.financial_summary import FinancialSummaryWidget
from app.ui.widgets.status_badge import make_status_badge

logger = logging.getLogger(__name__)

_STATUS = {status.value: status for status in BookingStatus}


class _CheckInTimeDialog(QDialog):
    def __init__(self, default_time: dtime, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("Check-in Time")
        self.setModal(True)
        layout = QVBoxLayout(self)
        label = QLabel("Confirm the actual check-in time:")
        layout.addWidget(label)
        self.time_edit = QTimeEdit(QTime(default_time.hour, default_time.minute))
        self.time_edit.setDisplayFormat("h:mm AP")
        layout.addWidget(self.time_edit)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Confirm")
        ok.setObjectName("ActionButton")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)

    def selected_time(self) -> dtime:
        qtime = self.time_edit.time()
        return dtime(qtime.hour(), qtime.minute())


class BookingDetailsDialog(QDialog):
    def __init__(
        self,
        database: Database,
        booking_id: int,
        on_changed: Callable[[], None] | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.booking_id = booking_id
        self.on_changed = on_changed

        self.setWindowTitle("Booking Details")
        self.setModal(True)
        self.setMinimumSize(660, 560)

        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Scrollable content so the dialog fits shorter screens.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(12)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        title_row = QHBoxLayout()
        self.booking_number_label = QLabel()
        self.booking_number_label.setObjectName("DialogRoomNumber")
        title_row.addWidget(self.booking_number_label)
        self.status_badge = make_status_badge(BookingStatus.RESERVED.value)
        title_row.addWidget(self.status_badge)
        title_row.addStretch(1)
        inner.addLayout(title_row)

        info_card = QFrame()
        info_card.setObjectName("DetailsCard")
        self.grid = QGridLayout(info_card)
        self.grid.setContentsMargins(16, 12, 16, 12)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(7)
        inner.addWidget(info_card)

        # --- Financial summary -------------------------------------------
        finance_heading = QLabel("Financial Summary")
        finance_heading.setObjectName("SectionHeading")
        inner.addWidget(finance_heading)

        self.finance_widget = FinancialSummaryWidget()
        inner.addWidget(self.finance_widget)

        finance_row = QHBoxLayout()
        finance_row.setSpacing(8)
        self.add_payment_button = QPushButton("+ Payment")
        self.add_payment_button.setObjectName("ActionButton")
        self.add_payment_button.clicked.connect(self._add_payment)
        finance_row.addWidget(self.add_payment_button)
        self.add_charge_button = QPushButton("+ Charge")
        self.add_charge_button.setObjectName("SecondaryButton")
        self.add_charge_button.clicked.connect(self._add_charge)
        finance_row.addWidget(self.add_charge_button)
        self.discount_button = QPushButton("Discount")
        self.discount_button.setObjectName("SecondaryButton")
        self.discount_button.clicked.connect(self._set_discount)
        finance_row.addWidget(self.discount_button)
        finance_row.addStretch(1)
        inner.addLayout(finance_row)

        # --- Charges table ----------------------------------------------
        charges_heading = QLabel("Charges")
        charges_heading.setObjectName("SectionHeading")
        inner.addWidget(charges_heading)

        self.charges_table = QTableWidget(0, 5)
        self.charges_table.setHorizontalHeaderLabels(
            ["Description", "Type", "Qty", "Unit", "Amount"]
        )
        self.charges_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.charges_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.charges_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.charges_table.verticalHeader().setVisible(False)
        header = self.charges_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.charges_table.setMaximumHeight(150)
        inner.addWidget(self.charges_table)

        # --- Payments table ---------------------------------------------
        payments_heading = QLabel("Payments")
        payments_heading.setObjectName("SectionHeading")
        inner.addWidget(payments_heading)

        self.payments_table = QTableWidget(0, 5)
        self.payments_table.setHorizontalHeaderLabels(
            ["Date", "Method", "Amount", "Ref. No.", "Status"]
        )
        self.payments_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.payments_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.payments_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.payments_table.verticalHeader().setVisible(False)
        header = self.payments_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.payments_table.setMaximumHeight(150)
        inner.addWidget(self.payments_table)

        self.reverse_payment_button = QPushButton("Reverse Payment")
        self.reverse_payment_button.setObjectName("SecondaryButton")
        self.reverse_payment_button.clicked.connect(self._reverse_payment)
        reverse_row = QHBoxLayout()
        reverse_row.addWidget(self.reverse_payment_button)
        reverse_row.addStretch(1)
        inner.addLayout(reverse_row)

        # --- Status history --------------------------------------------
        history_heading = QLabel("Status History")
        history_heading.setObjectName("SectionHeading")
        inner.addWidget(history_heading)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setHorizontalHeaderLabels(
            ["Date & Time", "From", "To", "Note"]
        )
        self.history_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.verticalHeader().setVisible(False)
        history_header = self.history_table.horizontalHeader()
        history_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        history_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.history_table.setMaximumHeight(140)
        inner.addWidget(self.history_table)

        self.action_row = QHBoxLayout()
        self.action_row.addStretch(1)
        inner.addLayout(self.action_row)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _detail(self, row: int, title: str, value: str) -> None:
        label = QLabel(title)
        label.setProperty("detailLabel", True)
        self.grid.addWidget(label, row, 0)
        value_label = QLabel(value)
        value_label.setProperty("detailValue", True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)
        self.grid.addWidget(value_label, row, 1)

    # ---------------------------------------------------------------- load

    def _load(self) -> None:
        with self.database.session_scope() as session:
            booking = booking_service.get_booking(session, self.booking_id)
            if booking is None:
                self.reject()
                return
            self.booking = booking
            guest = booking.guest
            room = booking.room
            source = booking.source
            summary = financial_service.get_financial_summary(session, self.booking_id)
            charges = (
                session.query(BookingCharge)
                .filter(BookingCharge.booking_id == self.booking_id)
                .order_by(BookingCharge.id)
                .all()
            )
            payments = financial_service.get_payment_history(session, self.booking_id)
            history = booking_service.get_booking_status_history(session, self.booking_id)

        self.booking_number_label.setText(booking.booking_number)
        self.status_badge.setText(_STATUS[booking.status].label)
        self.status_badge.setStyleSheet(
            make_status_badge(booking.status).styleSheet()
        )

        rows = [
            ("Guest", guest.guest_name if guest else "—"),
            ("Mobile", guest.mobile_number if guest else "—"),
            ("Room", f"Room {room.room_number} ({room.room_type})" if room else "—"),
            ("Check-in", format_date_time(booking.check_in_date, booking.check_in_time)),
            ("Check-out", format_date_time(booking.check_out_date, booking.check_out_time)),
            ("Adults / Children", f"{booking.adults} / {booking.children}"),
            ("Booking Source", source.name if source else "—"),
        ]
        from app.services.booking_source_service import is_ota_paid_online_source

        if source is not None and is_ota_paid_online_source(source.name):
            rows.append(("Payment Arrangement", "Paid Online" if booking.paid_online else "Pay at Hotel"))
        rows.extend([
            ("Room Rate", format_money(booking.room_rate)),
            ("Extra Person Charge", format_money(booking.extra_person_charge)),
            ("Early Check-in Charge", format_money(booking.early_check_in_charge)),
            ("Late Check-out Charge", format_money(booking.late_check_out_charge)),
            ("Special Notes", booking.special_notes or "—"),
            ("Created", format_datetime(booking.created_at)),
            ("Last Updated", format_datetime(booking.updated_at)),
        ])
        if booking.status == BookingStatus.CANCELLED.value:
            rows.append(("Cancelled", f"{format_datetime(booking.cancelled_at)} — {booking.cancellation_reason} (by {booking.cancelled_by or 'Reception'})"))
        if booking.status == BookingStatus.NO_SHOW.value:
            rows.append(("No-show", f"{format_datetime(booking.no_show_at)} — {booking.no_show_reason or 'No reason given'}"))
        if booking.status == BookingStatus.CHECKED_OUT.value:
            rows.append(("Actual Check-out", format_datetime(booking.actual_check_out_at)))
        if booking.status == BookingStatus.DELETED.value:
            rows.append(("Deleted", f"{format_datetime(booking.deleted_at)} — {booking.deletion_reason or 'No reason given'} (by {booking.deleted_by or 'Reception'})"))

        for row, (title, value) in enumerate(rows):
            self._detail(row, title, value)

        self.finance_widget.load(summary)
        self._render_charges(charges)
        self._render_payments(payments)
        self._render_history(history)

        self._build_actions()

    def _render_history(self, history: list) -> None:
        self.history_table.setRowCount(0)
        for row_index, entry in enumerate(history):
            self.history_table.insertRow(row_index)
            from_text = self._status_label(entry.old_status)
            to_text = self._status_label(entry.new_status)
            values = [
                format_datetime(entry.changed_at),
                from_text,
                to_text,
                entry.note or "—",
            ]
            for col, value in enumerate(values):
                self.history_table.setItem(row_index, col, QTableWidgetItem(value))
        if not history:
            self.history_table.setRowCount(1)
            item = QTableWidgetItem("No status changes recorded yet")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.history_table.setItem(0, 0, item)

    @staticmethod
    def _status_label(value: str) -> str:
        if not value:
            return "—"
        try:
            return _STATUS[value].label
        except KeyError:
            return value.title()

    def _render_charges(self, charges: list) -> None:
        from app.core.constants import ChargeType

        self.charges_table.setRowCount(0)
        for row_index, charge in enumerate(charges):
            self.charges_table.insertRow(row_index)
            try:
                type_label = ChargeType(charge.charge_type).label
            except ValueError:
                type_label = charge.charge_type
            values = [
                charge.description,
                type_label,
                str(charge.quantity),
                format_money(charge.unit_amount),
                format_money(charge.total_amount),
            ]
            for col, value in enumerate(values):
                self.charges_table.setItem(row_index, col, QTableWidgetItem(value))

    def _render_payments(self, payments: list) -> None:
        from app.core.constants import PaymentMethod, PaymentRecordStatus

        self.payments_table.setRowCount(0)
        for row_index, payment in enumerate(payments):
            self.payments_table.insertRow(row_index)
            try:
                method_label = PaymentMethod(payment.payment_method).label
            except ValueError:
                method_label = payment.payment_method
            try:
                status_label = PaymentRecordStatus(payment.status).label
            except ValueError:
                status_label = payment.status
            values = [
                format_date_time(payment.payment_date, None),
                method_label,
                format_money(payment.amount),
                payment.reference_number or "—",
                status_label,
            ]
            for col, value in enumerate(values):
                self.payments_table.setItem(row_index, col, QTableWidgetItem(value))

    def _clear_actions(self) -> None:
        while self.action_row.count():
            item = self.action_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_actions(self) -> None:
        self._clear_actions()
        status = self.booking.status

        if status == BookingStatus.RESERVED.value or status == BookingStatus.NEW.value:
            check_in = QPushButton("Check-in")
            check_in.setObjectName("ActionButton")
            check_in.clicked.connect(self._check_in)
            self.action_row.addWidget(check_in)

            edit = QPushButton("Edit")
            edit.setObjectName("SecondaryButton")
            edit.clicked.connect(self._edit_booking)
            self.action_row.addWidget(edit)

            cancel = QPushButton("Cancel Booking")
            cancel.setObjectName("SecondaryButton")
            cancel.clicked.connect(self._cancel_booking)
            self.action_row.addWidget(cancel)

            no_show = QPushButton("No-show")
            no_show.setObjectName("SecondaryButton")
            no_show.clicked.connect(self._mark_no_show)
            self.action_row.addWidget(no_show)

        elif status == BookingStatus.CHECKED_IN.value:
            check_out = QPushButton("Check-out")
            check_out.setObjectName("ActionButton")
            check_out.clicked.connect(self._check_out)
            self.action_row.addWidget(check_out)

        elif status == BookingStatus.CHECKED_OUT.value:
            invoice_button = QPushButton("Generate Invoice")
            invoice_button.setObjectName("ActionButton")
            invoice_button.clicked.connect(self._generate_invoice)
            self.action_row.addWidget(invoice_button)

        if status != BookingStatus.DELETED.value:
            delete_button = QPushButton("Delete Booking")
            delete_button.setObjectName("DangerButton")
            delete_button.clicked.connect(self._delete_booking)
            self.action_row.addWidget(delete_button)

    # ------------------------------------------------------------- actions

    def _generate_invoice(self) -> None:
        from app.ui.dialogs.invoice_dialog import InvoiceDialog

        try:
            with self.database.session_scope() as session:
                invoice = invoice_service.get_or_create_draft_invoice(session, self.booking.id)
        except invoice_service.DuplicateFinalizedInvoiceError as exc:
            answer = QMessageBox.information(
                self,
                "Invoice Already Exists",
                "Invoice already exists.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Open,
                QMessageBox.StandardButton.Open,
            )
            if answer == QMessageBox.StandardButton.Open:
                dialog = InvoiceDialog(self.database, exc.invoice.id, parent=self)
                dialog.exec()
            return
        except invoice_service.InvoiceStateError as exc:
            QMessageBox.warning(self, "Cannot Generate Invoice", str(exc))
            return
        except Exception:
            logger.exception("Invoice generation failed")
            QMessageBox.critical(self, "Error", "Could not generate the invoice. See logs for details.")
            return
        dialog = InvoiceDialog(self.database, invoice.id, on_changed=self._notify, parent=self)
        dialog.exec()

    def _check_in(self) -> None:
        time_dialog = _CheckInTimeDialog(dtime(datetime.now().hour, datetime.now().minute), self)
        if not time_dialog.exec():
            return
        selected_time = time_dialog.selected_time()
        guest_name = self.booking.guest.guest_name if self.booking.guest else ""
        answer = QMessageBox.question(
            self,
            "Confirm Check-in",
            f"Check in guest {guest_name} into Room {self.booking.room.room_number if self.booking.room else ''}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.database.session_scope() as session:
                booking_service.check_in_booking(
                    session,
                    self.booking.id,
                    check_in_date=date.today(),
                    check_in_time=selected_time,
                )
        except Exception:
            logger.exception("Check-in failed")
            QMessageBox.critical(self, "Error", "Check-in failed. See logs for details.")
            return
        self._load()
        self._notify()

    def _check_out(self) -> None:
        from app.ui.dialogs.checkout_dialog import CheckOutDialog

        dialog = CheckOutDialog(self.database, self.booking.id, parent=self)
        if dialog.exec():
            self._load()
            self._notify()

    def _cancel_booking(self) -> None:
        from app.ui.dialogs.reason_dialog import ReasonPromptDialog

        dialog = ReasonPromptDialog("Cancel Booking", f"Cancel booking {self.booking.booking_number}?")
        if not dialog.exec():
            return
        try:
            with self.database.session_scope() as session:
                booking_service.cancel_booking(session, self.booking.id, dialog.reason())
        except Exception:
            logger.exception("Cancellation failed")
            QMessageBox.critical(self, "Error", "Cancellation failed. See logs for details.")
            return
        self._load()
        self._notify()

    def _mark_no_show(self) -> None:
        from app.ui.dialogs.reason_dialog import ReasonPromptDialog

        dialog = ReasonPromptDialog(
            "No-show", f"Mark booking {self.booking.booking_number} as no-show?", require_reason=False
        )
        if not dialog.exec():
            return
        try:
            with self.database.session_scope() as session:
                booking_service.mark_no_show(session, self.booking.id, dialog.reason())
        except Exception:
            logger.exception("No-show failed")
            QMessageBox.critical(self, "Error", "Could not mark as no-show. See logs for details.")
            return
        self._load()
        self._notify()

    def _delete_booking(self) -> None:
        from app.ui.dialogs.reason_dialog import ReasonPromptDialog

        dialog = ReasonPromptDialog(
            "Delete Booking",
            f"Delete booking {self.booking.booking_number}?\n\n"
            "The booking will be removed from all reports, payment counts and "
            "dashboards. It will remain only in the deleted-booking history.",
        )
        if not dialog.exec():
            return
        try:
            with self.database.session_scope() as session:
                booking_service.delete_booking(session, self.booking.id, dialog.reason())
        except Exception:
            logger.exception("Booking deletion failed")
            QMessageBox.critical(self, "Error", "Could not delete the booking. See logs for details.")
            return
        self._load()
        self._notify()

    def _edit_booking(self) -> None:
        from app.ui.dialogs.booking_form_dialog import BookingFormDialog

        dialog = BookingFormDialog(self.database, on_changed=self._notify, editing_booking_id=self.booking.id, parent=self)
        if dialog.exec():
            self._load()

    # -------------------------------------------------------- financial UI

    def _add_payment(self) -> None:
        from app.ui.dialogs.add_payment_dialog import AddPaymentDialog

        dialog = AddPaymentDialog(self.database, self.booking.id, parent=self)
        if dialog.exec():
            self._load()
            self._notify()

    def _add_charge(self) -> None:
        from app.ui.dialogs.add_charge_dialog import AddChargeDialog

        dialog = AddChargeDialog(self.database, self.booking.id, parent=self)
        if dialog.exec():
            self._load()
            self._notify()

    def _set_discount(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        with self.database.session_scope() as session:
            summary = financial_service.get_financial_summary(session, self.booking.id)
        amount, ok = QInputDialog.getDouble(
            self,
            "Set Discount",
            f"Discount amount (max ₹{summary.subtotal:,.2f}):",
            value=float(summary.discount),
            min=0.0,
            max=float(summary.subtotal),
            decimals=2,
        )
        if not ok:
            return
        try:
            with self.database.session_scope() as session:
                financial_service.set_discount(session, self.booking.id, amount)
        except financial_service.ChargeValidationError as exc:
            QMessageBox.warning(self, "Invalid Discount", str(exc))
            return
        except Exception:
            logger.exception("Discount set failed")
            QMessageBox.critical(self, "Error", "Could not set the discount. See logs for details.")
            return
        self._load()
        self._notify()

    def _reverse_payment(self) -> None:
        row = self.payments_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Payment", "Select a payment from the table first.")
            return
        from app.ui.dialogs.reason_dialog import ReasonPromptDialog

        payment_id = self._payment_id_at(row)
        if payment_id is None:
            return
        dialog = ReasonPromptDialog("Reverse Payment", "Reverse this payment?")
        if not dialog.exec():
            return
        try:
            with self.database.session_scope() as session:
                financial_service.reverse_payment(session, payment_id, dialog.reason())
        except financial_service.PaymentValidationError as exc:
            QMessageBox.warning(self, "Cannot Reverse", str(exc))
            return
        except Exception:
            logger.exception("Payment reverse failed")
            QMessageBox.critical(self, "Error", "Could not reverse the payment. See logs for details.")
            return
        self._load()
        self._notify()

    def _payment_id_at(self, row: int) -> int | None:
        with self.database.session_scope() as session:
            payments = financial_service.get_payment_history(session, self.booking.id)
        if 0 <= row < len(payments):
            return payments[row].id
        return None

    def _notify(self) -> None:
        if self.on_changed is not None:
            self.on_changed()
