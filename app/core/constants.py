"""Application-wide constants for Nashik Comfort Stay."""

from __future__ import annotations

from enum import Enum


# ---------------------------------------------------------------------------
# Application identity
# ---------------------------------------------------------------------------
APP_NAME = "Nashik Comfort Stay"
APP_TITLE = "Nashik Comfort Stay — Hotel Management System"
APP_VERSION = "1.0.0"
COMPANY_NAME = "Nashik Comfort Stay"

# Window defaults
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 760
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 620

# ---------------------------------------------------------------------------
# Hotel details (phase 1 confirmed data)
# ---------------------------------------------------------------------------
HOTEL_DESCRIPTION = (
    "Comfortable small luxury room hotel in Nashik, Pathardi Phata."
)
HOTEL_ADDRESS = (
    "Commercial 2nd Floor, Shivalik Sky Park, Pathardi Rd, beside Parksyde, "
    "Pandav Nagari, Indira Nagar, Nashik, Maharashtra 422009"
)
HOTEL_PHONE = "7888288655"
HOTEL_EMAIL = "shivalikcomfortstay@gmail.com"
HOTEL_WEBSITE = ""  # to be configured later from Admin Settings
GST_ENABLED = False
GSTIN = ""
DEFAULT_CURRENCY = "₹"

# Future invoice numbering pattern: NCS-INV-2026-000001
INVOICE_PREFIX = "NCS"


class RoomType(str, Enum):
    """Room categories. Value is persisted in the database as text."""

    AC = "AC"
    NON_AC = "Non-AC"

    @property
    def label(self) -> str:
        return self.value


class RoomStatus(str, Enum):
    """Room statuses used across the application.

    Values are persisted as lowercase text in the database.
    """

    VACANT = "vacant"
    OCCUPIED = "occupied"
    RESERVED = "reserved"
    CLEANING = "cleaning"

    @property
    def label(self) -> str:
        labels = {
            RoomStatus.VACANT: "Vacant",
            RoomStatus.OCCUPIED: "Occupied",
            RoomStatus.RESERVED: "Reserved",
            RoomStatus.CLEANING: "Cleaning",
        }
        return labels[self]

    @property
    def color(self) -> str:
        return ROOM_STATUS_COLORS[self]


ROOM_STATUS_COLORS: dict[RoomStatus, str] = {
    RoomStatus.VACANT: "#16a34a",
    RoomStatus.OCCUPIED: "#dc2626",
    RoomStatus.RESERVED: "#2563eb",
    RoomStatus.CLEANING: "#d97706",
}


class BookingStatus(str, Enum):
    """Booking lifecycle statuses.

    Deliberately separate from room statuses — e.g. a booking can be
    CHECKED_IN while the room is OCCUPIED.
    """

    NEW = "new"
    RESERVED = "reserved"
    CHECKED_IN = "checked-in"
    CHECKED_OUT = "checked-out"
    CANCELLED = "cancelled"
    NO_SHOW = "no-show"
    DELETED = "deleted"

    @property
    def label(self) -> str:
        labels = {
            BookingStatus.NEW: "New",
            BookingStatus.RESERVED: "Reserved",
            BookingStatus.CHECKED_IN: "Checked-in",
            BookingStatus.CHECKED_OUT: "Checked-out",
            BookingStatus.CANCELLED: "Cancelled",
            BookingStatus.NO_SHOW: "No-show",
            BookingStatus.DELETED: "Deleted",
        }
        return labels[self]


BOOKING_STATUS_COLORS: dict[BookingStatus, str] = {
    BookingStatus.NEW: "#64748b",
    BookingStatus.RESERVED: "#2563eb",
    BookingStatus.CHECKED_IN: "#dc2626",
    BookingStatus.CHECKED_OUT: "#16a34a",
    BookingStatus.CANCELLED: "#6b7280",
    BookingStatus.NO_SHOW: "#7c3aed",
    BookingStatus.DELETED: "#b91c1c",
}


# Configurable lists that Admin will manage in future phases.
DEFAULT_BOOKING_SOURCES = (
    "Agoda",
    "Booking.com",
    "FabHotels",
    "MakeMyTrip",
    "Goibibo",
    "Walk-in",
    "Direct Call",
    "Website",
    "Other",
)

# OTA sources whose bookings can be marked "Paid Online" (the guest already
# prepaid the OTA). Booking.com is deliberately excluded — its bookings are
# always collected at the hotel.
OTA_PAID_ONLINE_SOURCES = ("Agoda", "FabHotels", "MakeMyTrip", "Goibibo")

DEFAULT_PAYMENT_METHODS = ("Cash", "UPI", "QR", "Online", "Other")


