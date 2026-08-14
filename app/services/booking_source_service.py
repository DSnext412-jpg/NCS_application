"""Booking source service.

Seeds the default sources on first run and provides lookups. Sources are
stored in their own table so Admin can manage them in a future phase.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import DEFAULT_BOOKING_SOURCES, OTA_PAID_ONLINE_SOURCES
from app.database.models import BookingSource


def is_ota_paid_online_source(source_name: str | None) -> bool:
    """Whether a booking source name supports the paid-online option."""
    return (source_name or "").strip() in OTA_PAID_ONLINE_SOURCES


def initialize_default_sources(session: Session) -> list[BookingSource]:
    """Insert missing default sources; never duplicates existing ones."""
    existing = {source.name for source in session.query(BookingSource).all()}
    for index, name in enumerate(DEFAULT_BOOKING_SOURCES):
        if name not in existing:
            session.add(BookingSource(name=name, sort_order=index))
    session.commit()
    return get_sources(session)


def get_sources(session: Session) -> list[BookingSource]:
    return (
        session.query(BookingSource)
        .filter(BookingSource.is_active.is_(True))
        .order_by(BookingSource.sort_order, BookingSource.name)
        .all()
    )


def get_all_sources(session: Session) -> list[BookingSource]:
    return session.query(BookingSource).order_by(BookingSource.sort_order, BookingSource.name).all()


def get_source(session: Session, source_id: int) -> BookingSource | None:
    return session.get(BookingSource, source_id)


def get_source_by_name(session: Session, name: str) -> BookingSource | None:
    return session.query(BookingSource).filter(BookingSource.name == name).first()


def add_source(session: Session, name: str) -> BookingSource:
    """Add a new booking source. Raises ValueError on duplicates/invalid input.

    Sources are never deleted — only disabled — so historical bookings keep
    their source reference.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Source name cannot be empty.")
    if len(name) > 100:
        raise ValueError("Source name must be 100 characters or fewer.")
    existing = get_source_by_name(session, name)
    if existing is not None:
        if existing.is_active:
            raise ValueError(f"Booking source {name!r} already exists.")
        existing.is_active = True
        session.commit()
        return existing
    max_order = session.query(func.max(BookingSource.sort_order)).scalar() or 0
    source = BookingSource(name=name, sort_order=max_order + 1)
    session.add(source)
    session.commit()
    return source


def set_source_active(session: Session, source_id: int, active: bool) -> BookingSource:
    """Enable or disable a source (disable = hidden from new bookings)."""
    source = get_source(session, source_id)
    if source is None:
        raise ValueError("Booking source not found.")
    source.is_active = bool(active)
    session.commit()
    return source
