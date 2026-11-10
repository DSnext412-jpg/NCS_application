from __future__ import annotations

from enum import Enum

APP_NAME = "Nashik Comfort Stay"
APP_TITLE = "Nashik Comfort Stay — Hotel Management System"
APP_VERSION = "1.0.0"
COMPANY_NAME = "Nashik Comfort Stay"
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 760
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 620

HOTEL_DESCRIPTION = (
    "Comfortable small luxury room hotel in Nashik, Pathardi Phata."
)
HOTEL_ADDRESS = (
    "Commercial 2nd Floor, Shivalik Sky Park, Pathardi Rd, beside Parksyde, "
    "Pandav Nagari, Indira Nagar, Nashik, Maharashtra 422009"
)
HOTEL_PHONE = "7888288655"
HOTEL_EMAIL = "shivalikcomfortstay@gmail.com"
HOTEL_WEBSITE = "" 
GST_ENABLED = False
GSTIN = ""
DEFAULT_CURRENCY = "₹"

INVOICE_PREFIX = "NCS"


class RoomType(str, Enum):
    AC = "AC"
    NON_AC = "Non-AC"

    @property
    def label(self) -> str:
        return self.value


class RoomStatus(str, Enum):
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

OTA_PAID_ONLINE_SOURCES = ("Agoda", "FabHotels", "MakeMyTrip", "Goibibo")

DEFAULT_PAYMENT_METHODS = ("Cash", "UPI", "QR", "Online", "Other")


class ChargeType(str, Enum):
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

ID_TYPES = (
    "Aadhaar",
    "Passport",
    "Driving License",
    "Voter ID",
    "PAN",
    "Other",
)

DEFAULT_COUNTRY = "India"
DEFAULT_STATE = "Maharashtra"
DEFAULT_CITY = "Nashik"

BOOKING_NUMBER_PREFIX = "NCS-B"

ROOM_BLOCKING_BOOKING_STATUSES = (BookingStatus.RESERVED, BookingStatus.CHECKED_IN)

# Typical cancellation reasons (manual reason is also allowed).
CANCELLATION_REASONS = ("Guest request", "Plan changed", "Duplicate booking", "Other")
