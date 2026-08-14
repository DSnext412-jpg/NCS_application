"""Empty-state placeholder widget for lists and tables with no rows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self.setMinimumHeight(160)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        if icon:
            icon_label = QLabel(icon)
            icon_label.setProperty("emptyIcon", True)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setProperty("emptyTitle", True)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setProperty("emptySubtitle", True)
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setWordWrap(True)
            layout.addWidget(subtitle_label)