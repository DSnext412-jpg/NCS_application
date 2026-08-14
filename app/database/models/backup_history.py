"""Backup history model.

Records every backup attempt (manual, automatic and pre-restore safety
backups) so Admin can review date, file, size, location, verification
status and the metadata snapshot. This table is purely informational and
is NEVER required by the restore system — restoring reads only the
``.ncsbackup`` package file, so a corrupted or replaced main database can
always be recovered from a backup file even though this history is gone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class BackupHistory(Base):
    __tablename__ = "backup_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    backup_file: Mapped[str] = mapped_column(String(1000))
    file_name: Mapped[str] = mapped_column(String(300))
    location: Mapped[str] = mapped_column(String(1000), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # verified / failed
    status: Mapped[str] = mapped_column(String(20), default="verified", index=True)
    verification: Mapped[str] = mapped_column(String(500), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")
    reason: Mapped[str] = mapped_column(String(50), default="manual")
    error_message: Mapped[str] = mapped_column(String(1000), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<BackupHistory {self.file_name} status={self.status}>"
