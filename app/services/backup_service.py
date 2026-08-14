"""Backup, restore and data-safety service (Phase 8).

Backup package (``.ncsbackup``) is a ZIP archive containing:

* ``hotel.db`` — a consistent SQLite snapshot created with SQLite's online
  backup API (``sqlite3.Connection.backup``), NOT a raw file copy, so the
  archive is valid even while the application is writing.
* ``metadata.json`` — application name, backup format version, creation
  timestamp, schema version, application version, SHA-256 checksum of the
  database, record counts and file inventory. Passwords / authentication
  secrets are never written into metadata.
* ``invoices/*.pdf`` — historical invoice PDFs (kept with the backup so a
  restore never silently loses printed invoices).
* ``assets/`` — the Admin-uploaded hotel logo (if configured).

Restore is designed to be extremely safe:

1. validate the selected package (exists, readable, ZIP opens, embedded
   database passes ``PRAGMA integrity_check`` and contains the required
   tables, schema version not newer than the application),
2. create a ``PreRestore`` safety backup of the current database,
3. dispose all open connections,
4. extract + validate the database in a temp file inside the data folder,
5. atomically replace the production database (``os.replace``),
6. reopen, re-run integrity checks and restore invoice PDFs + logo.

If any step fails after the safety backup exists, the previous database is
restored from the safety backup. Backups are NOT encrypted — the metadata
explicitly states ``"encrypted": false``.

Backup history is stored in the application database (``backup_history``)
for Admin review, but the restore system NEVER depends on it: restoring
reads only the ``.ncsbackup`` file, so a damaged or missing main database
can always be recovered from a backup file.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any

from app.core.config import (
    KEY_BACKUP_AUTO_ENABLED,
    KEY_BACKUP_FREQUENCY,
    KEY_BACKUP_LAST_SUCCESS,
    KEY_BACKUP_LOCATION,
    KEY_BACKUP_RETENTION,
    KEY_BACKUP_TIME,
    KEY_LOGO_PATH,
)
from app.core.constants import APP_NAME, APP_VERSION
from app.core.paths import Paths
from app.database.models import BackupHistory
from app.services import audit_service, settings_service

logger = logging.getLogger(__name__)

BACKUP_EXTENSION = ".ncsbackup"
BACKUP_VERSION = 1
SCHEMA_VERSION = 8  # phase 8; bumps when the schema changes
APP_SCHEMA_VERSION = SCHEMA_VERSION

DEFAULT_RETENTION = 30
DEFAULT_FREQUENCY = "daily"
DEFAULT_TIME = "21:30"

PACKAGE_DB_NAME = "hotel.db"
PACKAGE_METADATA_NAME = "metadata.json"
PACKAGE_INVOICES_DIR = "invoices/"
PACKAGE_ASSETS_DIR = "assets/"

BACKUP_FILE_PREFIX = "NashikComfortStay"
PRE_RESTORE_FILE_PREFIX = "NashikComfortStay_PreRestore"

REQUIRED_TABLES = (
    "rooms",
    "guests",
    "bookings",
    "booking_charges",
    "booking_sources",
    "payments",
    "invoices",
    "hotel_settings",
    "audit_log",
    "booking_status_history",
    "room_status_history",
)


class BackupError(Exception):
    """Base error for backup operations."""


class BackupVerificationError(BackupError):
    """Raised when a created/selected backup fails verification."""


class RestoreError(BackupError):
    """Raised when a restore cannot be applied."""


class IncompatibleBackupError(RestoreError):
    """Raised when the backup is newer than the application can restore."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BackupResult:
    ok: bool
    file_path: Path
    message: str = ""
    size_bytes: int = 0
    checksum: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BackupVerification:
    ok: bool
    file_path: Path = None  # type: ignore[assignment]
    exists: bool = False
    readable: bool = False
    zip_ok: bool = False
    integrity_ok: bool = False
    tables_ok: bool = False
    schema_version: int = 0
    backup_version: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    db_checksum_match: bool = False
    error: str = ""


@dataclass
class RestoreResult:
    ok: bool
    message: str = ""
    database_path: Path = None  # type: ignore[assignment]
    backup_file: Path = None  # type: ignore[assignment]
    safety_backup: Path | None = None
    recovered: bool = False
    restored_at: datetime = field(default_factory=datetime.now)


