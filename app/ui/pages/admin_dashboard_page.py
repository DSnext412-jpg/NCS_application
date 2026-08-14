"""Admin Dashboard page.

Shows revenue KPIs, payment overview, booking-source breakdown, occupancy
and trend charts. All figures come from :mod:`app.services.analytics_service`
and use completed payments / payment-date revenue rules (never double
counted). This page is only reachable after an admin login.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.database.database import Database
from app.services import analytics_service, booking_service
from app.ui.formatters import format_money
from app.ui.widgets.bar_chart import BarChart
from app.ui.widgets.summary_card import SummaryCard


class AdminDashboardPage(QWidget):
    def __init__(self, database: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Admin Dashboard")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel(
            "Revenue and occupancy for the selected period — tap a period chip to change it."
        )
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(subtitle)

        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        from PySide6.QtWidgets import QButtonGroup, QPushButton

        self._period_group = QButtonGroup(self)
        for key, label in (("today", "Today"), ("week", "This Week"), ("month", "This Month"), ("year", "This Year")):
            button = QPushButton(label)
            button.setObjectName("FilterChip")
            button.setCheckable(True)
            button.setProperty("periodKey", key)
            if key == "today":
                button.setChecked(True)
            self._period_group.addButton(button)
            period_row.addWidget(button)
        period_row.addStretch(1)
        self._period_group.buttonClicked.connect(self._on_period)
        root.addLayout(period_row)

        self._scroll_container = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_container)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(self._scroll_container)
        root.addWidget(scroll, 1)

        self._cards: dict[str, SummaryCard] = {}
        self._build_cards()
        self._build_charts()

    def _build_cards(self) -> None:
        revenue_titles = ("today", "week", "month", "year")
        revenue_labels = ("Today's Revenue", "This Week", "This Month", "This Year")
        revenue_icons = ("📅", "📆", "🗓️", "📊")
        row = QHBoxLayout()
        row.setSpacing(12)
        self._revenue_cards = {}
        for key, label, icon in zip(revenue_titles, revenue_labels, revenue_icons, strict=False):
            card = SummaryCard(label, icon=icon, accent="paid")
            card.setMinimumHeight(92)
            self._revenue_cards[key] = card
            row.addWidget(card, 1)
        self._scroll_layout.addLayout(row)

        overview_titles = ("collected", "outstanding", "paid", "partial", "unpaid")
        overview_labels = ("Collected", "Outstanding", "Fully Paid", "Partial", "Unpaid")
        overview_icons = ("💰", "⏳", "✅", "🟡", "⛔")
        overview_accents = ("paid", "unpaid", "paid", "partial", "unpaid")
        row = QHBoxLayout()
        row.setSpacing(12)
        self._overview_cards = {}
        for key, label, icon, accent in zip(
            overview_titles, overview_labels, overview_icons, overview_accents, strict=False
        ):
            card = SummaryCard(label, icon=icon, accent=accent)
            card.setMinimumHeight(92)
            self._overview_cards[key] = card
            row.addWidget(card, 1)
        self._scroll_layout.addLayout(row)

        activity_row = QHBoxLayout()
        activity_row.setSpacing(12)
        self.check_ins_card = SummaryCard("Check-ins Today", icon="📥", accent="reserved")
        self.check_outs_card = SummaryCard("Check-outs Today", icon="📤", accent="checked-out")
        self.occupancy_card = SummaryCard("Occupancy (7 days)", icon="🏨", accent="occupied")
        for card in (self.check_ins_card, self.check_outs_card, self.occupancy_card):
            card.setMinimumHeight(92)
            activity_row.addWidget(card, 1)
        self._scroll_layout.addLayout(activity_row)

    def _build_charts(self) -> None:
        chart_row = QHBoxLayout()
        chart_row.setSpacing(14)
        self.method_chart = BarChart()
        self.source_chart = BarChart()
        chart_row.addWidget(self._chart_frame("Revenue by Payment Method", self.method_chart), 1)
        chart_row.addWidget(self._chart_frame("Bookings by Source", self.source_chart), 1)
        self._scroll_layout.addLayout(chart_row)

        trend_row = QHBoxLayout()
        trend_row.setSpacing(14)
        self.revenue_chart = BarChart()
        self.booking_chart = BarChart()
        trend_row.addWidget(self._chart_frame("Revenue Trend (7 days)", self.revenue_chart), 1)
        trend_row.addWidget(self._chart_frame("Bookings Trend (7 days)", self.booking_chart), 1)
        self._scroll_layout.addLayout(trend_row)

    def _chart_frame(self, title: str, chart: BarChart) -> QWidget:
        frame = QWidget()
        frame.setObjectName("Card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setProperty("cardTitle", True)
        layout.addWidget(label)
        layout.addWidget(chart, 1)
        return frame

    # -------------------------------------------------------------- actions

    def _on_period(self, button) -> None:  # noqa: ANN001
        key = button.property("periodKey")
        if key:
            self._period = key
            self.refresh()

    # --------------------------------------------------------------- data

    def refresh(self) -> None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        with self.database.session_scope() as session:
            period = getattr(self, "_period", "today")
            period_range = {
                "today": (today, today),
                "week": (week_start, today),
                "month": (month_start, today),
                "year": (year_start, today),
            }[period]
            revenue = analytics_service.get_revenue(session, *period_range)
            overview = analytics_service.get_payment_overview(session, *period_range)
            methods = analytics_service.get_revenue_by_method(session, *period_range)
            sources = analytics_service.get_booking_counts_by_source(session, *period_range)
            occupancy = analytics_service.get_occupancy(session, today - timedelta(days=6), today)
            check_ins = booking_service.get_today_check_ins(session, today)
            check_outs = booking_service.get_today_check_outs(session, today)
            trend_start = today - timedelta(days=6)
            revenue_trend = analytics_service.get_revenue_by_day(session, trend_start, today)
            booking_trend = analytics_service.get_booking_trend(session, trend_start, today)

        for key, card in self._revenue_cards.items():
            card.set_value(format_money(revenue if period == key else 0))
            card.set_subtext("Completed payments, " + period)

        self._overview_cards["collected"].set_value(format_money(overview["collected"]))
        self._overview_cards["collected"].set_subtext("Completed payments in period")
        self._overview_cards["outstanding"].set_value(format_money(overview["outstanding"]))
        self._overview_cards["outstanding"].set_subtext("Remaining balance, stays in period")
        for key in ("paid", "partial", "unpaid"):
            self._overview_cards[key].set_value(overview[key])

        self.check_ins_card.set_value(len(check_ins))
        self.check_outs_card.set_value(len(check_outs))
        self.occupancy_card.set_value(f"{occupancy['occupancy_percent']}%")
        self.occupancy_card.set_subtext(
            f"{occupancy['occupied_nights']} of {occupancy['available_nights']} room nights"
        )

        self.method_chart.set_data(sorted(methods.items()), unit="currency")
        self.source_chart.set_data(sorted(sources.items()))
        self.revenue_chart.set_data([(d.strftime("%d %b"), v) for d, v in revenue_trend], unit="currency")
        self.booking_chart.set_data(
            [
                (t["date"].strftime("%d %b"), t["reservations"] + t["check_ins"] + t["check_outs"])
                for t in booking_trend
            ]
        )

