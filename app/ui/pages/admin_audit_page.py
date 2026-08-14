"""Admin Audit Log page.

Shows the audit trail of admin actions (logins, password changes, settings
and source changes, exports). Data is stored in the ``audit_logs`` table via
:mod:`app.services.audit_service`.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import audit_service
from app.ui.widgets.empty_state import EmptyState
from app.ui.widgets.table import configure_table

_FILTERS = (
    ("all", "All"),
    ("admin_login", "Logins"),
    ("settings_changed", "Settings"),
    ("booking_source", "Sources"),
    ("report_generated", "Exports"),
    ("password_changed", "Password"),
)


class AdminAuditPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._action_filter: str | None = None
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Audit Log")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("A record of admin actions. Passwords are never stored.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        label = QLabel("Filter:")
        label.setProperty("detailLabel", True)
        filter_row.addWidget(label)
        self._group = QButtonGroup(self)
        for key, text in _FILTERS:
            button = QPushButton(text)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("actionFilter", key)
            if key == "all":
                button.setChecked(True)
            self._group.addButton(button)
            filter_row.addWidget(button)
        filter_row.addStretch(1)
        clear_button = QPushButton("Clear Log")
        clear_button.setObjectName("SecondaryButton")
        clear_button.clicked.connect(self._clear_log)
        filter_row.addWidget(clear_button)
        self._group.buttonClicked.connect(self._on_filter)
        layout.addLayout(filter_row)

        self.table = QTableWidget()
        configure_table(
            self.table,
            ["Date & Time", "Action", "Description"],
            resize_to_contents_cols=[0, 1],
        )
        layout.addWidget(self.table, 1)

        self.empty_state = EmptyState("No audit entries", "No admin actions recorded.", icon="📋")
        self.empty_state.setVisible(False)
        layout.addWidget(self.empty_state)

    # ------------------------------------------------------------- filters

    def _on_filter(self, button) -> None:  # noqa: ANN001
        value = button.property("actionFilter")
        self._action_filter = None if value == "all" else value
        self.refresh()

    def _clear_log(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear Audit Log",
            "Clear the entire audit log? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        with self.database.session_scope() as session:
            audit_service.clear_audit_log(session)
        self.refresh()

    # --------------------------------------------------------------- data

    def refresh(self) -> None:
        with self.database.session_scope() as session:
            entries = audit_service.get_audit_log(session, limit=1000)
            if self._action_filter:
                entries = [entry for entry in entries if entry.action == self._action_filter]

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for row_index, entry in enumerate(entries):
            self.table.insertRow(row_index)
            self.table.setItem(row_index, 0, QTableWidgetItem(entry.created_at.strftime("%d %b %Y, %I:%M %p")))
            self.table.setItem(row_index, 1, QTableWidgetItem(entry.action))
            self.table.setItem(row_index, 2, QTableWidgetItem(entry.description or ""))
        self.table.setSortingEnabled(True)

        has_rows = bool(entries)
        self.table.setVisible(has_rows)
        self.empty_state.setVisible(not has_rows)
