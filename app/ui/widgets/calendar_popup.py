"""Polished calendar popup used by the read-only date fields.

A lightweight, theme-matched calendar built from plain Qt widgets. It
highlights today, shows the currently selected date, navigates between
months and lets the user pick a day with a single click.
"""

from __future__ import annotations

from calendar import month_name, monthrange
from datetime import date, timedelta

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.styles import COLORS

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class CalendarPopup(QFrame):
    """A compact, theme-matched month calendar with day-picking."""

    date_selected = Signal(object)  # datetime.date

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CalendarPopup")
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._selected: date | None = None
        self._view_month = date.today().replace(day=1)
        self._day_buttons: list[list[QPushButton]] = []
        self._day_dates: dict[QPushButton, date] = {}

        self.setStyleSheet(self._stylesheet())
        self._build_ui()
        self._rebuild()

    # ------------------------------------------------------------------ UI

    def _stylesheet(self) -> str:
        return f"""
        QFrame#CalendarPopup {{
            background: {COLORS["surface"]};
            border: 1px solid {COLORS["border_strong"]};
            border-radius: 10px;
        }}
        QLabel#CalendarTitle {{
            color: {COLORS["text"]};
            font-size: 14px;
            font-weight: 700;
        }}
        QLabel#WeekdayHeader {{
            color: {COLORS["text_secondary"]};
            font-size: 11px;
            font-weight: 600;
        }}
        QPushButton#NavButton {{
            background: transparent;
            border: none;
            color: {COLORS["text_secondary"]};
            font-size: 18px;
            font-weight: 600;
            padding: 0px;
            border-radius: 6px;
        }}
        QPushButton#NavButton:hover {{
            background: {COLORS["surface_hover"]};
            color: {COLORS["text"]};
            border: none;
        }}
        QPushButton#DayButton {{
            background: transparent;
            border: 2px solid transparent;
            color: {COLORS["text"]};
            font-size: 13px;
            border-radius: 8px;
            padding: 0px;
        }}
        QPushButton#DayButton:hover {{
            background: {COLORS["surface_hover"]};
        }}
        QPushButton#DayButton[otherMonth="true"] {{
            color: {COLORS["text_muted"]};
        }}
        QPushButton#DayButton[today="true"] {{
            border-color: {COLORS["primary"]};
            color: {COLORS["primary"]};
            font-weight: 700;
        }}
        QPushButton#DayButton[selected="true"] {{
            background: {COLORS["primary"]};
            border-color: {COLORS["primary"]};
            color: #FFFFFF;
            font-weight: 700;
        }}
        QPushButton#DayButton[selected="true"]:hover {{
            background: {COLORS["primary_hover"]};
            border-color: {COLORS["primary_hover"]};
        }}
        QPushButton#TodayButton {{
            background: transparent;
            border: 1px solid {COLORS["border_strong"]};
            color: {COLORS["primary"]};
            font-size: 12px;
            font-weight: 600;
            padding: 3px 14px;
            border-radius: 8px;
        }}
        QPushButton#TodayButton:hover {{
            background: {COLORS["surface_hover"]};
            border-color: {COLORS["border_strong"]};
            color: {COLORS["primary"]};
        }}
        """

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.prev_button = QPushButton("\u2039")
        self.prev_button.setObjectName("NavButton")
        self.prev_button.setFixedSize(30, 30)
        self.prev_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_button.clicked.connect(self._previous_month)
        self.title_label = QLabel()
        self.title_label.setObjectName("CalendarTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.next_button = QPushButton("\u203a")
        self.next_button.setObjectName("NavButton")
        self.next_button.setFixedSize(30, 30)
        self.next_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_button.clicked.connect(self._next_month)
        header.addWidget(self.prev_button)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.next_button)
        layout.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(2)
        for column, name in enumerate(_WEEKDAYS):
            label = QLabel(name)
            label.setObjectName("WeekdayHeader")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, column)

        self._day_buttons = []
        for row in range(6):
            day_row: list[QPushButton] = []
            for column in range(7):
                button = QPushButton()
                button.setObjectName("DayButton")
                button.setFixedSize(36, 32)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.clicked.connect(
                    lambda _=False, r=row, c=column: self._pick_day(r, c)
                )
                grid.addWidget(button, row + 1, column)
                day_row.append(button)
            self._day_buttons.append(day_row)
        layout.addLayout(grid)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.today_button = QPushButton("Today")
        self.today_button.setObjectName("TodayButton")
        self.today_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_button.clicked.connect(self._pick_today)
        footer.addWidget(self.today_button)
        layout.addLayout(footer)

    # ------------------------------------------------------------- state

    def set_selected_date(self, value: date | None) -> None:
        self._selected = value
        if value is not None:
            self._view_month = value.replace(day=1)
        self._rebuild()

    def set_view_month(self, value: date) -> None:
        self._view_month = value.replace(day=1)
        self._rebuild()

    def show_below(self, anchor: QWidget) -> None:
        """Position the popup just under ``anchor`` and show it."""
        self.adjustSize()
        from PySide6.QtWidgets import QApplication

        screen = QApplication.screenAt(anchor.mapToGlobal(QPoint(0, 0)))
        if screen is None:
            screen = QApplication.primaryScreen()
        available = screen.availableGeometry()

        x = anchor.mapToGlobal(QPoint(0, anchor.height() + 4)).x()
        y = anchor.mapToGlobal(QPoint(0, anchor.height() + 4)).y()
        x = max(available.left() + 4, min(x, available.right() - self.width() - 4))
        if y + self.height() > available.bottom():
            y = max(available.top() + 4, anchor.mapToGlobal(QPoint(0, 0)).y() - self.height() - 4)
        self.move(x, y)
        self.show()
        self.raise_()
        self.setFocus()

    # ----------------------------------------------------------- building

    def _rebuild(self) -> None:
        today = date.today()
        self.title_label.setText(
            f"{month_name[self._view_month.month]} {self._view_month.year}"
        )
        first_weekday = self._view_month.weekday()
        start = self._view_month - timedelta(days=first_weekday)
        for row in range(6):
            for column in range(7):
                day = start + timedelta(days=row * 7 + column)
                button = self._day_buttons[row][column]
                button.setText(str(day.day))
                self._day_dates[button] = day
                button.setProperty(
                    "otherMonth", str(day.month != self._view_month.month).lower()
                )
                button.setProperty("today", str(day == today).lower())
                button.setProperty(
                    "selected",
                    str(self._selected is not None and day == self._selected).lower(),
                )
                button.style().unpolish(button)
                button.style().polish(button)

    # ------------------------------------------------------------ actions

    def _previous_month(self) -> None:
        year = self._view_month.year - 1 if self._view_month.month == 1 else self._view_month.year
        month = 12 if self._view_month.month == 1 else self._view_month.month - 1
        self._view_month = date(year, month, 1)
        self._rebuild()

    def _next_month(self) -> None:
        year = self._view_month.year + 1 if self._view_month.month == 12 else self._view_month.year
        month = 1 if self._view_month.month == 12 else self._view_month.month + 1
        self._view_month = date(year, month, 1)
        self._rebuild()

    def _pick_day(self, row: int, column: int) -> None:
        day = self._day_dates.get(self._day_buttons[row][column])
        if day is None:
            return
        self._selected = day
        self._view_month = day.replace(day=1)
        self.date_selected.emit(day)
        self.hide()

    def _pick_today(self) -> None:
        self._selected = date.today()
        self._view_month = self._selected.replace(day=1)
        self.date_selected.emit(self._selected)
        self.hide()
