"""Room details dialog.

Allows reception to view room information, change its status (with a
confirmation dialog), edit notes, and activate/deactivate the room.
Every database write goes through the room service; the dialog never
touches the database directly.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import BookingStatus, RoomStatus
from app.database.database import Database
from app.services import booking_service, room_service
from app.ui.formatters import format_date_time
from app.ui.widgets.status_badge import make_status_badge

logger = logging.getLogger(__name__)

_DATETIME_FORMAT = "%d %b %Y, %I:%M %p"


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return value.strftime(_DATETIME_FORMAT)


class RoomDetailsDialog(QDialog):
    def __init__(
        self,
        database: Database,
        room_id: int,
        on_changed: Callable[[], None] | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.room_id = room_id
        self.on_changed = on_changed
        self.room = None

        self.setWindowTitle("Room Details")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.room_number_label = QLabel()
        self.room_number_label.setObjectName("DialogRoomNumber")
        layout.addWidget(self.room_number_label)

        info_card = QFrame()
        info_card.setObjectName("DetailsCard")
        info_grid = QGridLayout(info_card)
        info_grid.setContentsMargins(16, 12, 16, 12)
        info_grid.setHorizontalSpacing(24)
        info_grid.setVerticalSpacing(10)

        self.type_value = self._add_detail_row(info_grid, 0, "Room Type")
        self.status_badge = make_status_badge(RoomStatus.VACANT.value, compact=False)
        info_grid.addWidget(self._detail_label("Status"), 1, 0)
        info_grid.addWidget(self.status_badge, 1, 1, alignment=Qt.AlignmentFlag.AlignLeft)
        self.active_value = self._add_detail_row(info_grid, 2, "Active")
        self.created_value = self._add_detail_row(info_grid, 3, "Created")
        self.updated_value = self._add_detail_row(info_grid, 4, "Last Updated")
        layout.addWidget(info_card)

        # --- Current occupant (context-aware actions) ----------------------
        self.occupant_card = QFrame()
        self.occupant_card.setObjectName("DetailsCard")
        occupant_layout = QVBoxLayout(self.occupant_card)
        occupant_layout.setContentsMargins(16, 12, 16, 12)
        occupant_layout.setSpacing(8)

        occupant_header = QLabel("Current Booking")
        occupant_header.setObjectName("SectionHeading")
        occupant_layout.addWidget(occupant_header)

        self.occupant_info = QLabel("This room is currently free.")
        self.occupant_info.setProperty("detailLabel", True)
        self.occupant_info.setWordWrap(True)
        occupant_layout.addWidget(self.occupant_info)

        occupant_row = QHBoxLayout()
        occupant_row.setSpacing(8)
        self.view_booking_button = QPushButton("View Booking")
        self.view_booking_button.setObjectName("ActionButton")
        self.view_booking_button.clicked.connect(self._view_booking)
        occupant_row.addWidget(self.view_booking_button)
        self.walkin_button = QPushButton("Walk-in Check-in")
        self.walkin_button.setObjectName("SecondaryButton")
        self.walkin_button.clicked.connect(self._walkin)
        occupant_row.addWidget(self.walkin_button)
        occupant_row.addStretch(1)
        occupant_layout.addLayout(occupant_row)
        layout.addWidget(self.occupant_card)

        status_card = QFrame()
        status_card.setObjectName("DetailsCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(8)

        status_header = QLabel("Change Status")
        status_header.setObjectName("SectionHeading")
        status_layout.addWidget(status_header)

        combo_row = QHBoxLayout()
        self.status_combo = QComboBox()
        for status in RoomStatus:
            self.status_combo.addItem(status.label, status.value)
        combo_row.addWidget(self.status_combo, 1)
        self.change_status_button = QPushButton("Change Status")
        self.change_status_button.setObjectName("ActionButton")
        self.change_status_button.clicked.connect(self._apply_status)
        combo_row.addWidget(self.change_status_button)
        status_layout.addLayout(combo_row)

        self.cleaned_container = QWidget()
        self.cleaned_row = QHBoxLayout(self.cleaned_container)
        self.cleaned_row.setContentsMargins(0, 0, 0, 0)
        self.cleaned_row.setSpacing(8)
        self.cleaned_hint = QLabel("Room is awaiting cleaning. Mark it as cleaned to make it vacant.")
        self.cleaned_hint.setProperty("detailLabel", True)
        self.cleaned_hint.setWordWrap(True)
        self.cleaned_row.addWidget(self.cleaned_hint, 1)
        self.mark_cleaned_button = QPushButton("Mark as Cleaned")
        self.mark_cleaned_button.setObjectName("ActionButton")
        self.mark_cleaned_button.clicked.connect(self._mark_cleaned)
        self.cleaned_row.addWidget(self.mark_cleaned_button)
        status_layout.addWidget(self.cleaned_container)

        self.status_lock_note = QLabel(
            "A guest is currently occupying this room. The status will be updated "
            "automatically after check-out."
        )
        self.status_lock_note.setProperty("detailLabel", True)
        self.status_lock_note.setWordWrap(True)
        self.status_lock_note.setStyleSheet("color: #b45309;")
        status_layout.addWidget(self.status_lock_note)

        self.status_note = QLineEdit()
        self.status_note.setPlaceholderText("Note (optional)")
        status_layout.addWidget(self.status_note)
        layout.addWidget(status_card)

        notes_card = QFrame()
        notes_card.setObjectName("DetailsCard")
        notes_layout = QVBoxLayout(notes_card)
        notes_layout.setContentsMargins(16, 12, 16, 12)
        notes_layout.setSpacing(8)

        notes_header = QLabel("Notes")
        notes_header.setObjectName("SectionHeading")
        notes_layout.addWidget(notes_header)

        self.notes_edit = QTextEdit()
        self.notes_edit.setPlaceholderText("e.g. AC remote needs replacement")
        self.notes_edit.setFixedHeight(90)
        notes_layout.addWidget(self.notes_edit)

        notes_row = QHBoxLayout()
        self.active_check = QCheckBox("Room is active")
        notes_row.addWidget(self.active_check)
        notes_row.addStretch(1)
        self.save_notes_button = QPushButton("Save Notes")
        self.save_notes_button.setObjectName("ActionButton")
        self.save_notes_button.clicked.connect(self._save_notes)
        notes_row.addWidget(self.save_notes_button)
        notes_layout.addLayout(notes_row)

        active_row = QHBoxLayout()
        self.save_active_button = QPushButton("Apply Active Setting")
        self.save_active_button.setObjectName("SecondaryButton")
        self.save_active_button.clicked.connect(self._apply_active)
        active_row.addStretch(1)
        active_row.addWidget(self.save_active_button)
        notes_layout.addLayout(active_row)
        layout.addWidget(notes_card)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setObjectName("SecondaryButton")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def _detail_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("detailLabel", True)
        return label

    def _add_detail_row(self, grid: QGridLayout, row: int, title: str) -> QLabel:
        grid.addWidget(self._detail_label(title), row, 0)
        value = QLabel()
        value.setProperty("detailValue", True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(value, row, 1)
        return value

    # --------------------------------------------------------------- logic

    def _load(self) -> None:
        with self.database.session_scope() as session:
            room = room_service.get_room(session, self.room_id)
            if room is None:
                QMessageBox.warning(self, "Room Not Found", "This room no longer exists.")
                self.reject()
                return
            self.room = room
            self.room_number_label.setText(f"ROOM {self.room.room_number}")
            self.type_value.setText(self.room.room_type)
            self.active_value.setText("Yes" if self.room.is_active else "No")
            self.created_value.setText(_format_datetime(self.room.created_at))
            self.updated_value.setText(_format_datetime(self.room.updated_at))

            self._refresh_status_badge()
            index = self.status_combo.findData(self.room.status)
            if index >= 0:
                self.status_combo.setCurrentIndex(index)

            is_cleaning = self.room.status == RoomStatus.CLEANING.value
            self.cleaned_container.setVisible(is_cleaning)
            if is_cleaning:
                self.status_combo.setCurrentIndex(self.status_combo.findData(RoomStatus.CLEANING.value))

            self.notes_edit.setPlainText(self.room.notes or "")
            self.active_check.setChecked(self.room.is_active)

            active_booking = booking_service.get_active_booking_for_room(session, self.room.id)
        self.active_booking = active_booking
        self._render_occupant()

    def _render_occupant(self) -> None:
        booking = self.active_booking
        if booking is None:
            self.occupant_info.setText("This room is currently free.")
            self.view_booking_button.setEnabled(False)
            self.walkin_button.setEnabled(True)
            self._set_status_controls_enabled(True)
            return
        guest = booking.guest
        guest_name = guest.guest_name if guest else "Guest"
        self.occupant_info.setText(
            f"{guest_name} • {format_date_time(booking.check_in_date, booking.check_in_time)} → "
            f"{format_date_time(booking.check_out_date, booking.check_out_time)}"
        )
        self.view_booking_button.setEnabled(True)
        self.walkin_button.setEnabled(False)
        self._set_status_controls_enabled(False)

    def _set_status_controls_enabled(self, enabled: bool) -> None:
        """Disable manual status changes while a guest is occupying the room."""
        self.status_combo.setEnabled(enabled)
        self.change_status_button.setEnabled(enabled)
        self.mark_cleaned_button.setEnabled(enabled)
        self.status_lock_note.setVisible(not enabled)

    def _view_booking(self) -> None:
        if self.active_booking is None:
            return
        from app.ui.dialogs.booking_details_dialog import BookingDetailsDialog

        dialog = BookingDetailsDialog(
            self.database,
            self.active_booking.id,
            on_changed=self._reload_occupant,
            parent=self,
        )
        dialog.exec()
        self._reload_occupant()

    def _walkin(self) -> None:
        from app.ui.dialogs.walkin_dialog import WalkInDialog

        dialog = WalkInDialog(
            self.database,
            on_changed=self._reload_occupant,
            parent=self,
            preset_room_id=self.room_id,
        )
        if dialog.exec():
            self._reload_occupant()

    def _reload_occupant(self) -> None:
        with self.database.session_scope() as session:
            self.active_booking = booking_service.get_active_booking_for_room(session, self.room_id)
        self._render_occupant()
        self._load()
        self._notify_changed()

    def _refresh_status_badge(self) -> None:
        try:
            status_text = RoomStatus(self.room.status).label
        except ValueError:
            status_text = str(self.room.status)
        self.status_badge.setText(status_text)
        self.status_badge.setStyleSheet(make_status_badge(self.room.status, compact=False).styleSheet())

    def _apply_status(self) -> None:
        if self.room is None:
            return
        new_status_value = self.status_combo.currentData()
        if new_status_value == self.room.status:
            QMessageBox.information(self, "No Change", "The room already has this status.")
            return

        old_label = RoomStatus(self.room.status).label
        new_label = RoomStatus(new_status_value).label

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Confirm Status Change")
        box.setText(f"Change Room {self.room.room_number} status from {old_label} to {new_label}?")
        confirm = box.addButton("Confirm", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(confirm)
        box.exec()

        if box.clickedButton() is not confirm:
            return

        try:
            with self.database.session_scope() as session:
                room_service.update_room_status(
                    session,
                    self.room.id,
                    new_status_value,
                    note=self.status_note.text().strip(),
                )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Status", str(exc))
            return
        except Exception:
            logger.exception("Failed to change status for room %s", self.room.room_number)
            QMessageBox.critical(self, "Error", "Could not change the room status. See logs for details.")
            return

        logger.info("Room %s status changed to %s", self.room.room_number, new_label)
        self.status_note.clear()
        self._load()
        self._notify_changed()

    def _mark_cleaned(self) -> None:
        if self.room is None:
            return
        answer = QMessageBox.question(
            self,
            "Confirm Cleaned",
            f"Mark Room {self.room.room_number} as cleaned and make it vacant?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            with self.database.session_scope() as session:
                room_service.set_room_vacant(session, self.room.id, note="Marked as cleaned")
        except Exception:
            logger.exception("Failed to mark room %s as cleaned", self.room.room_number)
            QMessageBox.critical(self, "Error", "Could not mark the room as cleaned. See logs for details.")
            return
        logger.info("Room %s marked as cleaned and set to vacant", self.room.room_number)
        self._load()
        self._notify_changed()

    def _save_notes(self) -> None:
        if self.room is None:
            return
        try:
            with self.database.session_scope() as session:
                room_service.update_room_notes(session, self.room.id, self.notes_edit.toPlainText())
        except Exception:
            logger.exception("Failed to save notes for room %s", self.room.room_number)
            QMessageBox.critical(self, "Error", "Could not save the notes. See logs for details.")
            return
        self._load()
        self._notify_changed()

    def _apply_active(self) -> None:
        if self.room is None:
            return
        new_active = self.active_check.isChecked()
        if new_active == self.room.is_active:
            return
        action = "activate" if new_active else "deactivate"
        answer = QMessageBox.question(
            self,
            "Confirm Change",
            f"{action.title()} Room {self.room.room_number}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.active_check.setChecked(self.room.is_active)
            return
        try:
            with self.database.session_scope() as session:
                room_service.set_room_active(session, self.room.id, new_active)
        except Exception:
            logger.exception("Failed to update active state for room %s", self.room.room_number)
            QMessageBox.critical(self, "Error", "Could not update the room. See logs for details.")
            return
        self._load()
        self._notify_changed()

    def _notify_changed(self) -> None:
        if self.on_changed is not None:
            self.on_changed()
