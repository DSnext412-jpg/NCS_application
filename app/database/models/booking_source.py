"""Booking source model.

Stored separately from bookings so Admin can add/edit/disable sources in
a future phase without touching booking records.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BookingSource(Base):
    __tablename__ = "booking_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="source")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BookingSource {self.name!r}>"
