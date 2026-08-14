"""Audit log model.

Records important Admin actions (login, logout, password changes, settings
changes, source management, logo changes, report generation) for later
troubleshooting and accountability. Passwords and authentication secrets are
never stored here — only a timestamp, an action label and a description.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(String(1000), default="")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<AuditLog {self.action!r} @ {self.created_at}>"
