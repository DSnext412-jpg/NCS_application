"""Tests for the financial service: charges, discounts, payments, reversals
and today's collected total.

All tests use temporary SQLite databases — the real hotel database is
never touched.
"""

from __future__ import annotations

from datetime import date, timedelta, time as dtime

import pytest

from app.core.constants import (
    ChargeType,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
)
from app.database.database import Database
from app.database.models import BookingCharge, Payment
from app.services import booking_service, financial_service, guest_service, room_service
from app.services.booking_source_service import initialize_default_sources
from app.services.financial_service import (
    ChargeValidationError,
    FinancialError,
    OverPaymentError,
    PaymentValidationError,
)
from tests._db_support import copy_db_template


def _make_database(tmp_path):  # noqa: ANN001
    database = Database(copy_db_template(tmp_path / "hotel.db"))
    return database


def _seed(database) -> None:  # noqa: ANN001
    with database.session_scope() as session:
        room_service.initialize_default_rooms(session)
        initialize_default_sources(session)


def _add_guest(database, name="Amit Sharma", mobile="9876543210") -> int:  # noqa: ANN001
    with database.session_scope() as session:
        guest = guest_service.create_guest(
            session,
            guest_name=name,
            mobile_number=mobile,
            city="Jaipur",
            id_type="Aadhaar",
            id_number="123456789012",
            address="Test Address",
        )
        return guest.id


def _reserve(database, guest_id, room_id, *, rate=1000.0) -> int:  # noqa: ANN001
    with database.session_scope() as session:
        booking = booking_service.create_reservation(
            session,
            guest_id=guest_id,
            room_id=room_id,
            booking_source_id=1,
            check_in_date=date.today(),
            check_in_time=dtime(12, 0),
            check_out_date=date.today() + timedelta(days=2),
            check_out_time=dtime(11, 0),
            adults=1,
            children=0,
            room_rate=rate,
        )
        return booking.id


def _summary(database, booking_id):  # noqa: ANN001
    with database.session_scope() as session:
        return financial_service.get_financial_summary(session, booking_id)


def _pay(database, booking_id, amount, method="CASH", when=None):  # noqa: ANN001
    with database.session_scope() as session:
        return financial_service.record_payment(
            session,
            booking_id=booking_id,
            amount=amount,
            payment_method=method,
            payment_date=when,
        )


# ---------------------------------------------------------------------------
# Derived charges
# ---------------------------------------------------------------------------

