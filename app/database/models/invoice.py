"""Invoice model.

An invoice is a financial document produced from a booking at checkout.
Once it is ``FINALIZED`` it becomes authoritative and immutable: all the
information needed to reprint it (guest, room, stay, line items and money
figures) is frozen into ``snapshot_json`` so later edits to the guest or
booking never silently change an issued invoice.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_number: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    booking_id: Mapped[int] = mapped_column(Integer, ForeignKey("bookings.id"), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)

    # Denormalized financial figures (authoritative once finalized).
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    grand_total: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_paid: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    remaining_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    payment_status: Mapped[str] = mapped_column(String(20), default="unpaid")

    # draft / finalized / cancelled
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    notes: Mapped[str] = mapped_column(String(1000), default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_reason: Mapped[str] = mapped_column(String(500), default="")

    # Frozen copy of everything printed on the invoice (see invoice service).
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    pdf_path: Mapped[str] = mapped_column(String(500), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    booking: Mapped["Booking"] = relationship(back_populates="invoices")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Invoice {self.invoice_number} status={self.status}>"
