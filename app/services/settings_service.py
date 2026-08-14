"""Hotel settings service.

Small read/write helpers on top of the :class:`HotelSetting` table plus a
seeding routine used at startup to populate the default settings.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import DEFAULT_HOTEL_SETTINGS, KEY_HOTEL_ADDRESS, KEY_HOTEL_DESCRIPTION, KEY_HOTEL_EMAIL, KEY_HOTEL_NAME, KEY_HOTEL_PHONE, KEY_HOTEL_WEBSITE, KEY_LOGO_PATH
from app.database.models import HotelSetting


def get_settings(session: Session) -> dict[str, str]:
    """Return all settings as a ``{key: value}`` dict."""
    return {row.key: row.value for row in session.query(HotelSetting).all()}


def get_setting(session: Session, key: str, default: str | None = None) -> str | None:
    row = session.query(HotelSetting).filter(HotelSetting.key == key).first()
    return row.value if row is not None else default


def get_bool_setting(session: Session, key: str, default: bool = False) -> bool:
    value = get_setting(session, key)
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def set_setting(session: Session, key: str, value: Any) -> None:
    row = session.query(HotelSetting).filter(HotelSetting.key == key).first()
    if row is None:
        row = HotelSetting(key=key, value=str(value))
        session.add(row)
    else:
        row.value = str(value)
    session.commit()


def initialize_default_settings(session: Session) -> dict[str, str]:
    """Insert missing default settings, leaving existing values untouched."""
    existing = {row.key for row in session.query(HotelSetting).all()}
    for key, value in DEFAULT_HOTEL_SETTINGS.items():
        if key not in existing:
            session.add(HotelSetting(key=key, value=value))
    session.commit()
    return get_settings(session)


def get_hotel_settings(session: Session) -> dict[str, str]:
    """Hotel identity/contact settings (keys starting with ``hotel_``)."""
    settings = get_settings(session)
    keys = [
        KEY_HOTEL_NAME,
        KEY_HOTEL_DESCRIPTION,
        KEY_HOTEL_ADDRESS,
        KEY_HOTEL_PHONE,
        KEY_HOTEL_EMAIL,
        KEY_HOTEL_WEBSITE,
        KEY_LOGO_PATH,
    ]
    return {key: settings.get(key, "") for key in keys}
