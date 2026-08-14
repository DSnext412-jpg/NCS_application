"""Admin Reports page.

Builds the four Phase 6 reports (Financial, Booking Sources, Occupancy,
Booking Trend) for a selectable period and exports them as CSV, Excel or
PDF. All data goes through :mod:`app.services.report_service` so the
on-screen table and every export always match.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import audit_service, report_service
from app.ui.widgets.table import configure_table

_REPORT_TABS = (
    ("financial", "Financial"),
    ("sources", "Booking Sources"),
    ("occupancy", "Occupancy"),
    ("booking_trend", "Booking Trend"),
)

_PERIOD_PRESETS = (
    ("today", "Today"),
    ("week", "This Week"),
    ("month", "This Month"),
    ("year", "This Year"),
    ("custom", "Custom"),
)


class AdminReportsPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._period: str = "week"
        self._report_type: str = "financial"
        self._tables_layouts: dict[str, QVBoxLayout] = {}

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        title = QLabel("Reports")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Operational and financial reports. Export as CSV, Excel or PDF.")
        subtitle.setObjectName("PageSubtitle")
        layout.addWidget(subtitle)

        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        self._period_group = QButtonGroup(self)
        for key, label in _PERIOD_PRESETS:
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("periodKey", key)
            if key == "week":
                button.setChecked(True)
            self._period_group.addButton(button)
            period_row.addWidget(button)
        period_row.addSpacing(14)
        period_row.addWidget(QLabel("From"))
        self.date_from_edit = QDateEdit()
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_from_edit.setEnabled(False)
        period_row.addWidget(self.date_from_edit)
        period_row.addWidget(QLabel("To"))
        self.date_to_edit = QDateEdit()
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDisplayFormat("dd-MM-yyyy")
        self.date_to_edit.setEnabled(False)
        period_row.addWidget(self.date_to_edit)
        self._period_group.buttonClicked.connect(self._on_period)
        self.date_from_edit.dateChanged.connect(self.refresh)
        self.date_to_edit.dateChanged.connect(self.refresh)
        period_row.addStretch(1)
        layout.addLayout(period_row)

        self.tabs = QTabWidget()
        for key, label in _REPORT_TABS:
            self.tabs.addTab(self._make_report_tab(key), label)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, 1)

    def _make_report_tab(self, report_type: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 10, 4, 4)
        layout.setSpacing(12)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(12)
        self.summary_labels: dict[tuple[str, int], QLabel] = {}
        layout.addLayout(summary_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(14)
        scroll.setWidget(container)
        self._tables_layouts[report_type] = container_layout
        layout.addWidget(scroll, 1)

        export_row = QHBoxLayout()
        export_row.addStretch(1)
        for fmt, label in (("csv", "Export CSV"), ("xlsx", "Export Excel"), ("pdf", "Export PDF")):
            button = QPushButton(label)
            button.setObjectName("ActionButton")
            button.clicked.connect(lambda checked=False, f=fmt: self._export(f))
            export_row.addWidget(button)
        layout.addLayout(export_row)

        return page

    # -------------------------------------------------------------- actions

    def _on_period(self, button) -> None:  # noqa: ANN001
        key = button.property("periodKey")
        if not key:
            return
        self._period = key
        custom = key == "custom"
        today = date.today()
        if custom:
            self.date_from_edit.setDate(QDate(today.replace(day=1)))
            self.date_to_edit.setDate(QDate(today))
        self.date_from_edit.setEnabled(custom)
        self.date_to_edit.setEnabled(custom)
        self.refresh()

    def _on_tab_changed(self, index: int) -> None:
        self._report_type = _REPORT_TABS[index][0]
        self.refresh()

    def _qdate(self, widget: QDateEdit) -> date:
        qdate = widget.date()
        return date(qdate.year(), qdate.month(), qdate.day())

    # --------------------------------------------------------------- data

    def _current_range(self) -> tuple[date, date]:
        today = date.today()
        if self._period == "today":
            return today, today
        if self._period == "month":
            return today.replace(day=1), today
        if self._period == "year":
            return today.replace(month=1, day=1), today
        if self._period == "custom":
            start, end = self._qdate(self.date_from_edit), self._qdate(self.date_to_edit)
            return (start, end) if start <= end else (end, start)
        week_start = today - timedelta(days=today.weekday())
        return week_start, today

    def refresh(self) -> None:
        date_from, date_to = self._current_range()
        with self.database.session_scope() as session:
            report = report_service.build_report(session, self._report_type, date_from, date_to)
        self._current_report = report

        index = 0
        for report_type, _ in _REPORT_TABS:
            if report_type == self._report_type:
                break
            index += 1
        page = self.tabs.widget(index)

        summary_row = page.layout().itemAt(0).layout()
        while summary_row.count():
            item = summary_row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for pair in (report.summary or [])[:6]:
            frame = QFrame()
            frame.setObjectName("Card")
            frame_layout = QVBoxLayout(frame)
            frame_layout.setContentsMargins(14, 10, 14, 10)
            frame_layout.setSpacing(2)
            title_label = QLabel(pair[0])
            title_label.setProperty("cardTitle", True)
            frame_layout.addWidget(title_label)
            value_label = QLabel(pair[1])
            value_label.setProperty("cardValue", True)
            value_label.setStyleSheet("font-size: 20px;")
            frame_layout.addWidget(value_label)
            summary_row.addWidget(frame, 1)

        table_layout = self._tables_layouts[self._report_type]
        while table_layout.count():
            item = table_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if not report.tables:
            table_layout.addStretch(1)
            return
        for report_table in report.tables:
            heading = QLabel(report_table.name)
            heading.setObjectName("SectionHeading")
            table_layout.addWidget(heading)
            table = QTableWidget()
            configure_table(table, report_table.headers, row_height=36, resize_to_contents_cols=[0])
            table.setRowCount(len(report_table.rows))
            for row_index, row in enumerate(report_table.rows):
                for col_index, value in enumerate(row):
                    table.setItem(row_index, col_index, QTableWidgetItem(value))
            table_layout.addWidget(table)
        table_layout.addStretch(1)

    # -------------------------------------------------------------- export

    def _export(self, fmt: str) -> None:
        report = getattr(self, "_current_report", None)
        if report is None:
            return
        try:
            from app.services import report_export

            path = report_export.export_report(report, fmt)
            with self.database.session_scope() as session:
                audit_service.log_action(
                    session,
                    audit_service.ACTION_REPORT_GENERATED,
                    f"Exported {report.title} as {fmt.upper()} ({path.name}).",
                )
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Report export failed")
            QMessageBox.critical(self, "Export Failed", "Could not export the report. See logs for details.")
            return
        QMessageBox.information(
            self,
            "Export Complete",
            f"Report exported to:\n{path}",
        )
