"""Guest service.

All guest business logic lives here. Guests are never deleted when a
booking is cancelled; relationships keep history intact.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.constants import BookingStatus
from app.database.models import Booking, Guest

logger = logging.getLogger(__name__)

DEFAULT_ADDRESS_VALUES = {"city": "Nashik", "state": "Maharashtra", "country": "India"}

_SEARCH_LIMIT = 100


class GuestError(Exception):
    """Base exception for guest domain errors."""


class GuestValidationError(GuestError):
    """Raised when required guest fields are missing/invalid."""


def _require(value: str | None, field_label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise GuestValidationError(f"{field_label} is required.")
    return text


def validate_mobile(mobile: str | None) -> str:
    """Return the cleaned mobile number or raise a clear validation error."""
    text = (mobile or "").strip()
    if not text:
        raise GuestValidationError("Mobile Number is required.")
    if not all(char.isdigit() or char in "+- ()" for char in text):
        raise GuestValidationError(
            "Mobile Number can only contain digits, spaces and the + - ( ) characters."
        )
    return text


def create_guest(
    session: Session,
    *,
    guest_name: str,
    mobile_number: str,
    alternate_number: str = "",
    address: str = "",
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    id_type: str = "",
    id_number: str = "",
    adults: int = 1,
    children: int = 0,
    special_notes: str = "",
) -> Guest:
    name = _require(guest_name, "Guest Name")
    mobile = validate_mobile(mobile_number)
    guest = Guest(
        guest_name=name,
        mobile_number=mobile,
        alternate_number=(alternate_number or "").strip(),
        address=(address or "").strip(),
        city=(city or DEFAULT_ADDRESS_VALUES["city"]).strip(),
        state=(state or DEFAULT_ADDRESS_VALUES["state"]).strip(),
        country=(country or DEFAULT_ADDRESS_VALUES["country"]).strip(),
        id_type=(id_type or "").strip(),
        id_number=(id_number or "").strip(),
        adults=max(0, int(adults or 0)),
        children=max(0, int(children or 0)),
        special_notes=(special_notes or "").strip(),
    )
    session.add(guest)
    session.commit()
    logger.info("Guest created: %s (%s)", guest.guest_name, guest.mobile_number)
    return guest


def update_guest(
    session: Session,
    guest_id: int,
    *,
    guest_name: str | None = None,
    mobile_number: str | None = None,
    alternate_number: str | None = None,
    address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    id_type: str | None = None,
    id_number: str | None = None,
    adults: int | None = None,
    children: int | None = None,
    special_notes: str | None = None,
) -> Guest:
    guest = get_guest(session, guest_id)
    if guest is None:
        raise GuestError(f"Guest {guest_id!r} not found")

    if guest_name is not None:
        guest.guest_name = _require(guest_name, "Guest Name")
    if mobile_number is not None:
        guest.mobile_number = validate_mobile(mobile_number)
    if alternate_number is not None:
        guest.alternate_number = (alternate_number or "").strip()
    if address is not None:
        guest.address = (address or "").strip()
    if city is not None:
        guest.city = (city or "").strip()
    if state is not None:
        guest.state = (state or "").strip()
    if country is not None:
        guest.country = (country or "").strip()
    if id_type is not None:
        guest.id_type = (id_type or "").strip()
    if id_number is not None:
        guest.id_number = (id_number or "").strip()
    if adults is not None:
        guest.adults = max(0, int(adults))
    if children is not None:
        guest.children = max(0, int(children))
    if special_notes is not None:
        guest.special_notes = (special_notes or "").strip()

    session.commit()
    logger.info("Guest %s updated", guest_id)
    return guest


def get_guest(session: Session, guest_id: int) -> Guest | None:
    return session.get(Guest, guest_id)


def find_guest_by_mobile(session: Session, mobile_number: str) -> Guest | None:
    """Duplicate detection: find an active guest with the same mobile."""
    mobile = (mobile_number or "").strip()
    if not mobile:
        return None
    return (
        session.query(Guest)
        .filter(Guest.mobile_number == mobile, Guest.is_active.is_(True))
        .first()
    )


def search_guests(session: Session, query: str, limit: int = _SEARCH_LIMIT) -> list[Guest]:
    """Case-insensitive search over guest name and mobile number."""
    text = (query or "").strip()
    base = session.query(Guest).options(joinedload(Guest.bookings))
    if not text:
        return base.filter(Guest.is_active.is_(True)).order_by(Guest.guest_name).limit(limit).all()
    pattern = f"%{text.lower()}%"
    return (
        base.filter(
            Guest.is_active.is_(True),
            or_(
                func.lower(Guest.guest_name).like(pattern),
                func.lower(Guest.mobile_number).like(pattern),
            ),
        )
        .order_by(Guest.guest_name)
        .limit(limit)
        .all()
    )


def get_all_guests(session: Session) -> list[Guest]:
    return session.query(Guest).filter(Guest.is_active.is_(True)).order_by(Guest.guest_name).all()


def get_guest_booking_history(session: Session, guest_id: int) -> list[Booking]:
    return (
        session.query(Booking)
        .options(joinedload(Booking.room))
        .filter(
            Booking.guest_id == guest_id,
            Booking.status != BookingStatus.DELETED.value,
        )
        .order_by(Booking.check_in_date.desc(), Booking.id.desc())
        .all()
    )
