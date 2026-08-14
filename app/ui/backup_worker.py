"""Lightweight background worker for automatic backups.

Runs a single backup in a ``QThread`` so a large backup never freezes the
reception UI. Emits human-readable messages for the status bar; technical
details go to the application log only.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread, Signal

from app.database.database import Database
from app.services import backup_service

logger = logging.getLogger(__name__)


class AutoBackupWorker(QThread):
    """Runs one automatic backup when due, then emits its outcome."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, database: Database, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.database = database

    def run(self) -> None:  # noqa: D102 - QThread.run
        try:
            result = backup_service.run_auto_backup(self.database)
            if result is None:
                self.succeeded.emit("")  # nothing due — no notification
                return
            self.succeeded.emit(
                f"Automatic backup completed: {result.file_path.name} "
                f"({result.size_bytes:,} bytes)."
            )
        except Exception as exc:  # noqa: BLE001 - always surface a friendly message
            logger.exception("Automatic backup failed")
            self.failed.emit(f"Automatic backup failed: {_user_message(exc)}")


def _user_message(exc: Exception) -> str:
    from app.services.backup_service import BackupError

    if isinstance(exc, BackupError):
        return str(exc)
    return "Could not create the automatic backup. See the application log for details."