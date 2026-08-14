"""Declarative base for all SQLAlchemy models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class shared by every model.

    Future models (rooms, guests, bookings, payments, invoices, ...) just
    subclass :class:`Base` and are automatically registered with the
    metadata used by :meth:`app.database.database.Database.create_all`.
    """

    pass
