"""Guest model.

Only guest identity metadata is stored — never document files. Document
attachments can be added in a future phase. Only ``guest_name`` and
``mobile_number`` are required; everything else is optional so reception
can continue even when optional details are unknown.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    guest_name: Mapped[str] = mapped_column(String(120), index=True)
    mobile_number: Mapped[str] = mapped_column(String(30), index=True)
    alternate_number: Mapped[str] = mapped_column(String(30), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    city: Mapped[str] = mapped_column(String(100), default="Nashik")
    state: Mapped[str] = mapped_column(String(100), default="Maharashtra")
    country: Mapped[str] = mapped_column(String(100), default="India")
    id_type: Mapped[str] = mapped_column(String(50), default="")
    id_number: Mapped[str] = mapped_column(String(100), default="")
    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    special_notes: Mapped[str] = mapped_column(String(1000), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="guest")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Guest {self.guest_name!r} ({self.mobile_number})>"
