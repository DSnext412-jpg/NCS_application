"""Booking model.

Represents a reservation or a walk-in stay. Room rates and all charges
are entered manually by reception at booking time and stored on the
booking, so future price changes never modify existing bookings.
"""

from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    booking_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    guest_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("guests.id"), index=True, nullable=True)
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), index=True)
    booking_source_id: Mapped[int] = mapped_column(Integer, ForeignKey("booking_sources.id"), index=True)

    check_in_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    check_out_date: Mapped[date] = mapped_column(Date, index=True)
    check_out_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    adults: Mapped[int] = mapped_column(Integer, default=1)
    children: Mapped[int] = mapped_column(Integer, default=0)
    room_rate: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    extra_person_charge: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    early_check_in_charge: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    late_check_out_charge: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    paid_online: Mapped[bool] = mapped_column(Boolean, default=False)
    special_notes: Mapped[str] = mapped_column(String(1000), default="")

    status: Mapped[str] = mapped_column(String(30), default="reserved", index=True)

    actual_check_out_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(500), default="")
    cancelled_by: Mapped[str] = mapped_column(String(100), default="")
    no_show_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    no_show_reason: Mapped[str] = mapped_column(String(500), default="")

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    deleted_by: Mapped[str] = mapped_column(String(100), default="")
    deletion_reason: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    guest: Mapped["Guest"] = relationship(back_populates="bookings")
    room: Mapped["Room"] = relationship(back_populates="bookings")
    source: Mapped["BookingSource"] = relationship(back_populates="bookings")
    charges: Mapped[list["BookingCharge"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingCharge.id",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="Payment.id",
    )
    invoices: Mapped[list["Invoice"]] = relationship(
        back_populates="booking",
        order_by="Invoice.id",
    )
    status_history: Mapped[list["BookingStatusHistory"]] = relationship(
        back_populates="booking",
        cascade="all, delete-orphan",
        order_by="BookingStatusHistory.changed_at",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Booking {self.booking_number} status={self.status}>"
