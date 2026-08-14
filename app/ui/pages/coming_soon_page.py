"""Generic "Coming Soon" page shown for unimplemented sections."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ComingSoonPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addStretch(1)

        self.title_label = QLabel()
        self.title_label.setObjectName("ComingSoonTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        text = QLabel("This section is coming soon.")
        text.setObjectName("ComingSoonText")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)

        layout.addStretch(1)

    def set_section(self, label: str) -> None:
        self.title_label.setText(label)
