"""Booking charge model.

Manual charges reception can add to a booking — extra mattresses,
miscellaneous and other charges. The base charges (room rate, extra
person, early check-in, late check-out) are stored directly on the
booking and are NOT duplicated here; ``ROOM``-type rows represent an
additional manual room charge (e.g. same-day stays where the derived
room charge is zero).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BookingCharge(Base):
    __tablename__ = "booking_charges"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    charge_type: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="charges")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BookingCharge id={self.id} booking={self.booking_id} {self.charge_type}>"
