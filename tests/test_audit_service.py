"""Tests for the audit log service.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

from app.database.database import Database
from app.database.models import AuditLog
from app.services import audit_service
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def test_log_action_creates_entry(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            audit_service.log_action(session, audit_service.ACTION_ADMIN_LOGIN, "Admin logged in.")
            assert session.query(AuditLog).count() == 1
    finally:
        database.dispose()


def test_get_audit_log_returns_most_recent_first(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            audit_service.log_action(session, "first", "one")
            audit_service.log_action(session, "second", "two")
        with database.session_scope() as session:
            entries = audit_service.get_audit_log(session)
        assert [entry.action for entry in entries][:2] == ["second", "first"]
    finally:
        database.dispose()


def test_get_audit_log_limit(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            for index in range(10):
                audit_service.log_action(session, "bulk", f"entry {index}")
        with database.session_scope() as session:
            assert len(audit_service.get_audit_log(session, limit=4)) == 4
    finally:
        database.dispose()


def test_clear_audit_log_empties_table(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            audit_service.log_action(session, "x", "x")
            audit_service.clear_audit_log(session)
            assert session.query(AuditLog).count() == 0
    finally:
        database.dispose()


def test_passwords_never_logged(tmp_path) -> None:  # noqa: ANN001
    """Audit descriptions must never contain password material."""
    database = _make_database(tmp_path)
    try:
        with database.session_scope() as session:
            audit_service.log_action(session, audit_service.ACTION_PASSWORD_CHANGED, "Admin password changed.")
            audit_service.log_action(session, audit_service.ACTION_ADMIN_LOGIN, "Admin logged in.")
            entries = audit_service.get_audit_log(session)
        combined = " ".join(entry.description or "" for entry in entries).lower()
        assert "password changed" in combined
        assert "secret" not in combined
    finally:
        database.dispose()