@dataclass
class BackupRecord:
    created_at: datetime
    file_name: str
    backup_file: str
    size_bytes: int
    status: str
    verification: str
    checksum: str
    reason: str
    error_message: str
    location: str


# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

def default_backup_location() -> Path:
    """Default backup folder: ``Documents\\Nashik Comfort Stay\\Backups``."""
    try:
        documents = Path.home() / "Documents"
    except RuntimeError:
        documents = Path.cwd()
    return documents / "Nashik Comfort Stay" / "Backups"


def get_backup_location(database) -> Path:  # noqa: ANN001
    """Configured backup folder, falling back to the Documents default."""
    return _resolve_location(_read_setting(database, KEY_BACKUP_LOCATION, ""))


def _read_setting(database, key: str, default: str) -> str:  # noqa: ANN001
    """Read a settings key, returning ``default`` when the DB is missing/corrupt."""
    try:
        with database.session_scope() as session:
            return settings_service.get_setting(session, key, default=default) or default
    except Exception:  # noqa: BLE001 - a damaged DB must not block backup/restore
        return default


def _resolve_location(raw: str) -> Path:
    if raw and raw.strip():
        return Path(raw.strip()).expanduser()
    return default_backup_location()


def backup_filename(timestamp: datetime | None = None, *, pre_restore: bool = False) -> str:
    timestamp = timestamp or datetime.now()
    prefix = PRE_RESTORE_FILE_PREFIX if pre_restore else BACKUP_FILE_PREFIX
    return f"{prefix}_{timestamp:%Y-%m-%d}_{timestamp:%H%M%S}{BACKUP_EXTENSION}"


def _unique_target(folder: Path, name: str) -> Path:
    """A non-clobbering path: if ``name`` exists, append a numeric suffix."""
    candidate = folder / name
    stem = candidate.stem
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{counter:02d}{BACKUP_EXTENSION}"
        counter += 1
    return candidate


# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

def _online_backup(source_db: Path, target_db: Path) -> None:
    """Create a consistent SQLite snapshot using the online backup API."""
    source = sqlite3.connect(str(source_db))
    try:
        target = sqlite3.connect(str(target_db))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _integrity_check(db_path: Path) -> tuple[bool, str]:
    """Run ``PRAGMA integrity_check`` on a SQLite file."""
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return row is not None and row[0] == "ok", str(row[0] if row else "no result")
    except sqlite3.Error as exc:
        return False, str(exc)
    finally:
        connection.close()


