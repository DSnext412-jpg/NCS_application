"""Admin Settings service.

Handles the configuration edits only an Admin can make: hotel identity and
contact details, website, logo management and booking sources. Changes are
persisted via the settings/source tables and should be audited by the caller
(:func:`app.services.audit_service.log_action`).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import (
    KEY_HOTEL_ADDRESS,
    KEY_HOTEL_DESCRIPTION,
    KEY_HOTEL_EMAIL,
    KEY_HOTEL_NAME,
    KEY_HOTEL_PHONE,
    KEY_HOTEL_WEBSITE,
    KEY_LOGO_PATH,
)
from app.core.paths import Paths
from app.database.models import BookingSource
from app.services import booking_source_service, settings_service

_WEBSITE_MAX_LENGTH = 200
_PHONE_MAX_LENGTH = 30
_EMAIL_MAX_LENGTH = 120


class ValidationError(Exception):
    """Raised when admin settings input is invalid."""


def _clean(value: str) -> str:
    return (value or "").strip()


def validate_website(value: str) -> str:
    """Return the normalized website (no scheme) or raise ValidationError."""
    website = _clean(value)
    if not website:
        return ""
    if len(website) > _WEBSITE_MAX_LENGTH:
        raise ValidationError("Website must be 200 characters or fewer.")
    candidate = website if "://" in website else f"http://{website}"
    try:
        parsed = urlparse(candidate)
    except ValueError:
        raise ValidationError("Please enter a valid website address.") from None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValidationError("Please enter a valid website address.")
    host = parsed.netloc.lower()
    if "." not in host and host not in ("localhost",):
        raise ValidationError("Please enter a valid website address.")
    return website


def update_hotel_info(
    session: Session,
    name: str,
    description: str,
    address: str,
    phone: str,
    email: str,
    website: str,
) -> None:
    """Validate and save hotel identity/contact settings."""
    name = _clean(name)
    if not name:
        raise ValidationError("Hotel name is required.")
    if len(name) > 120:
        raise ValidationError("Hotel name must be 120 characters or fewer.")
    if len(description) > 500:
        raise ValidationError("Description must be 500 characters or fewer.")
    if len(address) > 500:
        raise ValidationError("Address must be 500 characters or fewer.")
    if len(phone) > _PHONE_MAX_LENGTH:
        raise ValidationError("Phone must be 30 characters or fewer.")
    if len(email) > _EMAIL_MAX_LENGTH:
        raise ValidationError("Email must be 120 characters or fewer.")
    website = validate_website(website)

    settings_service.set_setting(session, KEY_HOTEL_NAME, name)
    settings_service.set_setting(session, KEY_HOTEL_DESCRIPTION, description)
    settings_service.set_setting(session, KEY_HOTEL_ADDRESS, address)
    settings_service.set_setting(session, KEY_HOTEL_PHONE, phone)
    settings_service.set_setting(session, KEY_HOTEL_EMAIL, email)
    settings_service.set_setting(session, KEY_HOTEL_WEBSITE, website)


def get_logo_path(session: Session) -> str | None:
    path = settings_service.get_setting(session, KEY_LOGO_PATH, "")
    if not path:
        return None
    return path if Path(path).exists() else None


def upload_logo(session: Session, source_path: str | Path) -> str:
    """Copy a logo image into the assets dir and return its stored path.

    The old logo file is removed. The stored path is the copied file, so a
    deleted original never breaks the app.
    """
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        raise ValidationError("Logo file not found.")
    suffix = source.suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".gif"):
        raise ValidationError("Logo must be a PNG, JPG, JPEG or GIF image.")
    assets = Paths().assets_dir
    assets.mkdir(parents=True, exist_ok=True)
    old = get_logo_path(session)
    target = assets / f"logo{suffix}"
    shutil.copyfile(source, target)
    settings_service.set_setting(session, KEY_LOGO_PATH, str(target))
    if old and Path(old).resolve() != target.resolve():
        try:
            Path(old).unlink(missing_ok=True)
        except OSError:  # noqa: BLE001 - deleting the old logo is best-effort
            pass
    return str(target)


def remove_logo(session: Session) -> None:
    """Remove the stored logo file and clear the setting."""
    old = get_logo_path(session)
    settings_service.set_setting(session, KEY_LOGO_PATH, "")
    if old:
        try:
            Path(old).unlink(missing_ok=True)
        except OSError:  # noqa: BLE001 - best-effort cleanup
            pass


def get_booking_sources(session: Session) -> list[BookingSource]:
    """All sources (active and disabled) for the Admin settings list."""
    return booking_source_service.get_all_sources(session)


def add_booking_source(session: Session, name: str) -> BookingSource:
    """Add a new booking source (raises ValueError on duplicate/invalid)."""
    return booking_source_service.add_source(session, name)


def set_booking_source_active(session: Session, source_id: int, active: bool) -> BookingSource:
    """Enable/disable a booking source."""
    return booking_source_service.set_source_active(session, source_id, active)
