from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database.base import Base


def run_schema_migrations(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "rooms" in tables:
        columns = {column["name"] for column in inspector.get_columns("rooms")}
        statements: list[str] = []
        if "created_at" not in columns:
            statements.append("ALTER TABLE rooms ADD COLUMN created_at DATETIME")
        if "updated_at" not in columns:
            statements.append("ALTER TABLE rooms ADD COLUMN updated_at DATETIME")
        if statements:
            with engine.begin() as connection:
                for statement in statements:
                    connection.execute(text(statement))
                connection.execute(
                    text(
                        "UPDATE rooms SET created_at = CURRENT_TIMESTAMP, "
                        "updated_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"
                    )
                )

    if "bookings" in tables:
        columns = {column["name"] for column in inspector.get_columns("bookings")}
        if "discount" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN discount NUMERIC(10, 2) DEFAULT 0"))
        if "actual_check_out_at" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN actual_check_out_at DATETIME"))
        if "deleted_at" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN deleted_at DATETIME"))
        if "deleted_by" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN deleted_by VARCHAR(100) DEFAULT ''"))
        if "deletion_reason" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN deletion_reason VARCHAR(500) DEFAULT ''"))
        if "paid_online" not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE bookings ADD COLUMN paid_online BOOLEAN DEFAULT 0"))

        guest_id_column = next((c for c in inspector.get_columns("bookings") if c["name"] == "guest_id"), None)
        if guest_id_column is not None and not guest_id_column.get("nullable", True):
            raw = engine.raw_connection()
            try:
                cursor = raw.cursor()
                cursor.execute("PRAGMA foreign_keys=OFF")
                cursor.execute("BEGIN")
                cursor.execute(
                    """
                    CREATE TABLE bookings_new (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        booking_number VARCHAR(30) NOT NULL,
                        guest_id INTEGER,
                        room_id INTEGER NOT NULL,
                        booking_source_id INTEGER NOT NULL,
                        check_in_date DATE NOT NULL,
                        check_in_time TIME,
                        check_out_date DATE NOT NULL,
                        check_out_time TIME,
                        adults INTEGER NOT NULL DEFAULT 1,
                        children INTEGER NOT NULL DEFAULT 0,
                        room_rate NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        extra_person_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        early_check_in_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        late_check_out_charge NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        discount NUMERIC(10, 2) NOT NULL DEFAULT 0,
                        paid_online BOOLEAN NOT NULL DEFAULT 0,
                        special_notes VARCHAR(1000) NOT NULL DEFAULT '',
                        status VARCHAR(30) NOT NULL,
                        actual_check_out_at DATETIME,
                        cancelled_at DATETIME,
                        cancellation_reason VARCHAR(500) NOT NULL DEFAULT '',
                        cancelled_by VARCHAR(100) NOT NULL DEFAULT '',
                        no_show_at DATETIME,
                        no_show_reason VARCHAR(500) NOT NULL DEFAULT '',
                        deleted_at DATETIME,
                        deleted_by VARCHAR(100) NOT NULL DEFAULT '',
                        deletion_reason VARCHAR(500) NOT NULL DEFAULT '',
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO bookings_new(id, booking_number, guest_id, room_id, booking_source_id,check_in_date, check_in_time, check_out_date, check_out_time,adults, children, room_rate, extra_person_charge,early_check_in_charge, late_check_out_charge, discount,paid_online, special_notes, status, actual_check_out_at, cancelled_at,cancellation_reason, cancelled_by, no_show_at, no_show_reason,deleted_at, deleted_by, deletion_reason, created_at, updated_at)
                    SELEC id, booking_number, guest_id, room_id, booking_source_id,check_in_date, check_in_time, check_out_date, check_out_time,adults, children, room_rate, extra_person_charge,
                        early_check_in_charge, late_check_out_charge, discount,paid_online, special_notes, status, actual_check_out_at, cancelled_at,
                        cancellation_reason, cancelled_by, no_show_at, no_show_reason,deleted_at, deleted_by, deletion_reason, created_at, updated_at
                    FROM bookings
                    """
                )
                cursor.execute("DROP TABLE bookings")
                cursor.execute("ALTER TABLE bookings_new RENAME TO bookings")
                cursor.execute(
                    "CREATE UNIQUE INDEX ix_bookings_booking_number ON bookings (booking_number)"
                )
                cursor.execute("CREATE INDEX ix_bookings_guest_id ON bookings (guest_id)")
                cursor.execute("CREATE INDEX ix_bookings_room_id ON bookings (room_id)")
                cursor.execute(
                    "CREATE INDEX ix_bookings_booking_source_id ON bookings (booking_source_id)"
                )
                cursor.execute("CREATE INDEX ix_bookings_check_in_date ON bookings (check_in_date)")
                cursor.execute("CREATE INDEX ix_bookings_check_out_date ON bookings (check_out_date)")
                cursor.execute("CREATE INDEX ix_bookings_status ON bookings (status)")
                cursor.execute("COMMIT")
                cursor.execute("PRAGMA foreign_keys=ON")
                raw.commit()
            finally:
                raw.close()
    if "payments" in tables:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_payments_status "
                    "ON payments (status)"
                )
            )
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_payments_booking_id_status "
                    "ON payments (booking_id, status)"
                )
            )

    Base.metadata.create_all(engine)