def test_calculate_nights(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        assert financial_service.calculate_nights(date(2026, 8, 10), date(2026, 8, 12)) == 2
        assert financial_service.calculate_nights(date(2026, 8, 10), date(2026, 8, 10)) == 0
    finally:
        database.dispose()


def test_summary_derives_room_charge_from_rate_and_nights(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1200)
        summary = _summary(database, booking_id)
        assert summary.nights == 2
        assert summary.room_charges == 2400
        assert summary.extra_person_charges == 0
        assert summary.subtotal == 2400
        assert summary.grand_total == 2400
        assert summary.gst == 0
        assert summary.payment_status == PaymentStatus.UNPAID
    finally:
        database.dispose()


def test_summary_counts_extra_person_early_and_late_charges(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        guest_id = _add_guest(database)
        with database.session_scope() as session:
            booking = booking_service.create_reservation(
                session,
                guest_id=guest_id,
                room_id=1,
                booking_source_id=1,
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=2),
                check_out_time=dtime(11, 0),
                room_rate=1000,
                extra_person_charge=300,
                early_check_in_charge=200,
                late_check_out_charge=150,
            )
            booking_id = booking.id
        summary = _summary(database, booking_id)
        assert summary.room_charges == 2000
        assert summary.extra_person_charges == 300
        assert summary.early_check_in_charges == 200
        assert summary.late_check_out_charges == 150
        assert summary.subtotal == 2650
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Manual charges
# ---------------------------------------------------------------------------

def test_add_charge_increases_subtotal(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with database.session_scope() as session:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Extra mattress",
                charge_type=ChargeType.EXTRA_MATTRESS,
                quantity=1,
                unit_amount=200,
            )
        summary = _summary(database, booking_id)
        assert summary.mattress_charges == 200
        assert summary.subtotal == 2200
    finally:
        database.dispose()


def test_add_charge_with_quantity_multiplies_total(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with database.session_scope() as session:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Misc",
                charge_type=ChargeType.MISCELLANEOUS,
                quantity=3,
                unit_amount=50,
            )
        summary = _summary(database, booking_id)
        assert summary.miscellaneous_charges == 150
    finally:
        database.dispose()


def test_add_charge_requires_description_and_positive_quantity(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1)
        with database.session_scope() as session:
            with pytest.raises(ChargeValidationError):
                financial_service.add_charge(
                    session,
                    booking_id=booking_id,
                    description="   ",
                    charge_type=ChargeType.OTHER,
                    quantity=1,
                    unit_amount=10,
                )
            with pytest.raises(ChargeValidationError):
                financial_service.add_charge(
                    session,
                    booking_id=booking_id,
                    description="Test",
                    charge_type=ChargeType.OTHER,
                    quantity=0,
                    unit_amount=10,
                )
            with pytest.raises(ChargeValidationError):
                financial_service.add_charge(
                    session,
                    booking_id=booking_id,
                    description="Test",
                    charge_type=ChargeType.OTHER,
                    quantity=1,
                    unit_amount=-5,
                )
    finally:
        database.dispose()


def test_remove_charge_reverts_subtotal(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with database.session_scope() as session:
            charge = financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Misc",
                charge_type=ChargeType.MISCELLANEOUS,
                unit_amount=100,
            )
            charge_id = charge.id
        assert _summary(database, booking_id).subtotal == 2100
        with database.session_scope() as session:
            financial_service.remove_charge(session, charge_id)
        assert _summary(database, booking_id).subtotal == 2000
    finally:
        database.dispose()


def test_manual_room_charge_counts_towards_room_total(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        # Same-day stay: derived room charge is 0, confirmed manually.
        guest_id = _add_guest(database)
        with database.session_scope() as session:
            booking = booking_service.create_reservation(
                session,
                guest_id=guest_id,
                room_id=1,
                booking_source_id=1,
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today(),
                check_out_time=dtime(18, 0),
                room_rate=1000,
            )
            booking_id = booking.id
        assert _summary(database, booking_id).room_charges == 0
        with database.session_scope() as session:
            financial_service.add_charge(
                session,
                booking_id=booking_id,
                description="Same-day room charge",
                charge_type=ChargeType.ROOM,
                unit_amount=500,
            )
        assert _summary(database, booking_id).room_charges == 500
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Discount
# ---------------------------------------------------------------------------

def test_set_discount_reduces_grand_total(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with database.session_scope() as session:
            financial_service.set_discount(session, booking_id, 200)
        summary = _summary(database, booking_id)
        assert summary.discount == 200
        assert summary.subtotal == 2000
        assert summary.grand_total == 1800
    finally:
        database.dispose()


def test_discount_cannot_exceed_subtotal_or_be_negative(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with database.session_scope() as session:
            with pytest.raises(ChargeValidationError):
                financial_service.set_discount(session, booking_id, 5000)
            with pytest.raises(ChargeValidationError):
                financial_service.set_discount(session, booking_id, -10)
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

def test_record_payment_updates_paid_and_status(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 1500, method="UPI", when=date.today())
        summary = _summary(database, booking_id)
        assert summary.total_paid == 1500
        assert summary.remaining == 500
        assert summary.payment_status == PaymentStatus.PARTIAL
        with database.session_scope() as session:
            payments = financial_service.get_payment_history(session, booking_id)
            assert len(payments) == 1
            assert payments[0].payment_method == PaymentMethod.UPI.value
            assert payments[0].status == PaymentRecordStatus.COMPLETED.value
    finally:
        database.dispose()


def test_full_payment_marks_booking_paid(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 2000)
        summary = _summary(database, booking_id)
        assert summary.remaining == 0
        assert summary.payment_status == PaymentStatus.PAID
    finally:
        database.dispose()


def test_overpayment_is_rejected(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 1500)
        with pytest.raises(OverPaymentError):
            _pay(database, booking_id, 1000)
    finally:
        database.dispose()


def test_non_positive_and_invalid_method_payments_rejected(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        with pytest.raises(PaymentValidationError):
            _pay(database, booking_id, 0)
        with pytest.raises(PaymentValidationError):
            _pay(database, booking_id, -100)
        with pytest.raises(PaymentValidationError):
            _pay(database, booking_id, 100, method="Bitcoin")
    finally:
        database.dispose()


def test_reverse_payment_excludes_from_paid_but_keeps_record(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 800, method="CASH", when=date.today())
        with database.session_scope() as session:
            payment = financial_service.get_payment_history(session, booking_id)[0]
            financial_service.reverse_payment(session, payment.id, "Guest requested refund")
        summary = _summary(database, booking_id)
        assert summary.total_paid == 0
        assert summary.payment_status == PaymentStatus.UNPAID
        with database.session_scope() as session:
            payment = financial_service.get_payment_history(session, booking_id)[0]
            assert payment.status == PaymentRecordStatus.REFUNDED.value
            assert payment.reversal_reason == "Guest requested refund"
            assert payment.reversed_at is not None
    finally:
        database.dispose()


def test_cannot_reverse_a_payment_twice_or_without_reason(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 800)
        with database.session_scope() as session:
            payment = financial_service.get_payment_history(session, booking_id)[0]
            financial_service.reverse_payment(session, payment.id, "Refund")
            with pytest.raises(PaymentValidationError):
                financial_service.reverse_payment(session, payment.id, "Again")
        with database.session_scope() as session:
            payment = financial_service.get_payment_history(session, booking_id)[0]
            with pytest.raises(PaymentValidationError):
                financial_service.reverse_payment(session, payment.id, "  ")
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Today's collected
# ---------------------------------------------------------------------------

def test_today_payment_total_counts_only_completed_today(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        booking_id = _reserve(database, _add_guest(database), 1, rate=1000)
        _pay(database, booking_id, 500, when=date.today())
        _pay(database, booking_id, 300, when=date.today())
        # Record one on another day.
        yesterday = date.today() - timedelta(days=1)
        with database.session_scope() as session:
            financial_service.record_payment(
                session,
                booking_id=booking_id,
                amount=200,
                payment_method="CASH",
                payment_date=yesterday,
            )
        with database.session_scope() as session:
            assert financial_service.get_today_payment_total(session, date.today()) == 800
            assert financial_service.get_today_payment_total(session, yesterday) == 200
    finally:
        database.dispose()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_missing_booking_raises_financial_error(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        with pytest.raises(FinancialError):
            _summary(database, 99999)
    finally:
        database.dispose()


def test_payment_status_helper(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        assert financial_service.get_payment_status(0, 0) == PaymentStatus.PAID
        assert financial_service.get_payment_status(1000, 0) == PaymentStatus.UNPAID
        assert financial_service.get_payment_status(1000, 500) == PaymentStatus.PARTIAL
        assert financial_service.get_payment_status(1000, 1000) == PaymentStatus.PAID
    finally:
        database.dispose()


def test_grand_total_never_negative_with_large_discount_blocked(tmp_path) -> None:  # noqa: ANN001
    database = _make_database(tmp_path)
    try:
        _seed(database)
        # Zero-rate booking: no charges at all -> paid, zero balance.
        guest_id = _add_guest(database)
        with database.session_scope() as session:
            booking = booking_service.create_reservation(
                session,
                guest_id=guest_id,
                room_id=1,
                booking_source_id=1,
                check_in_date=date.today(),
                check_in_time=dtime(12, 0),
                check_out_date=date.today() + timedelta(days=1),
                check_out_time=dtime(11, 0),
                room_rate=0,
            )
            booking_id = booking.id
        summary = _summary(database, booking_id)
        assert summary.grand_total == 0
        assert summary.payment_status == PaymentStatus.PAID
    finally:
        database.dispose()
