"""Room configuration model.

Rooms are deliberately stored WITHOUT any price column: room rates and
extra-person charges are entered manually by reception staff at booking
time. This table simply records which rooms exist and their category.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_number: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    room_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="vacant")
    floor: Mapped[str] = mapped_column(String(20), default="")
    notes: Mapped[str] = mapped_column(String(500), default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    status_history: Mapped[list["RoomStatusHistory"]] = relationship(
        back_populates="room",
        order_by="RoomStatusHistory.changed_at",
    )

    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Room {self.room_number} ({self.room_type}) status={self.status}>"
