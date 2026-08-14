"""Restore backup dialog.

Guides Admin through a safe restore: pick a ``.ncsbackup`` file, preview
its details, show a strong warning, then restore through the backup
service. On success the application asks for a restart.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import backup_service

logger = logging.getLogger(__name__)


def _friendly_size(size_bytes: int) -> str:
    value = float(size_bytes or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:,.0f} {unit}" if unit == "B" else f"{value:,.1f} {unit}"
        value /= 1024
    return f"{size_bytes:,} B"


def run_restore_flow(database: Database, parent: QWidget | None = None) -> None:
    """Top-level entry: pick, preview, confirm and perform a restore."""
    location = backup_service.get_backup_location(database)
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Select Backup to Restore",
        str(location),
        "Nashik Comfort Stay Backups (*.ncsbackup)",
    )
    if not path:
        return

    verification = backup_service.verify_backup_file(path)
    if not verification.ok:
        QMessageBox.warning(
            parent,
            "Backup Not Valid",
            verification.error or "The selected file is not a valid backup.",
        )
        return

    dialog = RestorePreviewDialog(database, path, verification, parent)
    dialog.exec()


class RestorePreviewDialog(QDialog):
    """Shows backup details and a strong warning before restoring."""

    def __init__(self, database: Database, backup_file: str, verification, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database
        self.backup_file = backup_file
        self.verification = verification
        self.setWindowTitle("Restore Backup")
        self.setMinimumWidth(520)
        self._build_ui()
        self._populate()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("Restore Backup")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.form)

        warning = QLabel(
            "Restoring this backup will replace the current hotel data with "
            "the selected backup.\n\n"
            "The current data will first be saved as a safety backup."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #b45309; font-weight: 600; background: #fef3c7; padding: 10px; border-radius: 6px;")
        layout.addWidget(warning)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("SecondaryButton")
        cancel.clicked.connect(self.reject)
        self.continue_button = QPushButton("Continue")
        self.continue_button.setObjectName("ActionButton")
        self.continue_button.clicked.connect(self._restore)
        buttons.addWidget(cancel)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)

    def _populate(self) -> None:
        metadata = self.verification.metadata
        created_at = str(metadata.get("created_at", ""))[:19].replace("T", " ")
        rows = (
            ("Backup file", self.backup_file.split("/")[-1].split("\\")[-1]),
            ("Backup date", created_at or "—"),
            ("Backup size", _friendly_size(verification_size(self.backup_file))),
            ("Backup version", str(metadata.get("backup_version", "—"))),
            ("Database / schema version", str(metadata.get("schema_version", "—"))),
            ("Verification status", "VERIFIED" if self.verification.ok else "NOT VERIFIED"),
        )
        for label, value in rows:
            key = QLabel(label)
            key.setProperty("detailLabel", True)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            self.form.addRow(key, value_label)

    def _restore(self) -> None:
        self.continue_button.setEnabled(False)
        try:
            result = backup_service.restore_backup(self.database, self.backup_file)
        except backup_service.IncompatibleBackupError as exc:
            QMessageBox.critical(
                self, "Cannot Restore",
                str(exc) or "This backup was created by a newer version of the application "
                             "and cannot be safely restored.",
            )
            self.reject()
            return
        except backup_service.BackupError as exc:
            QMessageBox.critical(self, "Restore Failed", str(exc))
            self.reject()
            return
        except Exception:
            logger.exception("Restore failed")
            QMessageBox.critical(
                self, "Restore Failed",
                "Restore failed. Your current hotel data has not been replaced. "
                "See the application log for details.",
            )
            self.reject()
            return

        QMessageBox.information(
            self, "Restore Completed",
            f"{result.message}\n\nPlease restart the application to complete the restore.",
        )
        self.accept()


def verification_size(backup_file: str) -> int:
    from pathlib import Path

    try:
        return Path(backup_file).stat().st_size
    except OSError:
        return 0