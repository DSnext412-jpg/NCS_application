"""Admin Backup & Data Safety page (Phase 8).

Admin-only management of backups: create, restore, change location,
automatic-backup settings, retention and history. Reception never reaches
this page — it is gated by the admin login in the main window.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import backup_service
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table, status_item

logger = logging.getLogger(__name__)


def _friendly_size(size_bytes: int) -> str:
    value = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{size_bytes:,} B"


class AdminBackupPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Backup & Data Safety")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel(
            "Create and restore backups of your hotel data. "
            "Reception staff cannot access this page."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # --- status card --------------------------------------------------
        status_card = QFrame()
        status_card.setObjectName("Card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 14, 16, 14)
        status_layout.setSpacing(8)

        status_row = QHBoxLayout()
        self.db_status_label = QLabel()
        self.db_status_label.setObjectName("SectionHeading")
        status_row.addWidget(self.db_status_label)
        status_row.addStretch(1)
        self.last_backup_label = QLabel("Last Backup: —")
        self.last_backup_label.setProperty("detailLabel", True)
        status_row.addWidget(self.last_backup_label)
        status_layout.addLayout(status_row)

        location_row = QHBoxLayout()
        location_row.setSpacing(8)
        location_label = QLabel("Backup Location:")
        location_label.setProperty("detailLabel", True)
        self.location_edit = QLineEdit()
        self.location_edit.setReadOnly(True)
        location_row.addWidget(location_label)
        location_row.addWidget(self.location_edit, 1)
        self.change_location_button = QPushButton("Change Location")
        self.change_location_button.setObjectName("SecondaryButton")
        self.change_location_button.clicked.connect(self._change_location)
        location_row.addWidget(self.change_location_button)
        self.open_folder_button = QPushButton("Open Backup Folder")
        self.open_folder_button.setObjectName("SecondaryButton")
        self.open_folder_button.clicked.connect(self._open_folder)
        location_row.addWidget(self.open_folder_button)
        status_layout.addLayout(location_row)
        layout.addWidget(status_card)

        # --- actions ------------------------------------------------------
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        self.create_button = QPushButton("Create Backup Now")
        self.create_button.setObjectName("ActionButton")
        self.create_button.clicked.connect(self._create_backup)
        actions_row.addWidget(self.create_button)
        self.restore_button = QPushButton("Restore Backup")
        self.restore_button.setObjectName("ActionButton")
        self.restore_button.clicked.connect(self._restore_backup)
        actions_row.addWidget(self.restore_button)
        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        # --- automatic backup ---------------------------------------------
        auto_card = QFrame()
        auto_card.setObjectName("Card")
        auto_layout = QVBoxLayout(auto_card)
        auto_layout.setContentsMargins(16, 14, 16, 14)
        auto_layout.setSpacing(10)
        heading = QLabel("Automatic Backup")
        heading.setObjectName("SectionHeading")
        auto_layout.addWidget(heading)

        form = QFormLayout()
        self.auto_checkbox = QCheckBox("Automatic Backup")
        self.auto_checkbox.toggled.connect(self._save_auto_settings)
        form.addRow("Status:", self.auto_checkbox)
        self.frequency_combo = QComboBox()
        self.frequency_combo.addItem("Daily", "daily")
        self.frequency_combo.addItem("Weekly", "weekly")
        self.frequency_combo.currentIndexChanged.connect(self._save_auto_settings)
        form.addRow("Frequency:", self.frequency_combo)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("hh:mm AP")
        self.time_edit.timeChanged.connect(self._save_auto_settings)
        form.addRow("Time:", self.time_edit)
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 1000)
        self.retention_spin.setValue(30)
        self.retention_spin.valueChanged.connect(self._save_auto_settings)
        form.addRow("Keep newest backups:", self.retention_spin)
        self.next_backup_label = QLabel("Next Backup: —")
        self.next_backup_label.setProperty("detailLabel", True)
        form.addRow("Next Backup:", self.next_backup_label)
        auto_layout.addLayout(form)
        layout.addWidget(auto_card)

        # --- history ------------------------------------------------------
        history_heading = QLabel("Backup History")
        history_heading.setObjectName("SectionHeading")
        layout.addWidget(history_heading)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Date & Time", "Backup File", "Size", "Status", "Reason", "Verification"],
            resize_to_contents_cols=[0, 2, 3, 4, 5],
        )
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyState("No backups yet", "Create your first backup to protect your data.", icon="💾")
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

        self._loading_flag = False

    # ------------------------------------------------------------- actions

    def _create_backup(self) -> None:
        try:
            result = backup_service.create_backup(self.database, reason="manual")
        except backup_service.BackupError as exc:
            QMessageBox.critical(self, "Backup Failed", str(exc))
            self.refresh()
            return
        except Exception:
            logger.exception("Manual backup failed")
            QMessageBox.critical(
                self, "Backup Failed",
                "Could not create the backup. See the application log for details.",
            )
            self.refresh()
            return
        QMessageBox.information(
            self, "Backup Created",
            f"Backup created successfully.\n\n"
            f"File: {result.file_path.name}\n"
            f"Location: {result.file_path.parent}\n"
            f"Size: {_friendly_size(result.size_bytes)}",
        )
        self.refresh()

    def _restore_backup(self) -> None:
        from app.ui.dialogs.restore_backup_dialog import run_restore_flow

        run_restore_flow(self.database, self)
        self.refresh()

    def _change_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Backup Folder", str(backup_service.get_backup_location(self.database))
        )
        if not folder:
            return
        try:
            backup_service.set_backup_location(self.database, folder)
        except backup_service.BackupError as exc:
            QMessageBox.warning(self, "Backup Location", str(exc))
            return
        QMessageBox.information(self, "Backup Location", "Backup location updated.")
        self.refresh()

    def _open_folder(self) -> None:
        import os
        import subprocess
        import sys

        folder = backup_service.get_backup_location(self.database)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if sys.platform == "win32":
            os.startfile(str(folder))  # noqa: S606 - opening a folder for the user
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _save_auto_settings(self) -> None:
        if self._loading_flag:
            return
        try:
            backup_service.set_auto_backup_config(
                self.database,
                enabled=self.auto_checkbox.isChecked(),
                frequency=str(self.frequency_combo.currentData()),
                time_raw=self.time_edit.time().toString("HH:mm"),
                retention=self.retention_spin.value(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Automatic Backup", str(exc))
        except Exception:
            logger.exception("Failed to save automatic backup settings")
        self._update_next_backup()

    # --------------------------------------------------------------- data

    def _update_next_backup(self) -> None:
        with self.database.session_scope() as session:
            from app.core.config import KEY_BACKUP_LAST_SUCCESS
            from app.services import settings_service

            last_raw = settings_service.get_setting(session, KEY_BACKUP_LAST_SUCCESS, default="") or ""
        if last_raw:
            try:
                from datetime import datetime

                last = datetime.fromisoformat(last_raw)
                label = f"Next Backup: {last.strftime('%d %b %Y, %I:%M %p')}"
            except ValueError:
                label = "Next Backup: —"
        else:
            label = "Next Backup: today"
        self.next_backup_label.setText(label)

    def refresh(self) -> None:
        self._loading_flag = True
        try:
            health = backup_service.database_health(self.database.database_path)
            self.db_status_label.setText(
                f"Current Database: {'HEALTHY' if health == 'healthy' else 'ERROR'}"
            )
            self.db_status_label.setStyleSheet(
                "color: #16a34a;" if health == "healthy" else "color: #dc2626;"
            )

            self.location_edit.setText(str(backup_service.get_backup_location(self.database)))

            with self.database.session_scope() as session:
                from app.core.config import (
                    KEY_BACKUP_AUTO_ENABLED,
                    KEY_BACKUP_FREQUENCY,
                    KEY_BACKUP_RETENTION,
                    KEY_BACKUP_TIME,
                )
                from app.services import settings_service

                enabled = settings_service.get_bool_setting(session, KEY_BACKUP_AUTO_ENABLED, default=True)
                frequency = settings_service.get_setting(session, KEY_BACKUP_FREQUENCY, default="daily") or "daily"
                time_raw = settings_service.get_setting(session, KEY_BACKUP_TIME, default="21:30") or "21:30"
                retention = settings_service.get_setting(session, KEY_BACKUP_RETENTION, default="30") or "30"
            self.auto_checkbox.setChecked(enabled)
            index = self.frequency_combo.findData(frequency)
            self.frequency_combo.setCurrentIndex(index if index >= 0 else 0)
            try:
                hour, minute = (int(part) for part in time_raw.split(":", 1))
                self.time_edit.setTime(self.time_edit.time().fromString(f"{hour:02d}:{minute:02d}", "HH:mm"))
            except (ValueError, AttributeError):
                pass
            self.retention_spin.setValue(int(retention or 30))

            last = backup_service.last_successful_backup(self.database)
            if last is not None:
                self.last_backup_label.setText(
                    f"Last Backup: {last.created_at.strftime('%d %b %Y, %I:%M %p')}"
                )
            else:
                self.last_backup_label.setText("Last Backup: never")

            records = backup_service.get_backup_history(self.database, limit=100)
            self.table.setSortingEnabled(False)
            self.table.setRowCount(0)
            for row_index, record in enumerate(records):
                self.table.insertRow(row_index)
                self.table.setItem(
                    row_index, 0,
                    QTableWidgetItem(record.created_at.strftime("%d %b %Y, %I:%M %p")),
                )
                self.table.setItem(row_index, 1, QTableWidgetItem(record.file_name))
                self.table.setItem(row_index, 2, QTableWidgetItem(_friendly_size(record.size_bytes)))
                self.table.setItem(row_index, 3, status_item("Verified", "verified" if record.status == "verified" else "failed"))
                self.table.setItem(row_index, 4, QTableWidgetItem(record.reason or ""))
                self.table.setItem(row_index, 5, QTableWidgetItem(record.verification or ""))
            self.table.setSortingEnabled(True)
            has_rows = bool(records)
            self.table.setVisible(has_rows)
            self.empty_state.setVisible(not has_rows)
        finally:
            self._loading_flag = False
        self._update_next_backup()