class ChargeType(str, Enum):
    """Kinds of booking charges.

    ``ROOM``, ``EXTRA_PERSON``, ``EARLY_CHECK_IN`` and ``LATE_CHECK_OUT``
    are the base charges stored on the booking. ``EXTRA_MATTRESS``,
    ``MISCELLANEOUS`` and ``OTHER`` are the manual charges reception can
    add/remove from the charges table.
    """

    ROOM = "ROOM"
    EXTRA_PERSON = "EXTRA_PERSON"
    EARLY_CHECK_IN = "EARLY_CHECK_IN"
    LATE_CHECK_OUT = "LATE_CHECK_OUT"
    EXTRA_MATTRESS = "EXTRA_MATTRESS"
    MISCELLANEOUS = "MISCELLANEOUS"
    OTHER = "OTHER"

    @property
    def label(self) -> str:
        labels = {
            ChargeType.ROOM: "Room (manual)",
            ChargeType.EXTRA_PERSON: "Extra Person",
            ChargeType.EARLY_CHECK_IN: "Early Check-in",
            ChargeType.LATE_CHECK_OUT: "Late Check-out",
            ChargeType.EXTRA_MATTRESS: "Extra Mattress",
            ChargeType.MISCELLANEOUS: "Miscellaneous",
            ChargeType.OTHER: "Other",
        }
        return labels[self]


class PaymentMethod(str, Enum):
    """Accepted payment methods."""

    CASH = "cash"
    UPI = "upi"
    QR = "qr"
    ONLINE = "online"
    OTHER = "other"

    @property
    def label(self) -> str:
        labels = {
            PaymentMethod.CASH: "Cash",
            PaymentMethod.UPI: "UPI",
            PaymentMethod.QR: "QR",
            PaymentMethod.ONLINE: "Online",
            PaymentMethod.OTHER: "Other",
        }
        return labels[self]


class PaymentRecordStatus(str, Enum):
    """Lifecycle of an individual payment transaction.

    Payments are never deleted; a completed payment can be reversed for
    refunds, preserving an auditable history.
    """

    COMPLETED = "completed"
    REFUNDED = "refunded"
    REVERSED = "reversed"

    @property
    def label(self) -> str:
        labels = {
            PaymentRecordStatus.COMPLETED: "Completed",
            PaymentRecordStatus.REFUNDED: "Refunded",
            PaymentRecordStatus.REVERSED: "Reversed",
        }
        return labels[self]


class PaymentStatus(str, Enum):
    """Booking-level payment status derived from totals (never stored)."""

    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"

    @property
    def label(self) -> str:
        labels = {
            PaymentStatus.UNPAID: "Unpaid",
            PaymentStatus.PARTIAL: "Partial",
            PaymentStatus.PAID: "Paid",
        }
        return labels[self]


PAYMENT_STATUS_COLORS: dict[PaymentStatus, str] = {
    PaymentStatus.UNPAID: "#dc2626",
    PaymentStatus.PARTIAL: "#d97706",
    PaymentStatus.PAID: "#16a34a",
}


class InvoiceStatus(str, Enum):
    """Lifecycle of an invoice document.

    ``DRAFT`` is the provisional document before it becomes authoritative.
    ``FINALIZED`` invoices are immutable — they are never casually edited or
    deleted; corrections require a future reissue mechanism. ``CANCELLED``
    marks a draft (or, in a future phase, a corrected document) as void.
    """

    DRAFT = "draft"
    FINALIZED = "finalized"
    CANCELLED = "cancelled"

    @property
    def label(self) -> str:
        labels = {
            InvoiceStatus.DRAFT: "Draft",
            InvoiceStatus.FINALIZED: "Finalized",
            InvoiceStatus.CANCELLED: "Cancelled",
        }
        return labels[self]


INVOICE_STATUS_COLORS: dict[InvoiceStatus, str] = {
    InvoiceStatus.DRAFT: "#64748b",
    InvoiceStatus.FINALIZED: "#16a34a",
    InvoiceStatus.CANCELLED: "#dc2626",
}

# Guest identity document types (metadata only; no document files stored).
ID_TYPES = (
    "Aadhaar",
    "Passport",
    "Driving License",
    "Voter ID",
    "PAN",
    "Other",
)

# Guest address defaults (editable in the UI).
DEFAULT_COUNTRY = "India"
DEFAULT_STATE = "Maharashtra"
DEFAULT_CITY = "Nashik"

# Booking number format: NCS-B-<YEAR>-000001
BOOKING_NUMBER_PREFIX = "NCS-B"

# Statuses that occupy/reserve a room and therefore block availability.
ROOM_BLOCKING_BOOKING_STATUSES = (BookingStatus.RESERVED, BookingStatus.CHECKED_IN)

# Typical cancellation reasons (manual reason is also allowed).
CANCELLATION_REASONS = ("Guest request", "Plan changed", "Duplicate booking", "Other")
