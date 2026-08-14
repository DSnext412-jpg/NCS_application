"""Tests for the Backup, Restore & Data Safety service (Phase 8).

All tests use temporary databases, temporary backup folders and the temp
``NCS_APP_DATA`` directory. The production database, invoice PDFs and logo
are never touched.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.database.database import Database
from app.services import backup_service as bk
from app.services import guest_service, room_service, settings_service
from app.services.booking_source_service import initialize_default_sources
from tests._db_support import copy_db_template


def _fresh_db(tmp_path: Path, name: str = "hotel.db") -> Database:
    database = Database(copy_db_template(tmp_path / name))
    with database.session_scope() as session:
        from app.core.config import KEY_BACKUP_LOCATION

        settings_service.set_setting(session, KEY_BACKUP_LOCATION, str(tmp_path / "backups"))
        initialize_default_sources(session)
        room_service.initialize_default_rooms(session)
    return database


def _seed_guest(database: Database, name: str = "Sita", mobile: str = "9991112223") -> int:
    with database.session_scope() as session:
        guest = guest_service.create_guest(session, guest_name=name, mobile_number=mobile)
        return guest.id


def _read_guest_name(database: Database, guest_id: int) -> str | None:
    from app.database.models import Guest

    with database.session_scope() as session:
        guest = session.get(Guest, guest_id)
        return guest.guest_name if guest else None


# ---------------------------------------------------------------------------
# Manual backup
# ---------------------------------------------------------------------------

def test_manual_backup_creates_valid_package(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        guest_id = _seed_guest(database, name="Original")
        result = bk.create_backup(database, reason="manual")
        assert result.ok is True
        assert result.file_path.exists()
        assert result.file_path.suffix == bk.BACKUP_EXTENSION

        verification = bk.verify_backup_file(result.file_path)
        assert verification.ok is True
        assert verification.integrity_ok is True
        assert verification.tables_ok is True
        assert verification.schema_version == bk.SCHEMA_VERSION
        assert verification.metadata["encrypted"] is False
        assert verification.metadata["backup_version"] == bk.BACKUP_VERSION
        assert verification.metadata["reason"] == "manual"

        with zipfile.ZipFile(result.file_path) as archive:
            names = archive.namelist()
        assert bk.PACKAGE_DB_NAME in names
        assert bk.PACKAGE_METADATA_NAME in names

        # The snapshot must contain the seeded guest.
        with zipfile.ZipFile(result.file_path) as archive, archive.open(
            bk.PACKAGE_DB_NAME
        ) as source, open(tmp_path / "snap.db", "wb") as target:
            shutil.copyfileobj(source, target)
        probe = sqlite3.connect(tmp_path / "snap.db")
        try:
            row = probe.execute("SELECT guest_name FROM guests").fetchone()
        finally:
            probe.close()
        assert row is not None
        assert "Original" in row[0]
    finally:
        database.dispose()


def test_backup_metadata_never_contains_passwords(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        with database.session_scope() as session:
            from app.services import security_service

            security_service.initialize_admin_password(session, "SuperSecret123")
        result = bk.create_backup(database, reason="manual")
        with zipfile.ZipFile(result.file_path) as archive:
            metadata = json.loads(archive.read(bk.PACKAGE_METADATA_NAME).decode("utf-8"))
        assert "SuperSecret123" not in json.dumps(metadata)
        assert "password" not in json.dumps(metadata).lower()
    finally:
        database.dispose()


def test_backup_records_history_and_last_success(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        result = bk.create_backup(database, reason="manual")
        last = bk.last_successful_backup(database)
        assert last is not None
        assert last.file_name == result.file_path.name
        assert last.status == "verified"
        history = bk.get_backup_history(database)
        assert len(history) == 1
        assert history[0].reason == "manual"
    finally:
        database.dispose()


def test_backup_failure_records_failed_history(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        import os

        database.dispose()
        os.remove(tmp_path / "hotel.db")
        with pytest.raises(bk.BackupError):
            bk.create_backup(database, reason="manual")
        # A failed backup must not be recorded as successful.
        last = bk.last_successful_backup(database)
        assert last is None
    finally:
        database.dispose()


def test_backup_marks_unknown_target_folder(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        result = bk.create_backup(database, location=tmp_path / "custom_folder", reason="manual")
        assert result.ok is True
        assert result.file_path.parent == (tmp_path / "custom_folder").resolve()
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def test_verify_missing_file_fails(tmp_path: Path) -> None:
    verification = bk.verify_backup_file(tmp_path / "nope.ncsbackup")
    assert verification.ok is False


def test_verify_garbage_file_fails(tmp_path: Path) -> None:
    junk = tmp_path / "junk.ncsbackup"
    junk.write_bytes(b"this is not a zip archive")
    verification = bk.verify_backup_file(junk)
    assert verification.ok is False


def test_verify_corrupted_backup_fails(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        result = bk.create_backup(database, reason="manual")
        # Rebuild the package with a corrupted embedded database.
        corrupted_path = tmp_path / "corrupt.ncsbackup"
        with zipfile.ZipFile(result.file_path) as source, zipfile.ZipFile(
            corrupted_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == bk.PACKAGE_DB_NAME:
                    data = b"X" * len(data)
                target.writestr(item, data)
        verification = bk.verify_backup_file(corrupted_path)
        assert verification.ok is False
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def test_restore_replaces_data_and_creates_safety_backup(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        guest_id = _seed_guest(database, name="Original")
        backup = bk.create_backup(database, reason="manual")

        with database.session_scope() as session:
            guest_service.update_guest(session, guest_id, guest_name="Changed")
        assert _read_guest_name(database, guest_id) == "Changed"

        result = bk.restore_backup(database, backup.file_path)
        assert result.ok is True
        assert _read_guest_name(database, guest_id) == "Original"
        assert result.safety_backup is not None
        assert result.safety_backup.exists()
        assert "PreRestore" in result.safety_backup.name
    finally:
        database.dispose()


def test_restore_invalid_backup_raises(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        junk = tmp_path / "junk.ncsbackup"
        junk.write_bytes(b"not a real backup")
        with pytest.raises(bk.RestoreError):
            bk.restore_backup(database, junk)
    finally:
        database.dispose()


def test_restore_missing_backup_raises(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        with pytest.raises(bk.RestoreError):
            bk.restore_backup(database, tmp_path / "missing.ncsbackup")
    finally:
        database.dispose()


def test_restore_newer_schema_is_blocked(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        result = bk.create_backup(database, reason="manual")
        with zipfile.ZipFile(result.file_path, "a") as archive:
            archive.writestr("metadata.json", '{"schema_version": 999}')
        with pytest.raises(bk.IncompatibleBackupError):
            bk.restore_backup(database, result.file_path)
    finally:
        database.dispose()


def test_restore_missing_database_file_works(tmp_path: Path) -> None:
    """Restoring onto a deleted database (crash recovery) must work."""
    database = _fresh_db(tmp_path)
    guest_id = _seed_guest(database, name="Keep Me")
    backup = bk.create_backup(database, reason="manual")
    database.dispose()

    import os

    os.remove(tmp_path / "hotel.db")
    assert not (tmp_path / "hotel.db").exists()

    fresh = Database(tmp_path / "hotel.db")
    try:
        result = bk.restore_backup(fresh, backup.file_path)
        assert result.ok is True
        assert (tmp_path / "hotel.db").exists()
        assert _read_guest_name(fresh, guest_id) == "Keep Me"
    finally:
        fresh.dispose()


# ---------------------------------------------------------------------------
# Automatic backups
# ---------------------------------------------------------------------------

def test_auto_backup_not_due_when_disabled(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        bk.set_auto_backup_config(database, enabled=False)
        assert bk.is_auto_backup_due(database) is False
        assert bk.run_auto_backup(database) is None
        history = bk.get_backup_history(database)
        assert history == []
    finally:
        database.dispose()


def test_auto_backup_due_when_never_run(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        bk.set_auto_backup_config(database, enabled=True)
        assert bk.is_auto_backup_due(database) is True
    finally:
        database.dispose()


def test_auto_backup_not_due_right_after_success(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        bk.set_auto_backup_config(database, enabled=True)
        result = bk.run_auto_backup(database)
        assert result is not None
        assert bk.is_auto_backup_due(database) is False
    finally:
        database.dispose()


def test_auto_backup_due_after_interval(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        bk.set_auto_backup_config(database, enabled=True)
        bk.run_auto_backup(database)
        with database.session_scope() as session:
            from app.core.config import KEY_BACKUP_LAST_SUCCESS
            from app.services import settings_service

            past = (date.today() - timedelta(days=5)).isoformat()
            settings_service.set_setting(session, KEY_BACKUP_LAST_SUCCESS, past)
        assert bk.is_auto_backup_due(database) is True
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def test_retention_keeps_newest_only(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        bk.set_auto_backup_config(database, enabled=True, retention=2)
        # Create three backups through the service so they land in the folder.
        first = bk.create_backup(database, reason="manual")
        second = bk.create_backup(database, reason="manual")
        third = bk.create_backup(database, reason="manual")
        files = bk.list_backup_files(tmp_path / "backups")
        names = {path.name for path in files}
        assert third.file_path.name in names
        assert second.file_path.name in names
        assert first.file_path.name not in names
        assert len(files) <= 2
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def test_set_backup_location_persists(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        new_location = tmp_path / "new_backups"
        resolved = bk.set_backup_location(database, new_location)
        assert resolved == new_location.resolve()
        assert bk.get_backup_location(database) == new_location.resolve()
    finally:
        database.dispose()


def test_set_backup_location_creates_nested_folders(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        new_location = tmp_path / "a" / "b" / "c"
        resolved = bk.set_backup_location(database, new_location)
        assert resolved == new_location.resolve()
        assert resolved.exists()
        assert bk.get_backup_location(database) == new_location.resolve()
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def test_delete_backup_file_removes_it(tmp_path: Path) -> None:
    database = _fresh_db(tmp_path)
    try:
        result = bk.create_backup(database, reason="manual")
        assert result.file_path.exists()
        assert bk.delete_backup_file(result.file_path) is True
        assert not result.file_path.exists()
    finally:
        database.dispose()