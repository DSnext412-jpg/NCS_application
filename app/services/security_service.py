from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import (
    ADMIN_LOCKOUT_SECONDS,ADMIN_MAX_FAILED_ATTEMPTS,
    DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES, KEY_ADMIN_FAILED_ATTEMPTS,
    KEY_ADMIN_LOCKED_UNTIL,KEY_ADMIN_PASSWORD_HASH, KEY_ADMIN_PASSWORD_SET,KEY_ADMIN_SESSION_TIMEOUT_MINUTES,
)
from app.services import settings_service

_ITERATIONS = 210_000
_ALGORITHM = "pbkdf2_sha256"
_SALT_BYTES = 16
_MIN_PASSWORD_LENGTH = 8

class SecurityError(Exception):

class PasswordNotSetError(SecurityError):

class PasswordAlreadySetError(SecurityError):

class IncorrectPasswordError(SecurityError):

class PasswordMismatchError(SecurityError):

class WeakPasswordError(SecurityError):

class LoginLockedError(SecurityError):

class SessionExpiredError(SecurityError):

def hash_password(password: str) -> str:
    if not password:
        raise WeakPasswordError("Password cannot be empty.")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    salt_b64 = base64.b64encode(salt).decode("ascii")
    digest_b64 = base64.b64encode(digest).decode("ascii")
    return f"{_ALGORITHM}${_ITERATIONS}${salt_b64}${digest_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
        if algorithm != _ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)

def validate_new_password(new_password: str, confirm_password: str) -> None:
    new_password = new_password or ""
    confirm_password = confirm_password or ""
    if len(new_password) < _MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters."
        )
    if new_password != confirm_password:
        raise PasswordMismatchError("New password and confirmation do not match.")


def is_password_set(session: Session) -> bool:
    flag = settings_service.get_bool_setting(session, KEY_ADMIN_PASSWORD_SET, default=False)
    if flag:
        return True
    stored = settings_service.get_setting(session, KEY_ADMIN_PASSWORD_HASH, default="")
    return bool(stored)


def initialize_admin_password(session: Session, new_password: str) -> None:
    if is_password_set(session):
        raise PasswordAlreadySetError(
            "Admin password is already set. Use Change Password instead."
        )
    stored = hash_password(new_password)
    settings_service.set_setting(session, KEY_ADMIN_PASSWORD_HASH, stored)
    settings_service.set_setting(session, KEY_ADMIN_PASSWORD_SET, "true")
    settings_service.set_setting(session, KEY_ADMIN_FAILED_ATTEMPTS, "0")
    _clear_lockout(session)


def _stored_hash(session: Session) -> str:
    return settings_service.get_setting(session, KEY_ADMIN_PASSWORD_HASH, default="") or ""

def _clear_lockout(session: Session) -> None:
    settings_service.set_setting(session, KEY_ADMIN_LOCKED_UNTIL, "")


def _failed_attempts(session: Session) -> int:
    try:
        return int(settings_service.get_setting(session, KEY_ADMIN_FAILED_ATTEMPTS, "0") or 0)
    except ValueError:
        return 0


def get_lockout_seconds(session: Session) -> int:
    raw = settings_service.get_setting(session, KEY_ADMIN_LOCKED_UNTIL, default="")
    if not raw:
        return 0
    try:
        locked_until = datetime.fromisoformat(raw)
    except ValueError:
        return 0
    remaining = (locked_until - datetime.now()).total_seconds()
    return max(0, int(remaining) + 1)


def check_login_allowed(session: Session) -> tuple[bool, int]:
    remaining = get_lockout_seconds(session)
    if remaining > 0:
        return False, remaining
    return True, 0


def _record_failure(session: Session) -> int:
    attempts = _failed_attempts(session) + 1
    settings_service.set_setting(session, KEY_ADMIN_FAILED_ATTEMPTS, str(attempts))
    if attempts >= ADMIN_MAX_FAILED_ATTEMPTS:
        locked_until = datetime.now() + timedelta(seconds=ADMIN_LOCKOUT_SECONDS)
        settings_service.set_setting(session, KEY_ADMIN_LOCKED_UNTIL, locked_until.isoformat())
        settings_service.set_setting(session, KEY_ADMIN_FAILED_ATTEMPTS, "0")
    return attempts


def _reset_failures(session: Session) -> None:
    settings_service.set_setting(session, KEY_ADMIN_FAILED_ATTEMPTS, "0")
    _clear_lockout(session)


def verify_admin_password(session: Session, password: str) -> bool:

    allowed, _ = check_login_allowed(session)
    if not allowed:
        raise LoginLockedError(
            "Too many failed attempts. Please try again in a moment."
        )
    if not is_password_set(session):
        raise PasswordNotSetError(
            "The admin password has not been initialized yet."
        )
    if verify_password(password, _stored_hash(session)):
        _reset_failures(session)
        return True
    attempts = _record_failure(session)
    if attempts >= ADMIN_MAX_FAILED_ATTEMPTS:
        raise LoginLockedError(
            "Too many failed attempts. Please try again in a moment."
        )
    return False


def change_admin_password(
    session: Session,
    *,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> None:
    if not is_password_set(session):
        raise PasswordNotSetError(
            "The admin password has not been initialized yet."
        )
    if not verify_password(current_password, _stored_hash(session)):
        raise IncorrectPasswordError("Current password is incorrect.")
    validate_new_password(new_password, confirm_password)
    settings_service.set_setting(session, KEY_ADMIN_PASSWORD_HASH, hash_password(new_password))
    _reset_failures(session)


class AdminSession:

    def __init__(
        self,
        *,
        timeout_minutes: int | None = None,
        now: datetime | None = None,
    ) -> None:
        self._now = now or datetime.now()
        self.started_at = self._now
        self.last_activity = self._now
        self.timeout_minutes = timeout_minutes

    def touch(self, now: datetime | None = None) -> None:
        self.last_activity = now or datetime.now()

    def _effective_timeout(self) -> timedelta:
        minutes = self.timeout_minutes or DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES
        return timedelta(minutes=minutes)

    def is_active(self, now: datetime | None = None) -> bool:
        return self.seconds_remaining(now) > 0

    def seconds_remaining(self, now: datetime | None = None) -> int:
        now = now or datetime.now()
        deadline = self.last_activity + self._effective_timeout()
        return max(0, int((deadline - now).total_seconds()))

    def expire(self) -> None:
        self.last_activity = datetime.min

    def logout(self) -> None:
        self.expire()


def session_timeout_minutes(session: Session) -> int:
    raw = settings_service.get_setting(
        session, KEY_ADMIN_SESSION_TIMEOUT_MINUTES,
        default=str(DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES),
    )
    try:
        minutes = int(raw or 0)
    except ValueError:
        minutes = 0
    return minutes if minutes > 0 else DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES


def set_session_timeout_minutes(session: Session, minutes: int) -> None:
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise ValueError("Session timeout must be a whole number of minutes.") from None
    if minutes < 1:
        raise ValueError("Session timeout must be at least 1 minute.")
    settings_service.set_setting(session, KEY_ADMIN_SESSION_TIMEOUT_MINUTES, str(minutes))
