"""Booking status change history.

Records every booking status transition (reserved → checked-in →
checked-out, cancellation, no-show) so reception can later answer
"what happened and when". ``changed_by`` defaults to "Reception"
because staff login does not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class BookingStatusHistory(Base):
    __tablename__ = "booking_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id"), index=True)
    old_status: Mapped[str] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    changed_by: Mapped[str] = mapped_column(String(100), default="Reception")
    note: Mapped[str] = mapped_column(String(500), default="")

    booking: Mapped["Booking"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BookingStatusHistory booking={self.booking_id} {self.old_status}->{self.new_status}>"
