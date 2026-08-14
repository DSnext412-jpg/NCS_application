"""Payment model.

Every payment received against a booking. Payments are never deleted —
a completed payment can be reversed (``status`` → ``reversed`` /
``refunded``) so the history stays auditable. ``status`` is
``completed`` by default; ``reversed_at`` and ``reversal_reason`` are
set when a payment is reversed.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id"), index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    payment_method: Mapped[str] = mapped_column(String(30), default="cash")
    payment_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    reference_number: Mapped[str] = mapped_column(String(100), default="")
    notes: Mapped[str] = mapped_column(String(500), default="")

    status: Mapped[str] = mapped_column(String(20), default="completed", index=True)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reversal_reason: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="payments")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Payment id={self.id} booking={self.booking_id} {self.amount} {self.status}>"