def _table_names(db_path: Path) -> set[str]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def _table_counts(db_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table in sorted(_table_names(db_path)):
            try:
                count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                counts[table] = int(count)
            except sqlite3.Error:
                counts[table] = -1
    finally:
        connection.close()
    return counts


def _sha256(db_path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with db_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def database_health(database_path: Path) -> str:
    """Return ``healthy``, ``corrupt`` or ``missing`` for a database file."""
    if not Path(database_path).exists():
        return "missing"
    try:
        ok, _ = _integrity_check(Path(database_path))
        return "healthy" if ok else "corrupt"
    except sqlite3.Error:
        return "corrupt"


# ---------------------------------------------------------------------------
# Package building
# ---------------------------------------------------------------------------

def _build_metadata(
    *,
    db_path: Path,
    invoice_files: list[Path],
    logo_file: Path | None,
    checksum: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "application_name": APP_NAME,
        "backup_version": BACKUP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "application_version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reason": reason,
        "database": {
            "file": db_path.name,
            "sha256": checksum,
            "size_bytes": db_path.stat().st_size,
            "tables": _table_counts(db_path),
        },
        "files": {
            "invoice_pdfs": [path.name for path in invoice_files],
            "logo": [path.name for path in [logo_file] if path is not None],
        },
        "encrypted": False,
    }


def _write_package(destination: Path, db_path: Path, metadata: dict[str, Any],
                   invoice_files: list[Path], logo_file: Path | None) -> Path:
    """Assemble the ``.ncsbackup`` ZIP archive at ``destination``."""
    with zipfile.ZipFile(str(destination), "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(db_path, PACKAGE_DB_NAME)
        archive.writestr(PACKAGE_METADATA_NAME, json.dumps(metadata, indent=2, ensure_ascii=False))
        for invoice in invoice_files:
            archive.write(invoice, PACKAGE_INVOICES_DIR + invoice.name)
        if logo_file is not None:
            archive.write(logo_file, PACKAGE_ASSETS_DIR + logo_file.name)
    return destination


def _gather_persistent_files(database) -> tuple[list[Path], Path | None]:  # noqa: ANN001
    """Invoice PDFs (from ``invoices/``) and the configured logo, if present."""
    paths = Paths()
    invoice_files: list[Path] = []
    invoices_dir = paths.invoices_dir
    if invoices_dir.exists():
        invoice_files = sorted(invoices_dir.glob("*.pdf"))
    logo_path = _read_setting(database, KEY_LOGO_PATH, "")
    logo_file = Path(logo_path).resolve() if logo_path and Path(logo_path).exists() else None
    return invoice_files, logo_file


def _check_disk_space(destination_dir: Path, required_bytes: int) -> None:
    destination_dir.mkdir(parents=True, exist_ok=True)
    try:
        free = shutil.disk_usage(destination_dir).free
    except OSError as exc:
        raise BackupError("Backup location is not writable. Please choose another folder.") from exc
    if free < required_bytes:
        raise BackupError("Not enough free disk space for the backup. Please free up space or choose another folder.")


def _prepare_source_snapshot(database, destination_dir: Path) -> Path:  # noqa: ANN001
    """Create a verified temp snapshot of the production DB, or raise."""
    database_path = Path(database.database_path)
    if not database_path.exists():
        raise BackupError("The hotel database was not found. Cannot create a backup.")
    snapshot = destination_dir / f".snapshot_{os.getpid()}.db"
    try:
        _online_backup(database_path, snapshot)
    except sqlite3.Error as exc:
        logger.error("Online backup failed for %s: %s", database_path, exc)
        raise BackupError("The hotel database could not be read for backup. It may be damaged.") from exc
    ok, result = _integrity_check(snapshot)
    if not ok:
        raise BackupVerificationError("Backup verification failed. The backup was not marked as valid.")
    missing = set(REQUIRED_TABLES) - _table_names(snapshot)
    if missing:
        raise BackupVerificationError(
            f"Backup verification failed — required data tables are missing ({', '.join(sorted(missing))})."
        )
    return snapshot


def _record_history(database, *, file_path: Path, status: str, verification: str,  # noqa: ANN001
                    reason: str, checksum: str = "", error_message: str = "",
                    metadata: dict[str, Any] | None = None) -> None:
    with database.session_scope() as session:
        session.add(
            BackupHistory(
                backup_file=str(file_path),
                file_name=file_path.name,
                location=str(file_path.parent),
                size_bytes=file_path.stat().st_size if file_path.exists() else 0,
                status=status,
                verification=verification,
                checksum=checksum,
                reason=reason,
                error_message=error_message,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
        )
        if status == "verified":
            settings_service.set_setting(
                session, KEY_BACKUP_LAST_SUCCESS, datetime.now().isoformat(timespec="seconds")
            )


# ---------------------------------------------------------------------------
# Backup creation
# ---------------------------------------------------------------------------

def create_backup(
    database,
    *,
    location: str | Path | None = None,
    reason: str = "manual",
    audit: bool = True,
) -> BackupResult:
    """Create, verify and record a backup. Raises :class:`BackupError` on failure.

    ``reason`` is one of ``manual`` / ``automatic`` / ``pre-restore``.
    """
    logger.info("Backup started (reason=%s)", reason)
    database_path = Path(database.database_path)
    if not database_path.exists():
        raise BackupError("The hotel database was not found. Cannot create a backup.")
    destination_dir = _resolve_location(_read_setting(database, KEY_BACKUP_LOCATION, "")) if location is None else Path(location)
    destination_dir.mkdir(parents=True, exist_ok=True)

    invoice_files, logo_file = _gather_persistent_files(database)

    required = max(1_000_000, database_path.stat().st_size if database_path.exists() else 0) + sum(
        (f.stat().st_size if f.exists() else 0) for f in invoice_files
    ) + (logo_file.stat().st_size if logo_file else 0)
    _check_disk_space(destination_dir, required)

    with tempfile.TemporaryDirectory(prefix="ncs_backup_") as tmp:
        workdir = Path(tmp)
        snapshot = _prepare_source_snapshot(database, workdir)
        checksum = _sha256(snapshot)
        metadata = _build_metadata(
            db_path=snapshot, invoice_files=invoice_files, logo_file=logo_file,
            checksum=checksum, reason=reason,
        )
        target = _unique_target(
            destination_dir, backup_filename(pre_restore=(reason == "pre-restore"))
        )
        _write_package(target, snapshot, metadata, invoice_files, logo_file)

    verification = verify_backup_file(target)
    if not verification.ok:
        _record_history(
            database, file_path=target, status="failed", reason=reason,
            verification=verification.error, error_message=verification.error,
        )
        raise BackupVerificationError(verification.error or "Backup verification failed.")

    _record_history(
        database, file_path=target, status="verified", reason=reason,
        verification="Verified — integrity check passed", checksum=checksum, metadata=metadata,
    )
    if audit:
        with database.session_scope() as session:
            audit_service.log_action(
                session, audit_service.ACTION_BACKUP_CREATED,
                f"Backup created: {target.name} ({target.stat().st_size:,} bytes).",
            )
    _apply_retention(database, location=destination_dir)
    logger.info("Backup completed and verified: %s", target)
    return BackupResult(
        ok=True, file_path=target, message="Backup created successfully.",
        size_bytes=target.stat().st_size, checksum=checksum, timestamp=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_backup_file(backup_file: str | Path) -> BackupVerification:
    """Thoroughly validate a ``.ncsbackup`` package file."""
    path = Path(backup_file)
    result = BackupVerification(ok=False, file_path=path)
    if not path.exists():
        result.error = "The backup file does not exist."
        return result
    if not path.is_file():
        result.error = "The selected file is not a backup."
        return result
    result.exists = True
    try:
        with path.open("rb") as handle:
            result.readable = True
    except OSError as exc:
        result.error = "The backup file could not be read."
        return result

    try:
        with zipfile.ZipFile(str(path)) as archive:
            names = set(archive.namelist())
            result.zip_ok = True
            if PACKAGE_DB_NAME not in names or PACKAGE_METADATA_NAME not in names:
                result.error = "The selected file is not a valid backup package."
                return result
            metadata_raw = archive.read(PACKAGE_METADATA_NAME)
            try:
                result.metadata = json.loads(metadata_raw)
            except (ValueError, TypeError):
                result.error = "The backup package metadata is unreadable."
                return result
            result.backup_version = int(result.metadata.get("backup_version", 0))
            result.schema_version = int(result.metadata.get("schema_version", 0))
            with tempfile.TemporaryDirectory(prefix="ncs_verify_") as tmp:
                db_tmp = Path(tmp) / PACKAGE_DB_NAME
                with archive.open(PACKAGE_DB_NAME) as source, db_tmp.open("wb") as target:
                    shutil.copyfileobj(source, target)
                result.integrity_ok, _ = _integrity_check(db_tmp)
                if not result.integrity_ok:
                    result.error = "Backup verification failed. The backup may be damaged."
                    return result
                missing = set(REQUIRED_TABLES) - _table_names(db_tmp)
                result.tables_ok = not missing
                if not result.tables_ok:
                    result.error = (
                        "Backup verification failed — required data tables are missing "
                        f"({', '.join(sorted(missing))})."
                    )
                    return result
                stored_checksum = str(result.metadata.get("database", {}).get("sha256", "") or "")
                if stored_checksum:
                    result.db_checksum_match = _sha256(db_tmp) == stored_checksum
    except zipfile.BadZipFile:
        result.error = "The selected file is not a valid backup package."
        return result

    result.ok = True
    return result


# ---------------------------------------------------------------------------
# Backup history
# ---------------------------------------------------------------------------

def get_backup_history(database, limit: int = 200) -> list[BackupRecord]:  # noqa: ANN001
    """Recent backup history records, newest first.

    Returns ``[]`` when the database is missing or damaged — reading the
    history must never block a restore of a recovered file.
    """
    try:
        with database.session_scope() as session:
            rows = (
                session.query(BackupHistory)
                .order_by(BackupHistory.created_at.desc(), BackupHistory.id.desc())
                .limit(limit)
                .all()
            )
            return [
                BackupRecord(
                    created_at=row.created_at,
                    file_name=row.file_name,
                    backup_file=row.backup_file,
                    size_bytes=row.size_bytes,
                    status=row.status,
                    verification=row.verification,
                    checksum=row.checksum,
                    reason=row.reason,
                    error_message=row.error_message,
                    location=row.location,
                )
                for row in rows
            ]
    except Exception:  # noqa: BLE001 - history is non-critical for restore
        return []


def last_successful_backup(database):  # noqa: ANN001
    """Most recent verified backup record, or ``None``."""
    records = get_backup_history(database, limit=500)
    for record in records:
        if record.status == "verified":
            return record
    return None


def find_backup_file(location: Path, file_name: str) -> Path | None:
    """Locate a backup file in a folder by its name (case-insensitive)."""
    if not location.exists():
        return None
    for candidate in location.glob(f"*{BACKUP_EXTENSION}"):
        if candidate.name.lower() == file_name.lower():
            return candidate
    return None


def list_backup_files(location: str | Path | None = None) -> list[Path]:
    """All application-owned ``.ncsbackup`` files in a folder (sorted by mtime, newest first)."""
    folder = Path(location) if location is not None else default_backup_location()
    if not folder.exists():
        return []
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == BACKUP_EXTENSION]
    return sorted(files, key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def _apply_retention(database, location: Path | None = None) -> int:  # noqa: ANN001
    """Delete the oldest application-owned backups beyond the retention count."""
    retention = _read_setting(database, KEY_BACKUP_RETENTION, str(DEFAULT_RETENTION))
    try:
        keep = max(1, int(retention or 0))
    except (TypeError, ValueError):
        keep = DEFAULT_RETENTION
    folder = location if location is not None else _resolve_location(
        _read_setting(database, KEY_BACKUP_LOCATION, "")
    )
    files = list_backup_files(folder)
    if len(files) <= keep:
        return 0
    removed = 0
    for old in files[keep:]:
        try:
            old.unlink()
            removed += 1
            logger.info("Retention removed old backup: %s", old)
        except OSError as exc:  # noqa: BLE001 - never let cleanup break a backup
            logger.warning("Could not remove old backup %s: %s", old, exc)
    return removed


# ---------------------------------------------------------------------------
# Automatic backups
# ---------------------------------------------------------------------------

def get_auto_backup_config(database) -> dict[str, Any]:  # noqa: ANN001
    with database.session_scope() as session:
        enabled = settings_service.get_bool_setting(session, KEY_BACKUP_AUTO_ENABLED, default=True)
        frequency = settings_service.get_setting(session, KEY_BACKUP_FREQUENCY, default=DEFAULT_FREQUENCY) or DEFAULT_FREQUENCY
        time_raw = settings_service.get_setting(session, KEY_BACKUP_TIME, default=DEFAULT_TIME) or DEFAULT_TIME
        retention = settings_service.get_setting(session, KEY_BACKUP_RETENTION, default=str(DEFAULT_RETENTION)) or str(DEFAULT_RETENTION)
    try:
        hour, minute = (int(part) for part in time_raw.split(":", 1))
        scheduled_time = dtime(hour, minute)
    except (ValueError, AttributeError):
        scheduled_time = dtime(21, 30)
    return {
        "enabled": enabled,
        "frequency": frequency,
        "time": scheduled_time,
        "retention": retention,
    }


def is_auto_backup_due(database) -> bool:  # noqa: ANN001
    """Whether an automatic backup is due (checked at startup / intervals)."""
    config = get_auto_backup_config(database)
    if not config["enabled"]:
        return False
    interval_days = 7 if config["frequency"] == "weekly" else 1
    last = _read_setting(database, KEY_BACKUP_LAST_SUCCESS, "")
    if not last:
        return True
    try:
        last_time = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return True
    return datetime.now() - last_time >= timedelta(days=interval_days)


def run_auto_backup(database) -> BackupResult | None:  # noqa: ANN001
    """Run the automatic backup when due; otherwise do nothing."""
    if not is_auto_backup_due(database):
        return None
    logger.info("Automatic backup triggered")
    return create_backup(database, reason="automatic", audit=False)


def set_auto_backup_config(database, *, enabled: bool, frequency: str = DEFAULT_FREQUENCY,  # noqa: ANN001
                           time_raw: str = DEFAULT_TIME, retention: int = DEFAULT_RETENTION,
                           audit: bool = True) -> None:
    if frequency not in ("daily", "weekly"):
        raise ValueError("Backup frequency must be 'daily' or 'weekly'.")
    try:
        hour, minute = (int(part) for part in time_raw.split(":", 1))
        dtime(hour, minute)
    except (ValueError, AttributeError):
        raise ValueError("Backup time must be in HH:MM format.") from None
    if int(retention or 0) < 1:
        raise ValueError("Retention must keep at least 1 backup.")
    with database.session_scope() as session:
        settings_service.set_setting(session, KEY_BACKUP_AUTO_ENABLED, "true" if enabled else "false")
        settings_service.set_setting(session, KEY_BACKUP_FREQUENCY, frequency)
        settings_service.set_setting(session, KEY_BACKUP_TIME, time_raw)
        settings_service.set_setting(session, KEY_BACKUP_RETENTION, str(int(retention)))
        if audit:
            audit_service.log_action(
                session, audit_service.ACTION_BACKUP_AUTO_CHANGED,
                f"Automatic backup {'enabled' if enabled else 'disabled'} ({frequency}).",
            )


def set_backup_location(database, location: str | Path, *, audit: bool = True) -> Path:  # noqa: ANN001
    folder = Path(location)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".ncs_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise BackupError("Backup location is not writable. Please choose another folder.") from exc
    with database.session_scope() as session:
        settings_service.set_setting(session, KEY_BACKUP_LOCATION, str(folder))
        if audit:
            audit_service.log_action(
                session, audit_service.ACTION_BACKUP_LOCATION_CHANGED, f"Backup location set to {folder}.",
            )
    return folder


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def _extract_database(archive: zipfile.ZipFile, target: Path) -> None:
    with archive.open(PACKAGE_DB_NAME) as source, target.open("wb") as destination:
        shutil.copyfileobj(source, destination)


def _restore_files(archive: zipfile.ZipFile) -> None:
    """Restore invoice PDFs and logo into the current app-data directories."""
    paths = Paths()
    names = set(archive.namelist())
    restored_invoices = [name for name in names if name.startswith(PACKAGE_INVOICES_DIR) and name.endswith(".pdf")]
    restored_assets = [name for name in names if name.startswith(PACKAGE_ASSETS_DIR)]
    for name in restored_invoices:
        target = paths.invoices_dir / Path(name).name
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(name) as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)
    logo_files = [name for name in restored_assets if not name.endswith("/")]
    return paths, logo_files


def _repair_logo_and_invoices(database, logo_files: list[str]) -> None:  # noqa: ANN001
    """Re-point the logo setting and invoice PDF paths after a restore.

    Absolute paths stored in the old database (from another machine or a
    previous data directory) are rewritten to the restored files.
    """
    paths = Paths()
    if logo_files:
        logo_name = logo_files[0]
        restored_logo = paths.assets_dir / logo_name
        if restored_logo.exists():
            with database.session_scope() as session:
                settings_service.set_setting(session, KEY_LOGO_PATH, str(restored_logo))
    from app.database.models import Invoice

    with database.session_scope() as session:
        for invoice in session.query(Invoice).all():
            if invoice.pdf_path and Path(invoice.pdf_path).exists():
                continue
            candidate = paths.invoices_dir / f"{invoice.invoice_number}.pdf"
            if candidate.exists():
                invoice.pdf_path = str(candidate)
        session.commit()


def restore_backup(database, backup_file: str | Path, *, audit: bool = True) -> RestoreResult:
    """Safely restore a ``.ncsbackup`` package. See module docstring.

    The current database is first preserved as a ``PreRestore`` safety
    backup. On failure after that point, the previous database is restored
    from the safety backup and ``recovered`` is set.
    """
    backup_path = Path(backup_file)
    logger.info("Restore started: %s", backup_path)

    verification = verify_backup_file(backup_path)
    if not verification.ok:
        raise RestoreError(verification.error or "The backup could not be verified.")

    if verification.schema_version > APP_SCHEMA_VERSION:
        raise IncompatibleBackupError(
            "This backup was created by a newer version of the application and cannot be safely restored."
        )
    if not verification.metadata.get("schema_version"):
        raise RestoreError("The backup has no schema version and cannot be safely restored.")

    database_path = Path(database.database_path)
    data_dir = database_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Safety backup of the current database (best effort, never skipped).
    safety = None
    try:
        safety_result = create_backup(
            database, reason="pre-restore", audit=False,
        )
        safety = safety_result.file_path
        logger.info("Pre-restore safety backup created: %s", safety)
    except BackupError as exc:
        logger.warning("Pre-restore safety backup failed: %s", exc)
        safety = None

    # 2. Close all open SQLite connections before touching the file.
    from app.database.database import dispose_all_databases

    dispose_all_databases()

    workdir = data_dir / f".restore_tmp_{os.getpid()}_{abs(hash(datetime.now().isoformat())) % 1000000}"
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        temp_db = workdir / PACKAGE_DB_NAME
        with zipfile.ZipFile(str(backup_path)) as archive:
            _extract_database(archive, temp_db)

            ok, _ = _integrity_check(temp_db)
            if not ok:
                raise RestoreError("Backup verification failed. The backup may be damaged.")
            missing = set(REQUIRED_TABLES) - _table_names(temp_db)
            if missing:
                raise RestoreError(
                    "The backup is missing required data tables "
                    f"({', '.join(sorted(missing))}). Restore was not performed."
                )

            # 3. Atomic replacement (same filesystem: temp sits inside data_dir).
            os.replace(temp_db, database_path)

            # 4. Restore persistent files.
            _, logo_files = _restore_files(archive)

        # 5. Reopen + verify the restored database.
        database.create_all()
        restored_health = database_health(database_path)
        if restored_health != "healthy":
            raise RestoreError("The restored database failed its integrity check.")
        restored_tables = set(REQUIRED_TABLES) - _table_names(database_path)
        if restored_tables:
            raise RestoreError("The restored database is missing required tables.")
        _repair_logo_and_invoices(database, logo_files)

    except BaseException as exc:  # noqa: BLE001 - recovery must run on any failure
        logger.exception("Restore failed; attempting recovery from safety backup")
        recovery_message = ""
        if safety is not None and safety.exists():
            try:
                dispose_all_databases()
                with zipfile.ZipFile(str(safety)) as archive:
                    safety_db = workdir / f"recovery_{PACKAGE_DB_NAME}"
                    _extract_database(archive, safety_db)
                    if _integrity_check(safety_db)[0]:
                        os.replace(safety_db, database_path)
                        database.create_all()
                        recovery_message = " Your previous data was restored from the safety backup."
                    else:
                        recovery_message = " The safety backup could not be validated."
            except BaseException:  # noqa: BLE001
                logger.exception("Recovery from safety backup also failed")
                recovery_message = " The safety backup could not be restored. Keep it for manual recovery."
        raise RestoreError(
            f"Restore failed. Your current hotel data has not been replaced.{recovery_message}"
        ) from exc
    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except OSError:
            pass

    if audit:
        with database.session_scope() as session:
            audit_service.log_action(
                session, audit_service.ACTION_BACKUP_RESTORED,
                f"Backup restored: {backup_path.name}.",
            )
    logger.info("Restore completed successfully from %s", backup_path)
    return RestoreResult(
        ok=True,
        message="Restore completed successfully. Please restart the application to complete the restore.",
        database_path=database_path,
        backup_file=backup_path,
        safety_backup=safety,
        restored_at=datetime.now(),
    )


# ---------------------------------------------------------------------------
# Deletion (Admin only)
# ---------------------------------------------------------------------------

def delete_backup_file(backup_file: str | Path, *, audit: bool = True) -> bool:
    """Delete an application-owned backup file if it exists. Never deletes arbitrary files."""
    path = Path(backup_file)
    if not path.exists():
        return False
    if path.suffix.lower() != BACKUP_EXTENSION:
        raise BackupError("Only application backup files (.ncsbackup) can be deleted.")
    path.unlink()
    logger.info("Backup deleted: %s", path)
    return True