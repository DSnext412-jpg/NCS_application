"""Report building service.

Builds structured report data (titles, summary rows and tables) for the
Admin Reports page. The report model is presentation-agnostic: the same
``ReportData`` is rendered by the on-screen tables, CSV, Excel and PDF
exporters in :mod:`app.services.report_export`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.config import KEY_HOTEL_ADDRESS, KEY_HOTEL_DESCRIPTION, KEY_HOTEL_EMAIL, KEY_HOTEL_NAME, KEY_HOTEL_PHONE
from app.services import analytics_service
from app.services.money import to_decimal
from app.services.settings_service import get_settings
from app.ui.formatters import format_date, format_money


@dataclass
class ReportTable:
    """A single table inside a report."""

    name: str
    headers: list[str]
    rows: list[list[str]]


@dataclass
class ReportData:
    """Presentation-agnostic report ready for any exporter."""

    report_type: str
    title: str
    date_from: date
    date_to: date
    generated_at: datetime
    hotel_name: str
    summary: list[tuple[str, str]] = field(default_factory=list)
    tables: list[ReportTable] = field(default_factory=list)


def report_filename(report_type: str, date_from: date, date_to: date, ext: str) -> str:
    """Deterministic, date-prefixed file name for a report export."""
    return f"{report_type}_{date_from:%Y-%m-%d}_{date_to:%Y-%m-%d}.{ext}"


def _base(session: Session, report_type: str, title: str, date_from: date, date_to: date) -> ReportData:
    settings = get_settings(session)
    return ReportData(
        report_type=report_type,
        title=title,
        date_from=date_from,
        date_to=date_to,
        generated_at=datetime.now(),
        hotel_name=settings.get(KEY_HOTEL_NAME, ""),
    )


def build_financial_report(session: Session, date_from: date, date_to: date) -> ReportData:
    """Collected revenue, outstanding and payment breakdown for the range."""
    date_from, date_to = analytics_service._normalize_range(date_from, date_to)  # noqa: SLF001
    overview = analytics_service.get_payment_overview(session, date_from, date_to)
    methods = analytics_service.get_revenue_by_method(session, date_from, date_to)
    daily = analytics_service.get_revenue_by_day(session, date_from, date_to)
    transactions = analytics_service.get_payment_transactions(session, date_from, date_to)

    report = _base(session, "financial", "Financial Summary", date_from, date_to)
    report.summary = [
        ("Period", f"{format_date(date_from)}  to  {format_date(date_to)}"),
        ("Collected (Completed Payments)", format_money(overview["collected"])),
        ("Outstanding", format_money(overview["outstanding"])),
        ("Bookings Fully Paid", str(overview["paid"])),
        ("Bookings Partially Paid", str(overview["partial"])),
        ("Bookings Unpaid", str(overview["unpaid"])),
    ]
    report.tables = [
        ReportTable(
            "Payment Methods",
            ["Payment Method", "Amount"],
            [[method.capitalize(), format_money(total)] for method, total in sorted(methods.items())],
        ),
        ReportTable(
            "Daily Revenue",
            ["Date", "Amount"],
            [[format_date(day), format_money(total)] for day, total in daily],
        ),
        ReportTable(
            "Payment Transactions",
            ["Date", "Booking No.", "Guest", "Payment Method", "Amount"],
            [
                [
                    format_date(transaction["payment_date"]),
                    transaction["booking_number"],
                    transaction["guest_name"],
                    transaction["payment_method"].capitalize(),
                    format_money(transaction["amount"]),
                ]
                for transaction in transactions
            ],
        ),
    ]
    return report


def build_source_report(session: Session, date_from: date, date_to: date) -> ReportData:
    """Booking counts and collected revenue by booking source."""
    date_from, date_to = analytics_service._normalize_range(date_from, date_to)  # noqa: SLF001
    counts = analytics_service.get_booking_counts_by_source(session, date_from, date_to)
    revenue = analytics_service.get_revenue_by_source(session, date_from, date_to)
    sources = sorted(set(counts) | set(revenue))

    report = _base(session, "sources", "Booking Sources Report", date_from, date_to)
    report.summary = [
        ("Period", f"{format_date(date_from)}  to  {format_date(date_to)}"),
        ("Total Bookings", str(sum(counts.values()))),
        ("Total Revenue (Completed Payments)", format_money(sum((revenue.get(s, to_decimal(0)) for s in sources), to_decimal(0)))),
    ]
    report.tables = [
        ReportTable(
            "By Source",
            ["Booking Source", "Bookings", "Revenue"],
            [
                [source, str(counts.get(source, 0)), format_money(revenue.get(source, to_decimal(0)))]
                for source in sources
            ],
        )
    ]
    return report


def build_occupancy_report(session: Session, date_from: date, date_to: date) -> ReportData:
    """Room-night occupancy plus per room-type and per-room breakdowns."""
    date_from, date_to = analytics_service._normalize_range(date_from, date_to)  # noqa: SLF001
    occupancy = analytics_service.get_occupancy(session, date_from, date_to)
    by_type = analytics_service.get_room_type_report(session, date_from, date_to)
    by_room = analytics_service.get_room_performance(session, date_from, date_to)

    report = _base(session, "occupancy", "Occupancy Report", date_from, date_to)
    report.summary = [
        ("Period", f"{format_date(date_from)}  to  {format_date(date_to)}"),
        ("Active Rooms", str(occupancy["total_rooms"])),
        ("Available Room Nights", str(occupancy["available_nights"])),
        ("Occupied Room Nights", str(occupancy["occupied_nights"])),
        ("Occupancy Rate", f"{occupancy['occupancy_percent']}%"),
    ]
    report.tables = [
        ReportTable(
            "By Room Type",
            ["Room Type", "Rooms", "Total Room Nights", "Occupied Room Nights", "Occupancy %"],
            [
                [
                    row["room_type"],
                    str(row["rooms"]),
                    str(row["total_room_nights"]),
                    str(row["occupied_room_nights"]),
                    f"{row['occupancy_percent']}%",
                ]
                for row in by_type
            ],
        ),
        ReportTable(
            "Room Performance",
            ["Room", "Type", "Bookings", "Revenue", "Occupied Nights"],
            [
                [
                    row["room_number"],
                    row["room_type"],
                    str(row["bookings"]),
                    format_money(row["revenue"]),
                    str(row["occupied_nights"]),
                ]
                for row in by_room
            ],
        ),
    ]
    return report


def build_booking_trend_report(session: Session, date_from: date, date_to: date) -> ReportData:
    """Per-day reservations, check-ins and check-outs."""
    date_from, date_to = analytics_service._normalize_range(date_from, date_to)  # noqa: SLF001
    trend = analytics_service.get_booking_trend(session, date_from, date_to)

    report = _base(session, "booking_trend", "Booking Trend Report", date_from, date_to)
    report.summary = [
        ("Period", f"{format_date(date_from)}  to  {format_date(date_to)}"),
        (
            "Total",
            (
                f"{sum(t['reservations'] for t in trend)} reservations, "
                f"{sum(t['check_ins'] for t in trend)} check-ins, "
                f"{sum(t['check_outs'] for t in trend)} check-outs"
            ),
        ),
    ]
    report.tables = [
        ReportTable(
            "Daily Bookings",
            ["Date", "Reservations", "Check-ins", "Check-outs"],
            [
                [
                    format_date(row["date"]),
                    str(row["reservations"]),
                    str(row["check_ins"]),
                    str(row["check_outs"]),
                ]
                for row in trend
            ],
        )
    ]
    return report


_BUILDERS = {
    "financial": build_financial_report,
    "sources": build_source_report,
    "occupancy": build_occupancy_report,
    "booking_trend": build_booking_trend_report,
}


def build_report(session: Session, report_type: str, date_from: date, date_to: date) -> ReportData:
    """Build any registered report type by key."""
    builder = _BUILDERS.get(report_type)
    if builder is None:
        raise ValueError(f"Unknown report type: {report_type!r}")
    return builder(session, date_from, date_to)


def build_all_reports(session: Session, date_from: date, date_to: date) -> list[ReportData]:
    """All registered reports for a given range (used by bulk export)."""
    date_from, date_to = analytics_service._normalize_range(date_from, date_to)  # noqa: SLF001
    return [builder(session, date_from, date_to) for builder in _BUILDERS.values()]


def report_hotel_header(session: Session) -> dict[str, str]:
    """Hotel details for export file headers."""
    settings = get_settings(session)
    return {
        "hotel_name": settings.get(KEY_HOTEL_NAME, ""),
        "hotel_description": settings.get(KEY_HOTEL_DESCRIPTION, ""),
        "hotel_address": settings.get(KEY_HOTEL_ADDRESS, ""),
        "hotel_phone": settings.get(KEY_HOTEL_PHONE, ""),
        "hotel_email": settings.get(KEY_HOTEL_EMAIL, ""),
    }
