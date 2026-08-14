"""New reservation / edit booking dialog.

Organized into clear sections: Guest, Stay, Booking, Notes. Room rates and
all charges are entered manually by reception and stored on the booking.
"""

from __future__ import annotations

from datetime import date, time as dtime
from typing import Callable

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import DEFAULT_PAYMENT_METHODS
from app.database.database import Database
from app.services import booking_service, booking_source_service, guest_service, room_service
from app.ui.widgets.calendar_date_edit import CalendarDateEdit


class BookingFormDialog(QDialog):
    def __init__(
        self,
        database: Database,
        on_changed: Callable[[], None] | None = None,
        editing_booking_id: int | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.on_changed = on_changed
        self.editing_booking_id = editing_booking_id
        self._booking = None
        self._rooms_loaded = False
        self._already_saved_this_session = False

        self.setWindowTitle("Edit Reservation" if editing_booking_id else "New Booking")
        self.setModal(True)
        self.setMinimumSize(540, 560)

        self._build_ui()
        if editing_booking_id:
            self._load_for_edit(editing_booking_id)

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

        # --- Guest ---
        from app.ui.widgets.guest_section import GuestSection

        self.guest_section = GuestSection(self.database)
        inner.addWidget(self.guest_section)

        # --- Stay ---
        inner.addWidget(self._section_label("Stay"))
        self.room_combo = QComboBox()
        inner.addWidget(self.room_combo)

        date_row = QHBoxLayout()
        self.check_in_date = CalendarDateEdit(QDate.currentDate())
        self.check_in_time = QTimeEdit(QTime(12, 0))
        self.check_in_time.setDisplayFormat("h:mm AP")
        date_row.addWidget(self._field_label("Check-in Date"))
        date_row.addWidget(self.check_in_date, 1)
        date_row.addWidget(self._field_label("Time"))
        date_row.addWidget(self.check_in_time)
        inner.addLayout(date_row)

        date_row2 = QHBoxLayout()
        self.check_out_date = CalendarDateEdit(QDate.currentDate().addDays(1))
        self.check_out_time = QTimeEdit(QTime(12, 0))
        self.check_out_time.setDisplayFormat("h:mm AP")
        date_row2.addWidget(self._field_label("Check-out Date"))
        date_row2.addWidget(self.check_out_date, 1)
        date_row2.addWidget(self._field_label("Time"))
        date_row2.addWidget(self.check_out_time)
        inner.addLayout(date_row2)

        people_row = QHBoxLayout()
        self.adults_spin = QSpinBox()
        self.adults_spin.setRange(0, 50)
        self.adults_spin.setValue(1)
        self.children_spin = QSpinBox()
        self.children_spin.setRange(0, 50)
        self.children_spin.setValue(0)
        people_row.addWidget(self._field_label("Adults"))
        people_row.addWidget(self.adults_spin)
        people_row.addSpacing(12)
        people_row.addWidget(self._field_label("Children"))
        people_row.addWidget(self.children_spin)
        people_row.addStretch(1)
        inner.addLayout(people_row)

        # --- Booking ---
        inner.addWidget(self._section_label("Booking"))
        self.source_combo = QComboBox()
        inner.addWidget(self.source_combo)

        # --- Paid Online (OTA sources only, new bookings) ---
        self.paid_online_box = None
        self.paid_online_combo = None
        if not self.editing_booking_id:
            self.paid_online_box = QWidget()
            paid_online_inner = QHBoxLayout(self.paid_online_box)
            paid_online_inner.setContentsMargins(0, 0, 0, 0)
            self.paid_online_combo = QComboBox()
            self.paid_online_combo.addItem("Pay at Hotel", False)
            self.paid_online_combo.addItem("Paid Online (guest already paid the OTA)", True)
            self.paid_online_combo.currentIndexChanged.connect(self._update_advance_visibility)
            paid_online_inner.addWidget(self._field_label("Payment Arrangement"))
            paid_online_inner.addWidget(self.paid_online_combo, 1)
            inner.addWidget(self.paid_online_box)

        charges_grid = QHBoxLayout()
        self.rate_spin = self._money_spin("₹ Room Rate *", minimum=0)
        self.extra_spin = self._money_spin("₹ Extra Person", minimum=0)
        charges_grid.addWidget(self.rate_spin)
        charges_grid.addWidget(self.extra_spin)
        inner.addLayout(charges_grid)

        charges_grid2 = QHBoxLayout()
        self.early_spin = self._money_spin("₹ Early Check-in", minimum=0)
        self.late_spin = self._money_spin("₹ Late Check-out", minimum=0)
        charges_grid2.addWidget(self.early_spin)
        charges_grid2.addWidget(self.late_spin)
        inner.addLayout(charges_grid2)

        # --- Notes ---
        inner.addWidget(self._section_label("Special Notes"))
        self.notes_edit = QTextEdit()
        self.notes_edit.setFixedHeight(80)
        inner.addWidget(self.notes_edit)

        # --- Advance payment (new bookings only) ---
        if not self.editing_booking_id:
            self.advance_heading = self._section_label("Advance Payment (optional)")
            inner.addWidget(self.advance_heading)
            advance_row = QHBoxLayout()
            self.advance_spin = self._money_spin("₹ Amount", minimum=0)
            self.advance_method = QComboBox()
            for method in DEFAULT_PAYMENT_METHODS:
                self.advance_method.addItem(method, method.lower())
            advance_row.addWidget(self._field_label("Method"))
            advance_row.addWidget(self.advance_method, 1)
            advance_row.addWidget(self.advance_spin)
            inner.addLayout(advance_row)
        else:
            self.advance_heading = None
            self.advance_spin = None
            self.advance_method = None

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryButton")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        save_button = QPushButton("Save Reservation")
        save_button.setObjectName("SecondaryButton")
        save_button.clicked.connect(self._save_reservation)
        button_row.addWidget(save_button)
        self.checkin_button = QPushButton("Save & Check-in")
        self.checkin_button.setObjectName("ActionButton")
        self.checkin_button.clicked.connect(self._save_and_check_in)
        self.checkin_button.setVisible(not self.editing_booking_id)
        button_row.addWidget(self.checkin_button)
        layout.addLayout(button_row)

        self.check_in_date.dateChanged.connect(self._on_stay_changed)
        self.check_in_time.timeChanged.connect(self._on_stay_changed)
        self.check_out_date.dateChanged.connect(self._on_stay_changed)
        self.check_out_time.timeChanged.connect(self._on_stay_changed)

        self._load_rooms_and_sources()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionHeading")
        return label

    def _field_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _money_spin(self, prefix: str, minimum: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, 1_000_000)
        spin.setDecimals(2)
        spin.setPrefix(prefix + " ")
        spin.setGroupSeparatorShown(True)
        return spin

    def _load_rooms_and_sources(self) -> None:
        with self.database.session_scope() as session:
            self.all_rooms = room_service.get_all_rooms(session)
            sources = booking_source_service.get_sources(session)
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for source in sources:
            self.source_combo.addItem(source.name, source.id)
        self.source_combo.blockSignals(False)
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self._refresh_room_list()
        self._update_paid_online_visibility()

    def _on_source_changed(self) -> None:
        self._update_paid_online_visibility()

    def _update_paid_online_visibility(self) -> None:
        """Show the paid-online choice only for OTA sources (not Booking.com)."""
        if self.paid_online_box is None:
            return
        source_name = self.source_combo.currentText()
        is_ota = booking_source_service.is_ota_paid_online_source(source_name)
        self.paid_online_box.setVisible(is_ota)
        if not is_ota:
            self.paid_online_combo.setCurrentIndex(0)
        self._update_advance_visibility()

    def _update_advance_visibility(self) -> None:
        """Hide the advance-payment row and Room Rate/Extra Person charges when
        the OTA booking is paid online (only early/late charges remain)."""
        paid_online = self.paid_online_combo is not None and bool(self.paid_online_combo.currentData())
        self.rate_spin.setVisible(not paid_online)
        self.extra_spin.setVisible(not paid_online)
        if paid_online:
            self.rate_spin.setValue(0)
            self.extra_spin.setValue(0)
        if self.advance_spin is None or self.advance_method is None:
            return
        visible = not paid_online
        self.advance_heading.setVisible(visible)
        self.advance_spin.setVisible(visible)
        self.advance_method.setVisible(visible)

    def _on_stay_changed(self) -> None:
        if self._rooms_loaded:
            self._refresh_room_list()

    def _refresh_room_list(self) -> None:
        """Re-populate rooms, keeping the current selection when possible."""
        previous = self.room_combo.currentData()
        self.room_combo.blockSignals(True)
        self.room_combo.clear()

        if self.editing_booking_id is not None:
            for room in self.all_rooms:
                self.room_combo.addItem(f"Room {room.room_number} ({room.room_type})", room.id)
        else:
            check_in_date = self._to_date(self.check_in_date)
            check_in_time = self._to_time(self.check_in_time)
            check_out_date = self._to_date(self.check_out_date)
            check_out_time = self._to_time(self.check_out_time)
            with self.database.session_scope() as session:
                available_rooms = []
                for room in self.all_rooms:
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
            if not available_rooms:
                self.room_combo.addItem("No rooms available", None)
            else:
                for room in available_rooms:
                    self.room_combo.addItem(f"Room {room.room_number} ({room.room_type})", room.id)
        self.room_combo.blockSignals(False)

        index = self.room_combo.findData(previous)
        if index >= 0:
            self.room_combo.setCurrentIndex(index)
        self._rooms_loaded = True

    # ------------------------------------------------------------ editing

    def _load_for_edit(self, booking_id: int) -> None:
        with self.database.session_scope() as session:
            booking = booking_service.get_booking(session, booking_id)
        if booking is None:
            self.reject()
            return
        self._booking = booking
        self.guest_section.fill_from_guest(booking.guest_id)

        index = self.room_combo.findData(booking.room_id)
        if index >= 0:
            self.room_combo.setCurrentIndex(index)
        index = self.source_combo.findData(booking.booking_source_id)
        if index >= 0:
            self.source_combo.setCurrentIndex(index)

        self.check_in_date.setDate(QDate(booking.check_in_date.year, booking.check_in_date.month, booking.check_in_date.day))
        self.check_out_date.setDate(QDate(booking.check_out_date.year, booking.check_out_date.month, booking.check_out_date.day))
        if booking.check_in_time is not None:
            self.check_in_time.setTime(QTime(booking.check_in_time.hour, booking.check_in_time.minute))
        if booking.check_out_time is not None:
            self.check_out_time.setTime(QTime(booking.check_out_time.hour, booking.check_out_time.minute))

        self.adults_spin.setValue(int(booking.adults or 0))
        self.children_spin.setValue(int(booking.children or 0))
        self.rate_spin.setValue(float(booking.room_rate or 0))
        self.extra_spin.setValue(float(booking.extra_person_charge or 0))
        self.early_spin.setValue(float(booking.early_check_in_charge or 0))
        self.late_spin.setValue(float(booking.late_check_out_charge or 0))
        self.notes_edit.setPlainText(booking.special_notes or "")

    # -------------------------------------------------------------- save

    def _to_date(self, widget: "CalendarDateEdit") -> date:
        qdate = widget.date()
        return date(qdate.year(), qdate.month(), qdate.day())

    def _to_time(self, widget: QTimeEdit) -> dtime | None:
        qtime = widget.time()
        return dtime(qtime.hour(), qtime.minute())

    def _save(self) -> int | None:
        """Save the booking and return its id, or ``None`` on failure."""
        guest_id, error = self.guest_section.resolve_guest_id()
        if error:
            QMessageBox.warning(self, "Missing Information", error)
            return None

        room_id = self.room_combo.currentData()
        source_id = self.source_combo.currentData()
        if room_id is None:
            QMessageBox.warning(self, "Missing Information", "Please select a room.")
            return None
        if source_id is None:
            QMessageBox.warning(self, "Missing Information", "Please select a booking source.")
            return None

        check_in_date = self._to_date(self.check_in_date)
        check_in_time = self._to_time(self.check_in_time)
        check_out_date = self._to_date(self.check_out_date)
        check_out_time = self._to_time(self.check_out_time)

        common = dict(
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=source_id,
            check_in_date=check_in_date,
            check_in_time=check_in_time,
            check_out_date=check_out_date,
            check_out_time=check_out_time,
            adults=self.adults_spin.value(),
            children=self.children_spin.value(),
            room_rate=self.rate_spin.value(),
            extra_person_charge=self.extra_spin.value(),
            early_check_in_charge=self.early_spin.value(),
            late_check_out_charge=self.late_spin.value(),
            special_notes=self.notes_edit.toPlainText(),
        )
        if self.advance_spin is not None:
            common["advance_payment"] = self.advance_spin.value()
            common["advance_payment_method"] = self.advance_method.currentData()
        if self.paid_online_combo is not None:
            common["paid_online"] = bool(self.paid_online_combo.currentData())

        booking_id: int | None = None
        try:
            with self.database.session_scope() as session:
                if self._booking is not None:
                    booking_service.update_booking(session, self._booking.id, **common)
                    booking_id = self._booking.id
                else:
                    booking = booking_service.create_reservation(session, **common)
                    booking_id = booking.id
        except booking_service.RoomNotAvailableError as exc:
            QMessageBox.warning(self, "Room Not Available", str(exc))
            return None
        except (booking_service.BookingValidationError, guest_service.GuestValidationError) as exc:
            QMessageBox.warning(self, "Invalid Booking", str(exc))
            return None
        except Exception:
            QMessageBox.critical(self, "Error", "Could not save the booking. See logs for details.")
            import logging

            logging.getLogger(__name__).exception("Booking save failed")
            return None

        if self.on_changed is not None:
            self.on_changed()
        self._already_saved_this_session = True
        return booking_id

    def _save_reservation(self) -> None:
        """Save the reservation and close the dialog on success."""
        if self._save() is not None:
            self.accept()

    def _save_and_check_in(self) -> None:
        """Save the booking and immediately check the guest in."""
        if self._already_saved_this_session:
            return
        booking_id = self._save()
        if booking_id is None:
            return
        guest_name = ""
        try:
            with self.database.session_scope() as session:
                booking = booking_service.get_booking(session, booking_id)
                if booking is not None and booking.guest is not None:
                    guest_name = booking.guest.guest_name
                room_number = booking.room.room_number if booking is not None and booking.room else ""
                booking_service.check_in_booking(
                    session,
                    booking_id,
                    check_in_date=self._to_date(self.check_in_date),
                    check_in_time=self._to_time(self.check_in_time),
                )
        except booking_service.InvalidBookingStateError as exc:
            QMessageBox.warning(self, "Check-in", str(exc))
            self.accept()
            return
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Direct check-in failed after booking save")
            QMessageBox.warning(
                self,
                "Check-in",
                "The booking was saved but check-in failed. See the log for details.",
            )
            self.accept()
            return
        QMessageBox.information(
            self,
            "Checked In",
            f"Guest {guest_name} was checked into Room {room_number}.",
        )
        self.accept()
