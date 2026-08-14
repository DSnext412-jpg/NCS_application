"""Admin audit log service.

Records important Admin actions (login, logout, password changes, settings
changes, source management, logo changes, report generation) for later
troubleshooting and accountability. Passwords and authentication secrets are
never logged — only a timestamp, an action label and a description.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.database.models import AuditLog

logger = logging.getLogger(__name__)

# Action labels used consistently by the UI and tests.
ACTION_ADMIN_LOGIN = "admin_login"
ACTION_ADMIN_LOGOUT = "admin_logout"
ACTION_PASSWORD_CHANGED = "password_changed"
ACTION_SETTINGS_CHANGED = "settings_changed"
ACTION_SOURCE_ADDED = "booking_source_added"
ACTION_SOURCE_DISABLED = "booking_source_disabled"
ACTION_SOURCE_ENABLED = "booking_source_enabled"
ACTION_LOGO_CHANGED = "logo_changed"
ACTION_REPORT_GENERATED = "report_generated"
ACTION_BACKUP_CREATED = "backup_created"
ACTION_BACKUP_RESTORED = "backup_restored"
ACTION_BACKUP_SETTINGS_CHANGED = "backup_settings_changed"
ACTION_BACKUP_LOCATION_CHANGED = "backup_location_changed"
ACTION_BACKUP_AUTO_CHANGED = "backup_auto_changed"


def log_action(session: Session, action: str, description: str = "") -> AuditLog:
    """Append one audit entry and commit."""
    entry = AuditLog(action=action, description=(description or "").strip())
    session.add(entry)
    session.commit()
    logger.info("Audit: %s — %s", action, description or "")
    return entry


def get_audit_log(session: Session, limit: int = 500) -> list[AuditLog]:
    """Most recent audit entries first."""
    return (
        session.query(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .all()
    )


def clear_audit_log(session: Session) -> None:
    """Delete all audit entries (used by tests / Admin)."""
    session.query(AuditLog).delete()
    session.commit()
