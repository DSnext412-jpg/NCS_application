"""Model registry.

Importing this package registers every model with
:attr:`app.database.base.Base.metadata`.
"""

from __future__ import annotations

from app.database.models.audit_log import AuditLog
from app.database.models.backup_history import BackupHistory
from app.database.models.booking import Booking
from app.database.models.booking_charge import BookingCharge
from app.database.models.booking_status_history import BookingStatusHistory
from app.database.models.booking_source import BookingSource
from app.database.models.guest import Guest
from app.database.models.hotel_setting import HotelSetting
from app.database.models.invoice import Invoice
from app.database.models.payment import Payment
from app.database.models.room import Room
from app.database.models.room_status_history import RoomStatusHistory

__all__ = [
    "AuditLog",
    "BackupHistory",
    "Booking",
    "BookingCharge",
    "BookingStatusHistory",
    "BookingSource",
    "Guest",
    "HotelSetting",
    "Invoice",
    "Payment",
    "Room",
    "RoomStatusHistory",
]
