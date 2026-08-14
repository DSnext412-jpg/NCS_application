"""Top header bar: greeting, global search and the current date."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.core.constants import APP_NAME


def greeting_for(hour: int | None = None) -> str:
    hour = datetime.now().hour if hour is None else hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


class TopHeader(QWidget):
    search_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TopHeader")
        self.setFixedHeight(72)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(16)

        # --- greeting (left) -------------------------------------------
        greeting_box = QVBoxLayout()
        greeting_box.setSpacing(1)
        greeting_label = QLabel(f"{greeting_for()}, Reception!")
        greeting_label.setObjectName("HeaderGreeting")
        greeting_box.addWidget(greeting_label)
        subtitle = QLabel(f"Welcome back to {APP_NAME}")
        subtitle.setObjectName("HeaderSubtitle")
        greeting_box.addWidget(subtitle)
        layout.addLayout(greeting_box)
        layout.addStretch(1)

        # --- search (middle-right) ---------------------------------------
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("HeaderSearch")
        self.search_edit.setPlaceholderText("Search booking, guest, mobile, room...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(300)
        self.search_edit.returnPressed.connect(self._on_search)
        layout.addWidget(self.search_edit)

        # --- date (right) ------------------------------------------------
        now = datetime.now()
        date_box = QVBoxLayout()
        date_box.setSpacing(1)
        date_label = QLabel(now.strftime("%d %b %Y"))
        date_label.setObjectName("HeaderDate")
        date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        date_box.addWidget(date_label)
        weekday_label = QLabel(now.strftime("%A"))
        weekday_label.setObjectName("HeaderDateSub")
        weekday_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        date_box.addWidget(weekday_label)
        layout.addLayout(date_box)

    def _on_search(self) -> None:
        query = self.search_edit.text().strip()
        self.search_edit.clear()
        self.search_requested.emit(query)