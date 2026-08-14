"""Lightweight bar chart widget (no external charting dependency).

Renders a vertical bar chart from ``(label, value)`` pairs using QPainter.
Kept deliberately simple so the 4 GB reception computers stay responsive.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

_COLORS = [
    "#2563eb",
    "#0284c7",
    "#16a34a",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#64748b",
    "#db2777",
    "#ca8a04",
    "#0891b2",
]


class BarChart(QWidget):
    """Vertical bar chart with labels and value callouts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items: list[tuple[str, float]] = []
        self._unit: str = ""
        self.setMinimumHeight(220)

    def set_data(self, items: list[tuple[str, Any]], unit: str = "") -> None:
        """Set ``(label, value)`` pairs to render."""
        self._items = [(label, float(value or 0)) for label, value in items]
        self._unit = unit
        self.update()

    def clear(self) -> None:
        self._items = []
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        if width < 40 or height < 60 or not self._items:
            painter.end()
            return

        margin_left = 54
        margin_right = 12
        margin_top = 24
        margin_bottom = 34
        plot_left = margin_left
        plot_right = width - margin_right
        plot_top = margin_top
        plot_bottom = height - margin_bottom
        plot_w = plot_right - plot_left
        plot_h = plot_bottom - plot_top

        values = [value for _, value in self._items]
        max_value = max(values) if values else 0
        if max_value <= 0:
            max_value = 1

        # Y axis labels.
        painter.setPen(QPen(QColor("#475569")))
        label_font = QFont("Inter", 10)
        if not label_font.exactMatch():
            label_font = QFont("Segoe UI", 10)
        label_font.setWeight(QFont.Weight.Medium)
        painter.setFont(label_font)
        for step in range(5):
            fraction = step / 4
            value = max_value * fraction
            y = plot_bottom - plot_h * fraction
            painter.drawText(
                QRectF(0, y - 10, margin_left - 8, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                self._fmt(value),
            )
            if step:
                painter.setPen(QPen(QColor("#e2e8f0")))
                painter.drawLine(plot_left, int(y), plot_right, int(y))
                painter.setPen(QPen(QColor("#475569")))

        # Bars.
        bar_area = plot_w - 20
        bar_gap = 6
        bar_count = len(self._items)
        bar_w = max(6, min(46, (bar_area - bar_gap * (bar_count - 1)) / bar_count))

        value_font = QFont("Inter", 10)
        if not value_font.exactMatch():
            value_font = QFont("Segoe UI", 10)
        value_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(value_font)
        for index, (label, value) in enumerate(self._items):
            x = plot_left + 10 + index * (bar_w + bar_gap)
            bar_h = (value / max_value) * plot_h
            y = plot_bottom - bar_h
            color = QColor(_COLORS[index % len(_COLORS)])
            painter.setPen(QPen(color))
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 3, 3)

            painter.setPen(QPen(QColor("#0f172a")))
            painter.drawText(
                QRectF(x - 14, y - 18, bar_w + 28, 16),
                Qt.AlignmentFlag.AlignCenter,
                self._fmt(value),
            )

            # X axis label.
            painter.setPen(QPen(QColor("#475569")))
            painter.drawText(
                QRectF(x - 12, plot_bottom + 4, bar_w + 24, 26),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label,
            )

        painter.end()

    def _fmt(self, value: float) -> str:
        text = f"{value:,.0f}"
        if self._unit == "currency":
            return f"\u20b9{text}"
        return text
