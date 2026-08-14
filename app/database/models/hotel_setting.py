"""Hotel settings key/value storage.

Stored as generic string values so new settings can be added without
schema changes. Booleans and numbers are converted on read.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class HotelSetting(Base):
    __tablename__ = "hotel_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    value: Mapped[str] = mapped_column(String(2000), default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<HotelSetting key={self.key!r} value={self.value!r}>"
