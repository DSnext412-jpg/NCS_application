"""Summary card used across dashboards for KPI counts and totals."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.ui.styles import solid_status_color


class SummaryCard(QFrame):
    def __init__(
        self,
        title: str,
        value: str = "--",
        icon: str | None = None,
        accent: str | None = None,
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(92)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Optional left accent bar in a semantic colour.
        if accent:
            accent_label = QLabel()
            accent_label.setProperty("cardAccent", True)
            accent_label.setStyleSheet(
                f"background: {solid_status_color(accent)};"
            )
            layout.addWidget(accent_label)

        # Optional icon.
        if icon:
            icon_label = QLabel(icon)
            icon_label.setProperty("cardIcon", True)
            layout.addWidget(icon_label)

        text_box = QVBoxLayout()
        text_box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setProperty("cardTitle", True)
        text_box.addWidget(title_label)

        self.value_label = QLabel(value)
        self.value_label.setProperty("cardValue", True)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        text_box.addWidget(self.value_label)

        self.subtext_label = QLabel("")
        self.subtext_label.setProperty("cardSubtext", True)
        self.subtext_label.setWordWrap(True)
        text_box.addWidget(self.subtext_label)

        layout.addLayout(text_box, 1)

    def set_value(self, value: str | int) -> None:
        self.value_label.setText(str(value))

    def set_subtext(self, text: str) -> None:
        self.subtext_label.setText(text)