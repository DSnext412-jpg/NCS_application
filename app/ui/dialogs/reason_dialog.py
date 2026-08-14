"""Small dialog that prompts for a reason (cancellation / no-show)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.core.constants import CANCELLATION_REASONS


class ReasonPromptDialog(QDialog):
    def __init__(self, title: str, message: str, require_reason: bool = True, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.require_reason = require_reason

        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        text = QLabel(message)
        text.setWordWrap(True)
        layout.addWidget(text)

        self.reason_combo = QComboBox()
        self.reason_combo.addItem("", "")
        for reason in CANCELLATION_REASONS:
            self.reason_combo.addItem(reason, reason)
        self.reason_combo.addItem("(manual reason below)", "__manual__")
        self.reason_combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self.reason_combo)

        self.manual_edit = QLineEdit()
        self.manual_edit.setPlaceholderText("Type reason...")
        self.manual_edit.setEnabled(False)
        layout.addWidget(self.manual_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_combo_changed(self) -> None:
        is_manual = self.reason_combo.currentData() == "__manual__"
        self.manual_edit.setEnabled(is_manual)
        if is_manual:
            self.manual_edit.setFocus()

    def _accept(self) -> None:
        reason = self.reason()
        if self.require_reason and not reason:
            QMessageBox.warning(self, "Reason Required", "Please provide a reason.")
            return
        self.accept()

    def reason(self) -> str:
        selected = self.reason_combo.currentData()
        if selected == "__manual__":
            return self.manual_edit.text().strip()
        return selected or ""
