"""Pytest configuration and shared fixtures.

* A function-scoped autouse fixture disposes every live SQLite connection
  after each test, so no :class:`Database` handle or connection survives its
  test (SQLite connections are never left open between tests).
* Qt is forced to the offscreen platform so service tests never attempt to
  open a window or connect to a display.
* The session-scoped template database (see ``tests/_db_support``) is
  cleaned up when the session finishes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.database.database import dispose_all_databases
from tests._db_support import cleanup_template

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _close_databases_after_test() -> Iterator[None]:
    """Close every Database created during a test before the next one runs."""
    yield
    dispose_all_databases()


@pytest.fixture(scope="session", autouse=True)
def _cleanup_template_at_session_end() -> Iterator[None]:
    """Remove the shared template database file when the session ends."""
    yield
    dispose_all_databases()
    cleanup_template()
