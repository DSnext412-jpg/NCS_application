"""Room configuration and status service.

All room business logic lives here. UI widgets must never touch the
database directly; they call these functions. Prices are never stored —
room rates and extra-person charges are entered manually per booking in
a future phase.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import DEFAULT_ROOMS
from app.core.constants import RoomStatus
from app.database.models import Room, RoomStatusHistory

logger = logging.getLogger(__name__)

# Recommended status flows. Reception may correct any status manually
# through a confirmation dialog, so these transitions are advisory and
# never block a manual correction.
ALLOWED_TRANSITIONS: dict[RoomStatus, set[RoomStatus]] = {
    RoomStatus.VACANT: {RoomStatus.OCCUPIED, RoomStatus.RESERVED},
    RoomStatus.OCCUPIED: {RoomStatus.CLEANING, RoomStatus.RESERVED},
    RoomStatus.RESERVED: {RoomStatus.OCCUPIED, RoomStatus.VACANT},
    RoomStatus.CLEANING: {RoomStatus.VACANT, RoomStatus.OCCUPIED, RoomStatus.RESERVED},
}

_COUNT_KEYS = ("vacant", "occupied", "reserved", "cleaning")


def is_allowed_transition(old_status: str | RoomStatus, new_status: str | RoomStatus) -> bool:
    """Whether ``new_status`` is a typical next state for ``old_status``."""
    try:
        old = _coerce_status(old_status)
        new = _coerce_status(new_status)
    except ValueError:
        return False
    return new in ALLOWED_TRANSITIONS[old]


def _coerce_status(value: str | RoomStatus) -> RoomStatus:
    """Normalize a status value to a :class:`RoomStatus` or raise ValueError."""
    if isinstance(value, RoomStatus):
        return value
    normalized = str(value).strip().lower()
    for status in RoomStatus:
        if normalized in (status.value, status.name.lower()):
            return status
    raise ValueError(f"Invalid room status: {value!r}")


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def initialize_default_rooms(session: Session) -> list[Room]:
    """Insert the standard rooms that are missing; keep existing ones.

    Safe to call repeatedly — never duplicates or destroys room records.
    """
    existing = {room.room_number for room in session.query(Room).all()}
    for index, spec in enumerate(DEFAULT_ROOMS):
        if spec["room_number"] not in existing:
            session.add(
                Room(
                    room_number=spec["room_number"],
                    room_type=spec["room_type"],
                    status=RoomStatus.VACANT.value,
                    sort_order=index,
                )
            )
    session.commit()
    return get_all_rooms(session, include_inactive=True)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def get_all_rooms(session: Session, include_inactive: bool = False) -> list[Room]:
    query = session.query(Room)
    if not include_inactive:
        query = query.filter(Room.is_active.is_(True))
    return query.order_by(Room.sort_order, Room.room_number).all()


def get_rooms(session: Session) -> list[Room]:
    """Backward-compatible alias returning all rooms (including inactive)."""
    return get_all_rooms(session, include_inactive=True)


def get_room(session: Session, room_id: int | str) -> Room | None:
    """Get a room by primary key ``id`` (int) or room number (str)."""
    if isinstance(room_id, int):
        return session.get(Room, room_id)
    return session.query(Room).filter(Room.room_number == room_id).first()


def get_room_by_number(session: Session, room_number: str) -> Room | None:
    return session.query(Room).filter(Room.room_number == room_number).first()


def get_status_history(session: Session, room_id: int) -> list[RoomStatusHistory]:
    return (
        session.query(RoomStatusHistory)
        .filter(RoomStatusHistory.room_id == room_id)
        .order_by(RoomStatusHistory.changed_at.desc(), RoomStatusHistory.id.desc())
        .all()
    )


def get_room_status_counts(session: Session) -> dict[str, int]:
    """Live counts for the dashboard, computed from the database.

    Counts only active rooms. Keys: total, vacant, occupied, reserved.
    """
    counts = {key: 0 for key in _COUNT_KEYS}
    total = 0
    for room in session.query(Room).filter(Room.is_active.is_(True)):
        total += 1
        if room.status in counts:
            counts[room.status] += 1
    return {"total": total, **counts}


def get_room_summary(session: Session) -> dict[str, int]:
    """Alias for :func:`get_room_status_counts` used by the dashboard."""
    return get_room_status_counts(session)


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

def update_room_status(
    session: Session,
    room_id: int | str,
    new_status: str | RoomStatus,
    note: str = "",
    changed_by: str = "Reception",
) -> Room:
    """Change a room's status and record it in the history table."""
    status = _coerce_status(new_status)
    room = get_room(session, room_id)
    if room is None:
        raise KeyError(f"Room {room_id!r} not found")

    old_status = room.status
    if old_status != status.value:
        room.status = status.value
        session.add(
            RoomStatusHistory(
                room_id=room.id,
                old_status=old_status,
                new_status=status.value,
                changed_by=changed_by,
                note=(note or "").strip(),
            )
        )
        session.commit()
        session.refresh(room)
        logger.info("Room %s status changed %s -> %s (by %s)", room.room_number, old_status, status.value, changed_by)
    return room


def set_room_vacant(session: Session, room_id: int | str, note: str = "", changed_by: str = "Reception") -> Room:
    return update_room_status(session, room_id, RoomStatus.VACANT, note, changed_by)


def set_room_occupied(session: Session, room_id: int | str, note: str = "", changed_by: str = "Reception") -> Room:
    return update_room_status(session, room_id, RoomStatus.OCCUPIED, note, changed_by)


def set_room_reserved(session: Session, room_id: int | str, note: str = "", changed_by: str = "Reception") -> Room:
    return update_room_status(session, room_id, RoomStatus.RESERVED, note, changed_by)


def set_room_cleaning(session: Session, room_id: int | str, note: str = "", changed_by: str = "Reception") -> Room:
    return update_room_status(session, room_id, RoomStatus.CLEANING, note, changed_by)


def update_room_notes(session: Session, room_id: int | str, notes: str) -> Room:
    room = get_room(session, room_id)
    if room is None:
        raise KeyError(f"Room {room_id!r} not found")
    room.notes = (notes or "").strip()
    session.commit()
    logger.info("Room %s notes updated", room.room_number)
    return room


def set_room_active(session: Session, room_id: int | str, active: bool) -> Room:
    room = get_room(session, room_id)
    if room is None:
        raise KeyError(f"Room {room_id!r} not found")
    room.is_active = bool(active)
    session.commit()
    logger.info("Room %s %s", room.room_number, "activated" if room.is_active else "deactivated")
    return room
