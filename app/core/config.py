"""Static configuration values and default seed data.

These defaults are copied into the SQLite database on first run so they
can later be changed from the Admin Settings screen without editing code.
"""

from __future__ import annotations

from typing import Any

from app.core.constants import (
    APP_NAME,
    GSTIN,
    GST_ENABLED,
    HOTEL_ADDRESS,
    HOTEL_DESCRIPTION,
    HOTEL_EMAIL,
    HOTEL_PHONE,
    HOTEL_WEBSITE,
    INVOICE_PREFIX,
    RoomType,
)

# Setting keys
KEY_HOTEL_NAME = "hotel_name"
KEY_HOTEL_DESCRIPTION = "hotel_description"
KEY_HOTEL_ADDRESS = "hotel_address"
KEY_HOTEL_PHONE = "hotel_phone"
KEY_HOTEL_EMAIL = "hotel_email"
KEY_HOTEL_WEBSITE = "hotel_website"
KEY_GST_ENABLED = "gst_enabled"
KEY_GSTIN = "gstin"
KEY_LOGO_PATH = "logo_path"
KEY_INVOICE_PREFIX = "invoice_prefix"
KEY_INVOICE_FOOTER = "invoice_footer_message"
KEY_INVOICE_TERMS = "invoice_terms"
KEY_LATE_CHECKOUT_CHARGE = "late_checkout_charge"
KEY_LATE_CHECKOUT_GRACE_HOURS = "late_checkout_grace_hours"

DEFAULT_LATE_CHECKOUT_CHARGE = "300"
DEFAULT_LATE_CHECKOUT_GRACE_HOURS = "4"

# Admin security / settings keys. The admin password is stored ONLY as a
# salted hash (see app.services.security_service); it is never plain text.
KEY_ADMIN_PASSWORD_HASH = "admin_password_hash"
KEY_ADMIN_PASSWORD_SET = "admin_password_set"
KEY_ADMIN_SESSION_TIMEOUT_MINUTES = "admin_session_timeout_minutes"
KEY_ADMIN_FAILED_ATTEMPTS = "admin_failed_attempts"
KEY_ADMIN_LOCKED_UNTIL = "admin_locked_until"

# Backup / data-safety settings (Phase 8). The backup location defaults to
# the user's Documents folder and is overridable by Admin; it is never the
# application installation directory.
KEY_BACKUP_LOCATION = "backup_location"
KEY_BACKUP_AUTO_ENABLED = "backup_auto_enabled"
KEY_BACKUP_FREQUENCY = "backup_frequency"          # daily / weekly
KEY_BACKUP_TIME = "backup_time"                    # "HH:MM"
KEY_BACKUP_RETENTION = "backup_retention_count"    # newest N backups kept
KEY_BACKUP_LAST_SUCCESS = "backup_last_success_at"  # ISO timestamp

DEFAULT_BACKUP_LOCATION = ""
DEFAULT_BACKUP_AUTO_ENABLED = "true"
DEFAULT_BACKUP_FREQUENCY = "daily"
DEFAULT_BACKUP_TIME = "21:30"
DEFAULT_BACKUP_RETENTION = "30"

DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES = 15
ADMIN_MAX_FAILED_ATTEMPTS = 5
ADMIN_LOCKOUT_SECONDS = 30

# GST is currently disabled for this property. It must only be enabled
# explicitly from Admin Settings in a future phase.
DEFAULT_HOTEL_SETTINGS: dict[str, str] = {
    KEY_HOTEL_NAME: APP_NAME,
    KEY_HOTEL_DESCRIPTION: HOTEL_DESCRIPTION,
    KEY_HOTEL_ADDRESS: HOTEL_ADDRESS,
    KEY_HOTEL_PHONE: HOTEL_PHONE,
    KEY_HOTEL_EMAIL: HOTEL_EMAIL,
    KEY_HOTEL_WEBSITE: HOTEL_WEBSITE,
    KEY_GST_ENABLED: str(GST_ENABLED).lower(),
    KEY_GSTIN: GSTIN,
    KEY_LOGO_PATH: "",
    KEY_INVOICE_PREFIX: INVOICE_PREFIX,
    KEY_INVOICE_FOOTER: "Thank you for staying with us!",
    KEY_INVOICE_TERMS: "",
    KEY_LATE_CHECKOUT_CHARGE: DEFAULT_LATE_CHECKOUT_CHARGE,
    KEY_LATE_CHECKOUT_GRACE_HOURS: DEFAULT_LATE_CHECKOUT_GRACE_HOURS,
    KEY_ADMIN_PASSWORD_SET: "false",
    KEY_ADMIN_SESSION_TIMEOUT_MINUTES: str(DEFAULT_ADMIN_SESSION_TIMEOUT_MINUTES),
    KEY_ADMIN_FAILED_ATTEMPTS: "0",
    # Phase 8 backup defaults (backup_location is resolved at runtime).
    KEY_BACKUP_LOCATION: DEFAULT_BACKUP_LOCATION,
    KEY_BACKUP_AUTO_ENABLED: DEFAULT_BACKUP_AUTO_ENABLED,
    KEY_BACKUP_FREQUENCY: DEFAULT_BACKUP_FREQUENCY,
    KEY_BACKUP_TIME: DEFAULT_BACKUP_TIME,
    KEY_BACKUP_RETENTION: DEFAULT_BACKUP_RETENTION,
    KEY_BACKUP_LAST_SUCCESS: "",
}

# The 11 standard rooms. Pricing is intentionally NOT part of room
# configuration -- room rates and extra-person charges are entered
# manually by reception staff at booking time (future phase).
#
# A 12th guest/property room exists but is intentionally not defined
# here; its number, type and details are configurable later by Admin.
DEFAULT_ROOMS: list[dict[str, Any]] = [
    {"room_number": "202", "room_type": RoomType.AC.value},
    {"room_number": "203", "room_type": RoomType.AC.value},
    {"room_number": "204", "room_type": RoomType.AC.value},
    {"room_number": "205", "room_type": RoomType.AC.value},
    {"room_number": "206", "room_type": RoomType.AC.value},
    {"room_number": "207", "room_type": RoomType.AC.value},
    {"room_number": "208", "room_type": RoomType.NON_AC.value},
    {"room_number": "209", "room_type": RoomType.NON_AC.value},
    {"room_number": "210", "room_type": RoomType.NON_AC.value},
    {"room_number": "211", "room_type": RoomType.NON_AC.value},
    {"room_number": "212", "room_type": RoomType.NON_AC.value},
]
