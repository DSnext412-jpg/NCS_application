"""Room status change history.

Records every room status change so Admin reports can later answer
"what happened" questions. ``changed_by`` defaults to "Reception"
because staff login does not exist yet.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class RoomStatusHistory(Base):
    __tablename__ = "room_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(Integer, ForeignKey("rooms.id"), index=True)
    old_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    changed_by: Mapped[str] = mapped_column(String(100), default="Reception")
    note: Mapped[str] = mapped_column(String(500), default="")

    room: Mapped["Room"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RoomStatusHistory room={self.room_id} {self.old_status}->{self.new_status}>"
