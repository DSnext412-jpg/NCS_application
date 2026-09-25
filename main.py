from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    from PySide6.QtCore import QTimer

from app.core.logging_config import setup_logging
from app.core.paths import Paths
from app.database.database import Database

logger = logging.getLogger(__name__)


def _resolve_database_startup(paths: Paths) -> bool:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from app.services import backup_service

    health = backup_service.database_health(paths.database_file)
    if health == "healthy":
        return True

    if os.environ.get("NCS_HEADLESS") == "1":
        if health != "missing":
            _remove_damaged_database(paths.database_file)
        logger.info("Headless startup without a healthy database — creating a fresh one.")
        return True

    backups = backup_service.list_backup_files()
    if not backups:
        if health == "missing":
            logger.info("No database present and no backups found — creating a fresh one.")
            return True
        QMessageBox.critical(
            None,
            "Database Problem",
            "The hotel database is damaged and no backup was found.\n\n"
            "The application cannot start. Please restore the database manually "
            "or check the application log.",
        )
        return False

    problem = (
        if health == "missing"
        else "The hotel database appears to be damaged. The application can restore it from a backup."
    )
    answer = QMessageBox.question(
        None,
        f"{problem}\n\n"
        f"Restore the latest backup ({backups[0].name}) now?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    if answer != QMessageBox.StandardButton.Yes:
        logger.info("Restore declined — removing damaged database and starting fresh.")
        _remove_damaged_database(paths.database_file)
        return True

    path, _ = QFileDialog.getOpenFileName(
        None,
        "Select Backup to Restore",
        str(backups[0].parent),
        "Nashik Comfort Stay Backups (*.ncsbackup)",
    )
    if not path:
        logger.info("No backup selected — removing damaged database and starting fresh.")
        _remove_damaged_database(paths.database_file)
        return True

    return _restore_and_continue(paths, path)


def _remove_damaged_database(database_path: Path) -> None:
    path = Path(database_path)
    if path.exists():
        aside = path.with_name(f"{path.stem}_damaged_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        try:
            path.replace(aside)
            logger.info("Damaged database moved aside to: %s", aside)
        except OSError:
            logger.warning("Could not move aside damaged database at %s — leaving it.", path)


def _restore_and_continue(paths: Paths, path: str) -> bool:
    from PySide6.QtWidgets import QMessageBox

    from app.database.database import Database
    from app.services import backup_service
    from app.services.backup_service import (
        BackupError,
        IncompatibleBackupError,
        RestoreError,
    )

    database = Database(paths.database_file)
    try:
        result = backup_service.restore_backup(database, path, audit=True)
    except (IncompatibleBackupError, RestoreError, BackupError) as exc:
        QMessageBox.critical(None, "Restore Failed", str(exc))
        database.dispose()
        return False
    except Exception:
        logger.exception("Startup restore failed")
        QMessageBox.critical(
            None, "Restore Failed",
            "Restore failed. See the application log for details.",
        )
        database.dispose()
        return False

    QMessageBox.information(
        None,
        "Restore Completed",
        f"{result.message}\n\n"
        f"The database now contains the data from:\n{path}",
    )
    database.dispose()
    return True


def initialize_application() -> tuple[QApplication, Database, Paths] | None:
    app = QApplication(sys.argv)
    app.setApplicationName("Nashik Comfort Stay")

    from app.ui.styles import APP_STYLESHEET, empty_state_stylesheet

    app.setStyleSheet(APP_STYLESHEET + "\n" + empty_state_stylesheet())

    paths = Paths()
    paths.ensure_directories()
    setup_logging(paths.logs_dir)

    logger.info("Application starting — Nashik Comfort Stay")
    logger.info("Application data directory: %s", paths.app_data_dir)

    if not _resolve_database_startup(paths):
        logger.info("Startup aborted by the user during database recovery.")
        return None

    try:
        database = Database(paths.database_file)
        database.create_all()
        with database.session_scope() as session:
            from app.services.booking_source_service import initialize_default_sources
            from app.services.room_service import initialize_default_rooms
            from app.services.settings_service import initialize_default_settings

            initialize_default_settings(session)
            initialize_default_rooms(session)
            initialize_default_sources(session)
        logger.info("Database initialized at %s", paths.database_file)
    except Exception:
        logger.exception("Database initialization failed")
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(
            None,
            "Startup Error",
            "The application could not initialize its local database.\n\n"
            "Please check the application log file for details.",
        )
        return None

    logger.info("Logging and database ready")
    return app, database, paths


def _start_auto_backup_worker(window: "MainWindow", database: Database) -> None:  # noqa: F821
    from app.ui.backup_worker import AutoBackupWorker

    worker = AutoBackupWorker(database, parent=window)

    def _on_succeeded(message: str) -> None:
        if message:
            window.statusBar().showMessage(message, 10_000)
        worker.deleteLater()

    def _on_failed(message: str) -> None:
        window.statusBar().showMessage(message, 15_000)
        worker.deleteLater()

    worker.succeeded.connect(_on_succeeded)
    worker.failed.connect(_on_failed)
    worker.finished.connect(worker.deleteLater)
    worker.start()


def main(auto_close_ms: int | None = None) -> int:
    from app.ui.main_window import MainWindow

    initialized = initialize_application()
    if initialized is None:
        return 1

    app, database, paths = initialized

    window = MainWindow(database)
    window.show()
    logger.info("Main window shown")

    from app.services import backup_service

    if backup_service.is_auto_backup_due(database):
        _start_auto_backup_worker(window, database)
    else:
        logger.info("Automatic backup is not due yet")

    if auto_close_ms:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(auto_close_ms, app.quit)

    exit_code = app.exec()
    logger.info("Application shut down (exit code %d)", exit_code)

    database.dispose()
    logger.info("Database connection closed")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
