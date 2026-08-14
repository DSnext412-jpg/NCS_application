"""SQLite database infrastructure built on SQLAlchemy.

Provides the engine, session factory, table creation and safe session
handling. The database filename is ``hotel.db`` resolved through the
centralized :class:`app.core.paths.Paths` manager.
"""

from __future__ import annotations

import logging
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database.migrations import run_schema_migrations

# Import models so they register with Base.metadata.
from app.database import models  # noqa: F401

logger = logging.getLogger(__name__)

# Live Database instances (weak, so garbage collection is unaffected). Lets
# the application and the test suite deterministically close every SQLite
# connection instead of relying on the garbage collector.
_live_databases: weakref.WeakSet[Database] = weakref.WeakSet()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # noqa: ANN001
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Owns the SQLite engine and session factory for the application."""

    def __init__(self, database_path: str | Path, echo: bool = False) -> None:
        self.database_path = Path(database_path).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine: Engine = create_engine(
            f"sqlite:///{self.database_path}",
            echo=echo,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _set_sqlite_pragma)
        self.SessionFactory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )
        _live_databases.add(self)

    def create_all(self) -> None:
        """Create missing tables and apply safe, idempotent migrations.

        Works with both fresh databases and existing Phase 1 databases
        without deleting or recreating them.
        """
        run_schema_migrations(self.engine)

    def new_session(self) -> Session:
        return self.SessionFactory()

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """Provide a transactional session that commits/rolls back safely.

        Example::

            with database.session_scope() as session:
                session.add(...)
        """
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """Release the underlying SQLite connection pool."""
        self.engine.dispose()


def dispose_all_databases() -> None:
    """Close every live :class:`Database` instance's SQLite connections.

    Idempotent and safe to call from tests (or application shutdown) to
    guarantee no SQLite file handle survives.
    """
    for database in list(_live_databases):
        try:
            database.dispose()
        except Exception:  # noqa: BLE001 - never let cleanup hide the test result
            logger.warning("Failed to dispose Database %s", database.database_path, exc_info=True)
