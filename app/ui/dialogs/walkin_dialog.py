"""Quick walk-in dialog.

Minimal fields for speed: guest details, a currently available room,
check-out date/time, room rate and optional charges. Check-in defaults to
now. An optional advance payment can be recorded at walk-in time. On save
the booking becomes CHECKED_IN and the room OCCUPIED. Available rooms are
re-filtered when the stay dates change.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime
from typing import Callable

from PySide6.QtCore import QDate, QTime
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
    QScrollArea,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import DEFAULT_PAYMENT_METHODS, ChargeType
from app.database.database import Database
from app.services import booking_service, booking_source_service, financial_service, guest_service, room_service


class WalkInDialog(QDialog):
    def __init__(
        self,
        database: Database,
        on_changed: Callable[[], None] | None = None,
        preset_room_id: int | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed
        self.preset_room_id = preset_room_id
        self.walkin_source_id = None
        self._rooms_loaded = False

        self.setWindowTitle("Walk-in")
        self.setModal(True)
        self.setMinimumSize(520, 560)

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

        from app.ui.widgets.guest_section import GuestSection

        self.guest_section = GuestSection(self.database)
        inner.addWidget(self.guest_section)

        inner.addWidget(self._heading("Stay"))

        self.room_combo = QComboBox()
        inner.addWidget(self.room_combo)

        now = datetime.now()
        row = QHBoxLayout()
        row.addWidget(self._field_label("Check-in"))
        self.check_in_label = QLabel(now.strftime("%d %b %Y, %I:%M %p"))
        self.check_in_label.setProperty("detailValue", True)
        row.addWidget(self.check_in_label)
        row.addStretch(1)
        inner.addLayout(row)

        out_row = QHBoxLayout()
        self.check_out_date = QDateEdit(QDate.currentDate().addDays(1))
        self.check_out_date.setCalendarPopup(True)
        self.check_out_time = QTimeEdit(QTime(12, 0))
        self.check_out_time.setDisplayFormat("h:mm AP")
        out_row.addWidget(self._field_label("Check-out Date"))
        out_row.addWidget(self.check_out_date, 1)
        out_row.addWidget(self._field_label("Time"))
        out_row.addWidget(self.check_out_time)
        inner.addLayout(out_row)

        inner.addWidget(self._heading("Charges"))

        rate_row = QHBoxLayout()
        self.rate_spin = self._money_spin("₹ Room Rate *")
        self.extra_spin = self._money_spin("₹ Extra Person")
        rate_row.addWidget(self.rate_spin)
        rate_row.addWidget(self.extra_spin)
        inner.addLayout(rate_row)

        inner.addWidget(self._heading("Optional Charge"))
        charge_row = QHBoxLayout()
        self.charge_desc_edit = QLineEdit()
        self.charge_desc_edit.setPlaceholderText("Description (e.g. extra mattress)")
        self.charge_amount_spin = self._money_spin("₹ Amount")
        charge_row.addWidget(self.charge_desc_edit, 1)
        charge_row.addWidget(self.charge_amount_spin)
        inner.addLayout(charge_row)

        inner.addWidget(self._heading("Advance Payment (optional)"))
        advance_row = QHBoxLayout()
        self.advance_spin = self._money_spin("₹ Amount")
        self.advance_method = QComboBox()
        for method in DEFAULT_PAYMENT_METHODS:
            self.advance_method.addItem(method, method.lower())
        advance_row.addWidget(self._field_label("Method"))
        advance_row.addWidget(self.advance_method, 1)
        advance_row.addWidget(self.advance_spin)
        inner.addLayout(advance_row)

        notes_row = QHBoxLayout()
        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("Special notes (optional)")
        self.notes_edit.setFixedHeight(60)
        inner.addWidget(self.notes_edit)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryButton")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        save_button = QPushButton("Complete Walk-in")
        save_button.setObjectName("ActionButton")
        save_button.clicked.connect(self._save)
        button_row.addWidget(save_button)
        layout.addLayout(button_row)

        self.check_out_date.dateChanged.connect(self._on_stay_changed)
        self.check_out_time.timeChanged.connect(self._on_stay_changed)

        self._load_rooms_and_source(now)

    def _heading(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionHeading")
        return label

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _money_spin(self, prefix: str) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setDecimals(2)
        spin.setPrefix(prefix + " ")
        spin.setGroupSeparatorShown(True)
        return spin

    def _on_stay_changed(self) -> None:
        if self._rooms_loaded:
            self._load_rooms_and_source(datetime.now())

    def _load_rooms_and_source(self, now: datetime) -> None:
        check_in_date = now.date()
        check_in_time = dtime(now.hour, now.minute)
        check_out_date = self.check_out_date.date().toPython()
        check_out_time = self.check_out_time.time().toPython()

        with self.database.session_scope() as session:
            rooms = room_service.get_all_rooms(session)
            walkin_source = booking_source_service.get_source_by_name(session, "Walk-in")
            available_rooms = []
            for room in rooms:
                ok, _ = booking_service.is_room_available(
                    session,
                    room.id,
                    check_in_date,
                    check_in_time,
                    check_out_date,
                    check_out_time,
                )
                if ok:
                    available_rooms.append(room)
            self.walkin_source_id = walkin_source.id if walkin_source else None

        previous = self.room_combo.currentData()
        self.room_combo.blockSignals(True)
        self.room_combo.clear()
        if not available_rooms:
            self.room_combo.addItem("No rooms available", None)
        else:
            for room in available_rooms:
                self.room_combo.addItem(f"Room {room.room_number} ({room.room_type})", room.id)
        self.room_combo.blockSignals(False)

        index = -1
        if self.preset_room_id is not None:
            index = self.room_combo.findData(self.preset_room_id)
        if index < 0:
            index = self.room_combo.findData(previous)
        if index >= 0:
            self.room_combo.setCurrentIndex(index)
        self._rooms_loaded = True

    def _save(self) -> None:
        guest_id, error = self.guest_section.resolve_guest_id()
        if error:
            QMessageBox.warning(self, "Missing Information", error)
            return

        room_id = self.room_combo.currentData()
        if room_id is None:
            QMessageBox.warning(self, "Missing Information", "No room is available for a walk-in right now.")
            return
        if self.walkin_source_id is None:
            QMessageBox.warning(self, "Missing Information", "Walk-in booking source is not configured.")
            return

        now = datetime.now()
        check_out_date = self.check_out_date.date().toPython()
        check_out_time = self.check_out_time.time().toPython()

        try:
            with self.database.session_scope() as session:
                booking = booking_service.create_walkin(
                    session,
                    guest_id=guest_id,
                    room_id=room_id,
                    booking_source_id=self.walkin_source_id,
                    check_in_date=now.date(),
                    check_in_time=dtime(now.hour, now.minute),
                    check_out_date=check_out_date,
                    check_out_time=check_out_time,
                    room_rate=self.rate_spin.value(),
                    extra_person_charge=self.extra_spin.value(),
                    special_notes=self.notes_edit.toPlainText(),
                    advance_payment=self.advance_spin.value(),
                    advance_payment_method=self.advance_method.currentData(),
                )
                if self.charge_desc_edit.text().strip() and self.charge_amount_spin.value() > 0:
                    financial_service.add_charge(
                        session,
                        booking_id=booking.id,
                        description=self.charge_desc_edit.text().strip(),
                        charge_type=ChargeType.MISCELLANEOUS,
                        quantity=1,
                        unit_amount=self.charge_amount_spin.value(),
                    )
        except booking_service.RoomNotAvailableError as exc:
            QMessageBox.warning(self, "Room Not Available", str(exc))
            return
        except financial_service.OverPaymentError as exc:
            QMessageBox.warning(self, "Advance Payment", str(exc))
            return
        except (booking_service.BookingValidationError, guest_service.GuestValidationError) as exc:
            QMessageBox.warning(self, "Invalid Booking", str(exc))
            return
        except Exception:
            QMessageBox.critical(self, "Error", "Could not complete the walk-in. See logs for details.")
            import logging

            logging.getLogger(__name__).exception("Walk-in save failed")
            return

        if self.on_changed is not None:
            self.on_changed()
        self.accept()
