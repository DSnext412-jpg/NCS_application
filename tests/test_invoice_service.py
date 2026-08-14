"""Tests for the Phase 5 invoice system: numbering, snapshots, financials,
statuses, PDF generation, workflow guards, search, filters and persistence.

All tests use temporary SQLite databases and temporary invoice directories
— the real hotel database and invoice folder are never touched.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime
from pathlib import Path

import pytest

from app.core.constants import (
    BookingStatus,
    ChargeType,
    InvoiceStatus,
    PaymentStatus,
)
from app.database.database import Database
from app.services import (
    booking_service,
    financial_service,
    guest_service,
    invoice_service,
    room_service,
)
from app.services.booking_source_service import initialize_default_sources
from app.services.invoice_service import (
    DuplicateFinalizedInvoiceError,
    InvoiceError,
    InvoiceStateError,
)
from app.services.money import to_decimal
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        room_service.initialize_default_rooms(session)
        initialize_default_sources(session)
        from app.services.settings_service import initialize_default_settings

        initialize_default_settings(session)


def _booking_fixture(
    database,
    *,
    rate=2000,
    nights=3,
    extra_person=0,
    early=0,
    late=0,
    mattress=0,
    misc=0,
    other=0,
    discount=0,
    payments=(),
    check_in=None,
):  # noqa: ANN001
    """Create + check-in + check-out a booking, adding charges/payments."""
    check_in = check_in or date.today()
    check_out = check_in + timedelta(days=nights)
    with database.session_scope() as session:
        guest = guest_service.create_guest(
            session,
            guest_name="Rahul Sharma",
            mobile_number="9876543210",
            city="Pune",
            address="Pune, Maharashtra",
        )
        guest_id = guest.id
        booking = booking_service.create_reservation(
            session,
            guest_id=guest.id,
            room_id=1,
            booking_source_id=1,
            check_in_date=check_in,
            check_in_time=dtime(14, 0),
            check_out_date=check_out,
            check_out_time=dtime(11, 0),
            room_rate=rate,
            extra_person_charge=extra_person,
            early_check_in_charge=early,
            late_check_out_charge=late,
        )
        booking_id = booking.id
        booking_service.check_in_booking(session, booking_id)
        booking_service.check_out_booking(session, booking_id)
        if mattress:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Extra Mattress",
                charge_type=ChargeType.EXTRA_MATTRESS,
                quantity=1,
                unit_amount=mattress,
            )
        if misc:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Miscellaneous",
                charge_type=ChargeType.MISCELLANEOUS,
                quantity=1,
                unit_amount=misc,
            )
        if other:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Other charge",
                charge_type=ChargeType.OTHER,
                quantity=1,
                unit_amount=other,
            )
        if discount:
            financial_service.set_discount(session, booking_id, discount)
        for amount, method, when, ref in payments:
            financial_service.record_payment(
                session,
                booking_id=booking_id,
                amount=amount,
                payment_method=method,
                payment_date=when,
                reference_number=ref,
            )
    return booking_id, guest_id


def _draft(database, booking_id):  # noqa: ANN001
    with database.session_scope() as session:
        return invoice_service.get_or_create_draft_invoice(session, booking_id)


def _finalize(database, invoice_id, invoice_dir):  # noqa: ANN001
    with database.session_scope() as session:
        return invoice_service.finalize_invoice(session, invoice_id, invoice_dir)


def _render(database, invoice):  # noqa: ANN001
    with database.session_scope() as session:
        fresh = invoice_service.get_invoice(session, invoice.id)
        return invoice_service.build_render_model(fresh)


# ---------------------------------------------------------------------------
# Invoice numbering
# ---------------------------------------------------------------------------

def test_first_invoice_number_uses_expected_format(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _guest_id = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        assert invoice.invoice_number == f"NCS-INV-{date.today().year}-000001"
        assert invoice.invoice_number.startswith("NCS-INV-")
    finally:
        database.dispose()


def test_invoice_numbers_are_unique_and_sequential(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        numbers = []
        for _ in range(2):
            booking_id, _ = _booking_fixture(database)
            invoice = _draft(database, booking_id)
            numbers.append(invoice.invoice_number)
        assert len(set(numbers)) == 2
        first = int(numbers[0].rsplit("-", 1)[1])
        second = int(numbers[1].rsplit("-", 1)[1])
        assert second == first + 1
    finally:
        database.dispose()


def test_invoice_numbering_survives_restart(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    _seed(database)
    booking_id, _ = _booking_fixture(database)
    with database.session_scope() as session:
        first = invoice_service.get_or_create_draft_invoice(session, booking_id)
    first_number = first.invoice_number
    database.dispose()

    reopened = Database(tmp_path / "hotel.db")
    reopened.create_all()
    try:
        booking_id2, _ = _booking_fixture(reopened)
        with reopened.session_scope() as session:
            second = invoice_service.get_or_create_draft_invoice(session, booking_id2)
        assert second.invoice_number != first_number
        seq1 = int(first_number.rsplit("-", 1)[1])
        seq2 = int(second.invoice_number.rsplit("-", 1)[1])
        assert seq2 == seq1 + 1
    finally:
        reopened.dispose()


def test_invoice_numbers_never_reuse_after_cancel(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            invoice_service.cancel_invoice(session, invoice.id, "Re-issue")
        booking_id2, _ = _booking_fixture(database)
        invoice2 = _draft(database, booking_id2)
        assert invoice2.invoice_number != invoice.invoice_number
        assert int(invoice2.invoice_number.rsplit("-", 1)[1]) == 2
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Invoice calculations
# ---------------------------------------------------------------------------

def test_room_charge_is_nights_times_rate(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=2000, nights=3)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        room_item = render["line_items"][0]
        assert room_item["description"] == "Room Stay - AC Room"
        assert room_item["quantity"] == "3"
        assert room_item["unit_amount"] == "₹2,000.00"
        assert room_item["amount"] == "₹6,000.00"
        assert render["subtotal"] == "₹6,000.00"
    finally:
        database.dispose()


def test_extra_charges_appear_as_line_items(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database, rate=2000, nights=3, extra_person=300, early=200, late=150, mattress=500
        )
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        descriptions = [item["description"] for item in render["line_items"]]
        assert "Extra Person" in descriptions
        assert "Early Check-in" in descriptions
        assert "Late Check-out" in descriptions
        assert "Extra Mattress" in descriptions
        assert render["subtotal"] == "₹7,150.00"  # 6000 + 300 + 200 + 150 + 500
    finally:
        database.dispose()


def test_discount_reduces_grand_total(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=2000, nights=3, discount=300)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["subtotal"] == "₹6,000.00"
        assert render["discount"] == "₹300.00"
        assert render["grand_total"] == "₹5,700.00"
    finally:
        database.dispose()


def test_zero_discount_is_hidden(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=2)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["discount"] is None
        assert render["grand_total"] == render["subtotal"]
    finally:
        database.dispose()


def test_gst_is_not_added(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=2000, nights=3)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["gst"] is None
        with database.session_scope() as session:
            snapshot = invoice_service.parse_snapshot(
                invoice_service.get_invoice(session, invoice.id).snapshot_json
            )
        assert to_decimal(snapshot["gst"]) == 0
        assert snapshot["gst_enabled"] is False
        assert render["grand_total"] == "₹6,000.00"
    finally:
        database.dispose()


def test_paid_remaining_and_payment_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database,
            rate=2000,
            nights=3,
            mattress=500,
            discount=300,
            payments=[(5000, "UPI", date.today(), "TXN1")],
        )
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["subtotal"] == "₹6,500.00"
        assert render["grand_total"] == "₹6,200.00"
        assert render["total_paid"] == "₹5,000.00"
        assert render["remaining"] == "₹1,200.00"
        assert render["payment_status"] == PaymentStatus.PARTIAL.value
        assert render["payment_status_label"] == "Partial"
    finally:
        database.dispose()


def test_full_payment_marks_invoice_paid(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database, rate=1000, nights=2, payments=[(2000, "CASH", date.today(), "")]
        )
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["total_paid"] == "₹2,000.00"
        assert render["remaining"] == "₹0.00"
        assert render["payment_status"] == PaymentStatus.PAID.value
    finally:
        database.dispose()


def test_multiple_payments_are_preserved(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database,
            rate=2000,
            nights=3,
            payments=[
                (2000, "CASH", date.today(), ""),
                (3000, "UPI", date.today(), "TXN123456789"),
            ],
        )
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert len(render["payments"]) == 2
        assert render["payments"][0]["method"] == "Cash"
        assert render["payments"][1]["method"] == "UPI"
        assert render["payments"][1]["reference"] == "TXN123456789"
        assert render["total_paid"] == "₹5,000.00"
    finally:
        database.dispose()


def test_line_items_reconcile_with_subtotal(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database, rate=2000, nights=3, extra_person=300, mattress=500, misc=120
        )
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            snapshot = invoice_service.parse_snapshot(
                invoice_service.get_invoice(session, invoice.id).snapshot_json
            )
        total = sum(to_decimal(item["amount"]) for item in snapshot["line_items"])
        assert total == to_decimal(snapshot["subtotal"])
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_guest_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["guest_name"] == "Rahul Sharma"
        assert render["guest_mobile"] == "9876543210"
        assert render["guest_address"] == "Pune, Maharashtra"
    finally:
        database.dispose()


def test_room_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["room_number"] == "202"
        assert render["room_type"] == "AC"
    finally:
        database.dispose()


def test_stay_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        check_in = date.today()
        booking_id, _ = _booking_fixture(database, check_in=check_in)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert render["check_in"].startswith(check_in.strftime("%d %b %Y"))
        assert render["check_out"].startswith((check_in + timedelta(days=3)).strftime("%d %b %Y"))
        assert render["nights"] == 3
        assert render["booking_source"] == "Agoda"
    finally:
        database.dispose()


def test_charges_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=2000, nights=3, mattress=500)
        invoice = _draft(database, booking_id)
        render = _render(database, invoice)
        assert len(render["line_items"]) == 2
        assert render["line_items"][1]["description"] == "Extra Mattress"
        assert render["line_items"][1]["amount"] == "₹500.00"
    finally:
        database.dispose()


def test_financial_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database, rate=2000, nights=3, mattress=500, discount=300,
            payments=[(5000, "UPI", date.today(), "")],
        )
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            fresh = invoice_service.get_invoice(session, invoice.id)
            snapshot = invoice_service.parse_snapshot(fresh.snapshot_json)
            assert to_decimal(snapshot["subtotal"]) == 6500
            assert to_decimal(snapshot["discount"]) == 300
            assert to_decimal(snapshot["grand_total"]) == 6200
            assert to_decimal(snapshot["total_paid"]) == 5000
            assert to_decimal(snapshot["remaining"]) == 1200
            assert snapshot["payment_status"] == PaymentStatus.PARTIAL.value
            assert fresh.subtotal == 6500
            assert fresh.discount == 300
            assert fresh.grand_total == 6200
            assert fresh.total_paid == 5000
            assert fresh.remaining_amount == 1200
            assert fresh.payment_status == PaymentStatus.PARTIAL.value
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Invoice status
# ---------------------------------------------------------------------------

def test_new_invoice_is_draft(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        assert invoice.status == InvoiceStatus.DRAFT.value
    finally:
        database.dispose()


def test_finalize_transitions_to_finalized(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        assert final.status == InvoiceStatus.FINALIZED.value
        assert Path(final.pdf_path).exists()
    finally:
        database.dispose()


def test_draft_can_be_cancelled(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            cancelled = invoice_service.cancel_invoice(session, invoice.id, "Wrong booking")
        assert cancelled.status == InvoiceStatus.CANCELLED.value
        assert cancelled.cancellation_reason == "Wrong booking"
    finally:
        database.dispose()


def test_finalized_invoice_cannot_be_cancelled(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with pytest.raises(InvoiceStateError):
            with database.session_scope() as session:
                invoice_service.cancel_invoice(session, final.id, "oops")
    finally:
        database.dispose()


def test_finalized_invoice_cannot_be_refreshed(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with pytest.raises(InvoiceStateError):
            with database.session_scope() as session:
                invoice_service.refresh_draft_snapshot(session, final.id)
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def test_pdf_is_generated_valid(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        pdf = Path(final.pdf_path)
        assert pdf.exists()
        assert pdf.stat().st_size > 100
        assert pdf.read_bytes().startswith(b"%PDF-")
    finally:
        database.dispose()


def test_pdf_filename_matches_invoice_number(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        assert Path(final.pdf_path).name == f"{final.invoice_number}.pdf"
    finally:
        database.dispose()


def test_pdf_stored_in_invoice_dir(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        assert Path(final.pdf_path) == tmp_path / "invoices" / f"{final.invoice_number}.pdf"
        assert (tmp_path / "invoices").is_dir()
    finally:
        database.dispose()


def test_missing_pdf_can_be_regenerated(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        pdf = Path(final.pdf_path)
        pdf.unlink()
        with database.session_scope() as session:
            path = invoice_service.regenerate_pdf(session, final.id, tmp_path / "invoices")
        assert Path(path).exists()
        assert Path(path).read_bytes().startswith(b"%PDF-")
    finally:
        database.dispose()


def test_existing_invoice_can_be_opened(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with database.session_scope() as session:
            opened = invoice_service.get_invoice_by_number(session, final.invoice_number)
            assert opened is not None
            assert opened.id == final.id
            render = invoice_service.build_render_model(opened)
            assert render["invoice_number"] == final.invoice_number
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Workflow guards
# ---------------------------------------------------------------------------

def test_checked_out_booking_can_generate_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        assert invoice.booking_id == booking_id
    finally:
        database.dispose()


def test_cancelled_booking_cannot_generate_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            guest = guest_service.create_guest(session, guest_name="A", mobile_number="1111111111")
            booking = booking_service.create_reservation(
                session, guest_id=guest.id, room_id=1, booking_source_id=1,
                check_in_date=date.today(), check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=1), check_out_time=dtime(11, 0),
                room_rate=1000,
            )
            booking_service.cancel_booking(session, booking.id, "Plan changed")
            booking_id = booking.id
        with pytest.raises(InvoiceStateError):
            _draft(database, booking_id)
    finally:
        database.dispose()


def test_no_show_booking_cannot_generate_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            guest = guest_service.create_guest(session, guest_name="A", mobile_number="2222222222")
            booking = booking_service.create_reservation(
                session, guest_id=guest.id, room_id=1, booking_source_id=1,
                check_in_date=date.today(), check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=1), check_out_time=dtime(11, 0),
                room_rate=1000,
            )
            booking_service.mark_no_show(session, booking.id, "Did not arrive")
            booking_id = booking.id
        with pytest.raises(InvoiceStateError):
            _draft(database, booking_id)
    finally:
        database.dispose()


def test_reserved_booking_cannot_generate_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with database.session_scope() as session:
            guest = guest_service.create_guest(session, guest_name="A", mobile_number="3333333333")
            booking = booking_service.create_reservation(
                session, guest_id=guest.id, room_id=1, booking_source_id=1,
                check_in_date=date.today(), check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=1), check_out_time=dtime(11, 0),
                room_rate=1000,
            )
            booking_id = booking.id
        with pytest.raises(InvoiceStateError):
            _draft(database, booking_id)
    finally:
        database.dispose()


def test_duplicate_finalized_invoice_prevented(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        _finalize(database, invoice.id, tmp_path / "invoices")
        with pytest.raises(DuplicateFinalizedInvoiceError) as exc_info:
            _draft(database, booking_id)
        assert exc_info.value.invoice.status == InvoiceStatus.FINALIZED.value
    finally:
        database.dispose()


def test_existing_draft_is_reused_not_duplicated(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        first = _draft(database, booking_id)
        second = _draft(database, booking_id)
        assert first.id == second.id
        assert first.invoice_number == second.invoice_number
    finally:
        database.dispose()


def test_checkout_helper_creates_draft_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        with database.session_scope() as session:
            invoices_before = invoice_service.get_invoices_for_booking(session, booking_id)
            assert invoices_before == []
            invoice = invoice_service.ensure_invoice_for_checkout(session, booking_id)
            assert invoice is not None
            assert invoice.status == InvoiceStatus.DRAFT.value
            assert invoice.booking_id == booking_id
            assert len(invoice_service.get_invoices_for_booking(session, booking_id)) == 1
    finally:
        database.dispose()


def test_checkout_helper_reuses_existing_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            again = invoice_service.ensure_invoice_for_checkout(session, booking_id)
            assert again.id == invoice.id
            assert len(invoice_service.get_invoices_for_booking(session, booking_id)) == 1
    finally:
        database.dispose()


def test_checkout_helper_returns_existing_finalized_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        _finalize(database, invoice.id, tmp_path / "invoices")
        with database.session_scope() as session:
            again = invoice_service.ensure_invoice_for_checkout(session, booking_id)
            assert again is not None
            assert again.id == invoice.id
            assert again.status == InvoiceStatus.FINALIZED.value
            assert len(invoice_service.get_invoices_for_booking(session, booking_id)) == 1
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Search / filters
# ---------------------------------------------------------------------------

def test_search_by_invoice_number(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            found = invoice_service.filter_invoices(session, query=invoice.invoice_number)
            assert any(i.id == invoice.id for i in found)
    finally:
        database.dispose()


def test_search_by_guest_name(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=1)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            found = invoice_service.filter_invoices(session, query="rahul")
            assert any(i.id == invoice.id for i in found)
            assert invoice_service.filter_invoices(session, query="zzzz") == []
    finally:
        database.dispose()


def test_search_by_mobile(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=1)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            found = invoice_service.filter_invoices(session, query="9876543210")
            assert any(i.id == invoice.id for i in found)
    finally:
        database.dispose()


def test_search_by_room(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=1)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            found = invoice_service.filter_invoices(session, query="202")
            assert any(i.id == invoice.id for i in found)
    finally:
        database.dispose()


def test_filter_by_payment_status_and_invoice_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(
            database, rate=1000, nights=2, payments=[(1000, "CASH", date.today(), "")]
        )
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            partial = invoice_service.filter_invoices(session, payment_status=PaymentStatus.PARTIAL)
            assert any(i.id == invoice.id for i in partial)
            paid = invoice_service.filter_invoices(session, payment_status=PaymentStatus.PAID)
            assert not any(i.id == invoice.id for i in paid)
            drafts = invoice_service.filter_invoices(session, invoice_status=InvoiceStatus.DRAFT)
            assert any(i.id == invoice.id for i in drafts)
            finalized = invoice_service.filter_invoices(session, invoice_status=InvoiceStatus.FINALIZED)
            assert not any(i.id == invoice.id for i in finalized)
    finally:
        database.dispose()


def test_filter_by_date_periods(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=1)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            assert any(
                i.id == invoice.id
                for i in invoice_service.filter_invoices(session, period="today")
            )
            assert any(
                i.id == invoice.id
                for i in invoice_service.filter_invoices(session, period="week")
            )
            assert any(
                i.id == invoice.id
                for i in invoice_service.filter_invoices(session, period="month")
            )
            assert any(
                i.id == invoice.id
                for i in invoice_service.filter_invoices(
                    session, period="custom",
                    date_from=date.today() - timedelta(days=1),
                    date_to=date.today() + timedelta(days=1),
                )
            )
            assert not any(
                i.id == invoice.id
                for i in invoice_service.filter_invoices(
                    session, period="custom",
                    date_from=date.today() + timedelta(days=10),
                    date_to=date.today() + timedelta(days=20),
                )
            )
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_invoice_remains_after_restart(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    _seed(database)
    booking_id, _ = _booking_fixture(database)
    invoice = _draft(database, booking_id)
    final = _finalize(database, invoice.id, tmp_path / "invoices")
    number = final.invoice_number
    database.dispose()

    reopened = Database(tmp_path / "hotel.db")
    reopened.create_all()
    try:
        with reopened.session_scope() as session:
            loaded = invoice_service.get_invoice_by_number(session, number)
            assert loaded is not None
            assert loaded.status == InvoiceStatus.FINALIZED.value
            assert Path(loaded.pdf_path).exists()
    finally:
        reopened.dispose()


def test_snapshot_unchanged_after_guest_edit(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, guest_id = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with database.session_scope() as session:
            guest_service.update_guest(
                session, guest_id,
                guest_name="Someone Else",
                mobile_number="9999999999",
                city="Mumbai",
            )
        with database.session_scope() as session:
            render = invoice_service.build_render_model(
                invoice_service.get_invoice_by_number(session, final.invoice_number)
            )
        assert render["guest_name"] == "Rahul Sharma"
        assert render["guest_mobile"] == "9876543210"
        assert render["guest_address"] == "Pune, Maharashtra"
    finally:
        database.dispose()


def test_snapshot_unchanged_after_booking_edit(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=2000, nights=3, mattress=500)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with database.session_scope() as session:
            booking_service.update_booking(
                session, booking_id, room_rate=9999, extra_person_charge=777
            )
        with database.session_scope() as session:
            render = invoice_service.build_render_model(
                invoice_service.get_invoice_by_number(session, final.invoice_number)
            )
        assert render["subtotal"] == "₹6,500.00"
        assert render["line_items"][0]["unit_amount"] == "₹2,000.00"
        assert render["line_items"][0]["amount"] == "₹6,000.00"
    finally:
        database.dispose()


def test_regenerated_pdf_uses_frozen_snapshot(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, guest_id = _booking_fixture(database, rate=2000, nights=3)
        invoice = _draft(database, booking_id)
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        pdf_path = Path(final.pdf_path)
        pdf_path.unlink()
        with database.session_scope() as session:
            guest_service.update_guest(session, guest_id, guest_name="Edited Guest")
        with database.session_scope() as session:
            regenerated = invoice_service.regenerate_pdf(session, final.id, tmp_path / "invoices")
        assert Path(regenerated).exists()
        with database.session_scope() as session:
            render = invoice_service.build_render_model(
                invoice_service.get_invoice_by_number(session, final.invoice_number)
            )
        assert render["guest_name"] == "Rahul Sharma"
        assert render["invoice_number"] == final.invoice_number
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def test_cancelled_draft_does_not_block_new_invoice(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database)
        invoice = _draft(database, booking_id)
        with database.session_scope() as session:
            invoice_service.cancel_invoice(session, invoice.id, "Typo")
        invoice2 = _draft(database, booking_id)
        assert invoice2.status == InvoiceStatus.DRAFT.value
        assert invoice2.invoice_number != invoice.invoice_number
    finally:
        database.dispose()


def test_missing_booking_raises_invoice_error(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with pytest.raises(InvoiceError):
            with database.session_scope() as session:
                invoice_service.create_draft_invoice(session, 99999)
    finally:
        database.dispose()


def test_finalize_refreshes_snapshot_with_latest_payments(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id, _ = _booking_fixture(database, rate=1000, nights=2)
        invoice = _draft(database, booking_id)
        # A payment is recorded after the draft is created.
        with database.session_scope() as session:
            financial_service.record_payment(
                session, booking_id=booking_id, amount=1500,
                payment_method="UPI", reference_number="AFTER",
            )
        final = _finalize(database, invoice.id, tmp_path / "invoices")
        with database.session_scope() as session:
            render = invoice_service.build_render_model(
                invoice_service.get_invoice_by_number(session, final.invoice_number)
            )
        assert render["total_paid"] == "₹1,500.00"
        assert render["remaining"] == "₹500.00"
        assert render["payment_status"] == PaymentStatus.PARTIAL.value
    finally:
        database.dispose()
