"""Tests for admin security: hashing, first-run setup, login lockout,
password change and session timeouts.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.core.config import (
    ADMIN_LOCKOUT_SECONDS,
    ADMIN_MAX_FAILED_ATTEMPTS,
    DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES,
)
from app.database.database import Database
from app.services import security_service, settings_service
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        settings_service.initialize_default_settings(session)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_hash_password_never_stores_plaintext(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            stored = settings_service.get_setting(session, "admin_password_hash")
        assert stored
        assert stored.startswith("pbkdf2_sha256$")
        assert "secret123" not in stored
    finally:
        database.dispose()


def test_hash_is_salted_and_different_each_time(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        first = security_service.hash_password("secret123")
        second = security_service.hash_password("secret123")
        assert first != second
        assert security_service.verify_password("secret123", first)
        assert security_service.verify_password("secret123", second)
        assert not security_service.verify_password("wrongpass", first)
        assert not security_service.verify_password("", first)
    finally:
        database.dispose()


def test_verify_password_rejects_malformed_hash(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        assert security_service.verify_password("x", "not-a-hash") is False
        assert security_service.verify_password("x", "md5$1000$c2FsdA==$abc") is False
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------

def test_password_not_set_by_default(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert security_service.is_password_set(session) is False
    finally:
        database.dispose()


def test_initialize_admin_password_then_login_succeeds(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            assert security_service.is_password_set(session) is True
            assert security_service.verify_admin_password(session, "secret123") is True
    finally:
        database.dispose()


def test_initialize_refuses_to_overwrite(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            with pytest.raises(security_service.PasswordAlreadySetError):
                security_service.initialize_admin_password(session, "other456")
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Failed attempts + lockout
# ---------------------------------------------------------------------------

def test_wrong_password_returns_false(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            assert security_service.verify_admin_password(session, "bad") is False
    finally:
        database.dispose()


def test_failed_attempts_tracked_and_lockout_engaged(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            for _ in range(ADMIN_MAX_FAILED_ATTEMPTS - 1):
                assert security_service.verify_admin_password(session, "bad") is False
            allowed, remaining = security_service.check_login_allowed(session)
            assert allowed is True
            with pytest.raises(security_service.LoginLockedError):
                security_service.verify_admin_password(session, "bad")
            allowed, remaining = security_service.check_login_allowed(session)
            assert allowed is False
            assert 0 < remaining <= ADMIN_LOCKOUT_SECONDS + 1
    finally:
        database.dispose()


def test_successful_login_resets_failures(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            assert security_service.verify_admin_password(session, "bad") is False
            assert security_service.verify_admin_password(session, "secret123") is True
            allowed, _ = security_service.check_login_allowed(session)
            assert allowed is True
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Password rules + change
# ---------------------------------------------------------------------------

def test_validate_new_password_enforces_min_length_and_match(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        with pytest.raises(security_service.WeakPasswordError):
            security_service.validate_new_password("short", "short")
        with pytest.raises(security_service.PasswordMismatchError):
            security_service.validate_new_password("longenough1", "different")
        security_service.validate_new_password("longenough1", "longenough1")
    finally:
        database.dispose()


def test_change_password_requires_current(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            with pytest.raises(security_service.IncorrectPasswordError):
                security_service.change_admin_password(
                    session,
                    current_password="wrong",
                    new_password="newpass456",
                    confirm_password="newpass456",
                )
            security_service.change_admin_password(
                session,
                current_password="secret123",
                new_password="newpass456",
                confirm_password="newpass456",
            )
            assert security_service.verify_admin_password(session, "newpass456") is True
            assert security_service.verify_admin_password(session, "secret123") is False
    finally:
        database.dispose()


def test_change_password_rejects_weak_and_mismatch(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.initialize_admin_password(session, "secret123")
            with pytest.raises(security_service.WeakPasswordError):
                security_service.change_admin_password(
                    session, current_password="secret123", new_password="ab", confirm_password="ab"
                )
            with pytest.raises(security_service.PasswordMismatchError):
                security_service.change_admin_password(
                    session, current_password="secret123", new_password="newpass456", confirm_password="nomatch"
                )
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def test_admin_session_expires_after_timeout(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        session = security_service.AdminSession(timeout_minutes=1)
        now = datetime.now()
        assert session.is_active(now) is True
        assert session.is_active(now + timedelta(minutes=2)) is False
        session.touch(now + timedelta(minutes=0.5))
        assert session.is_active(now + timedelta(minutes=1.2)) is True
        session.logout()
        assert session.is_active() is False
    finally:
        database.dispose()


def test_default_session_timeout_used_when_unset(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            assert security_service.session_timeout_minutes(session) == DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES
    finally:
        database.dispose()


def test_session_timeout_settable_and_validated(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            security_service.set_session_timeout_minutes(session, 30)
            assert security_service.session_timeout_minutes(session) == 30
            with pytest.raises(ValueError):
                security_service.set_session_timeout_minutes(session, 0)
            with pytest.raises(ValueError):
                security_service.set_session_timeout_minutes(session, "abc")
    finally:
        database.dispose()
