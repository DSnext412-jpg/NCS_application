"""Shared test database infrastructure.

Builds one fully migrated and seeded SQLite template per test session and
copies it into each test's temporary directory. Tests therefore keep a fresh,
isolated database without paying the schema-creation cost for every test, and
the production ``data/hotel.db`` is never touched.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from app.database.database import Database

_TEMPLATE_PATH: Path | None = None


def _build_template() -> Path:
    """Create a fresh, fully migrated and seeded database file once."""
    from app.services import room_service
    from app.services.booking_source_service import initialize_default_sources
    from app.services.settings_service import initialize_default_settings

    directory = Path(tempfile.mkdtemp(prefix="ncs_db_template_"))
    database = Database(directory / "hotel.db")
    database.create_all()
    with database.session_scope() as session:
        initialize_default_settings(session)
        room_service.initialize_default_rooms(session)
        initialize_default_sources(session)
    database.dispose()
    return directory / "hotel.db"


def copy_db_template(target: Path) -> Path:
    """Copy the session template database file to ``target`` and return it.

    The template is built lazily on first use and reused for every test.
    """
    global _TEMPLATE_PATH
    if _TEMPLATE_PATH is None or not _TEMPLATE_PATH.exists():
        _TEMPLATE_PATH = _build_template()
    shutil.copyfile(_TEMPLATE_PATH, target)
    return target


def cleanup_template() -> None:
    """Remove the cached template file and its directory."""
    global _TEMPLATE_PATH
    if _TEMPLATE_PATH is not None:
        try:
            _TEMPLATE_PATH.unlink(missing_ok=True)
            _TEMPLATE_PATH.parent.rmdir()
        except OSError:
            pass
        _TEMPLATE_PATH = None
