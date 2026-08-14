"""Invoice dialog.

Shows the shared invoice preview and offers status-appropriate actions:
* DRAFT      -> [Back] [Cancel Invoice] [Finalize Invoice]
* FINALIZED  -> [Print] [Open PDF] [Re-generate PDF] [Close]
* CANCELLED  -> [Open PDF] [Re-generate PDF] [Close]

Finalized invoices are never edited here — only viewed, printed and
regenerated from their frozen snapshot.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import InvoiceStatus
from app.core.paths import Paths
from app.database.database import Database
from app.services import invoice_service
from app.ui.widgets.invoice_preview_widget import InvoicePreviewWidget

logger = logging.getLogger(__name__)


class InvoiceDialog(QDialog):
    def __init__(
        self,
        database: Database,
        invoice_id: int,
        on_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.invoice_id = invoice_id
        self.on_changed = on_changed
        self.invoice_dir = Paths().invoices_dir

        self.setWindowTitle("Invoice")
        self.setModal(True)
        self.setMinimumSize(720, 560)

        self._build_ui()
        self._load()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        self.invoice_number_label = QLabel()
        self.invoice_number_label.setObjectName("DialogRoomNumber")
        layout.addWidget(self.invoice_number_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.preview_container)
        layout.addWidget(scroll, 1)

        self.action_row = QHBoxLayout()
        self.action_row.addStretch(1)
        layout.addLayout(self.action_row)

    def _clear_actions(self) -> None:
        while self.action_row.count():
            item = self.action_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_button(self, text: str, callback: Callable[[], None], primary: bool = False) -> None:
        button = QPushButton(text)
        button.setObjectName("ActionButton" if primary else "SecondaryButton")
        button.clicked.connect(callback)
        self.action_row.addWidget(button)
        return button

    # ---------------------------------------------------------------- load

    def _load(self) -> None:
        with self.database.session_scope() as session:
            invoice = invoice_service.get_invoice(session, self.invoice_id)
            if invoice is None:
                QMessageBox.critical(self, "Error", "Invoice not found.")
                self.reject()
                return
            self.invoice = invoice
            render = invoice_service.build_render_model(invoice)

        self.invoice_number_label.setText(f"{invoice.invoice_number}")
        while self.preview_layout.count():
            item = self.preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.preview_layout.addWidget(InvoicePreviewWidget(render))

        self._build_actions()
        self._notify()

    def _build_actions(self) -> None:
        self._clear_actions()
        status = self.invoice.status

        if status == InvoiceStatus.DRAFT.value:
            self._add_button("Back", self.reject)
            self._add_button("Cancel Invoice", self._cancel, primary=False)
            self._add_button("Finalize Invoice", self._finalize, primary=True)
        elif status == InvoiceStatus.FINALIZED.value:
            self._add_button("Print", self._print)
            self._add_button("Open PDF", self._open_pdf)
            self._add_button("Re-generate PDF", self._regenerate)
            self._add_button("Close", self.accept, primary=True)
        else:  # CANCELLED
            self._add_button("Open PDF", self._open_pdf)
            self._add_button("Re-generate PDF", self._regenerate)
            self._add_button("Close", self.accept, primary=True)

    # ------------------------------------------------------------- actions

    def _finalize(self) -> None:
        answer = QMessageBox.question(
            self,
            "Finalize Invoice",
            "Finalize this invoice?\n\nFinalized invoices should not be edited.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        try:
            with self.database.session_scope() as session:
                invoice_service.finalize_invoice(session, self.invoice_id, self.invoice_dir)
        except invoice_service.InvoiceError as exc:
            QMessageBox.warning(self, "Cannot Finalize", str(exc))
            return
        except Exception:
            logger.exception("Invoice finalization failed")
            QMessageBox.critical(self, "Error", "Could not finalize the invoice. See logs for details.")
            return
        self._load()
        QMessageBox.information(
            self,
            "Invoice Finalized",
            f"Invoice {self.invoice.invoice_number} has been finalized and its PDF saved.",
        )

    def _cancel(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Cancel Invoice")
        box.setText("Cancel Invoice?")
        box.setInformativeText(
            "This invoice will be marked as cancelled.\n"
            "The invoice record will remain in history."
        )
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        keep_button = box.addButton("Keep Invoice", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(keep_button)
        box.exec()
        if box.clickedButton() != cancel_button:
            return
        try:
            with self.database.session_scope() as session:
                invoice_service.cancel_invoice(session, self.invoice_id)
        except invoice_service.InvoiceError as exc:
            QMessageBox.warning(self, "Cannot Cancel", str(exc))
            return
        except Exception:
            logger.exception("Invoice cancellation failed")
            QMessageBox.critical(self, "Error", "Could not cancel the invoice. See logs for details.")
            return
        self._load()
        QMessageBox.information(
            self,
            "Invoice Cancelled",
            f"Invoice {self.invoice.invoice_number} has been cancelled.\n\n"
            "The record remains in history for reference.",
        )

    def _pdf_path(self) -> Path | None:
        path = self.invoice.pdf_path
        if path and Path(path).exists():
            return Path(path)
        return None

    def _ensure_pdf(self) -> Path | None:
        """Return the PDF path, regenerating from the snapshot if missing."""
        existing = self._pdf_path()
        if existing is not None:
            return existing
        try:
            with self.database.session_scope() as session:
                path = invoice_service.regenerate_pdf(session, self.invoice_id, self.invoice_dir)
            self._load()
            return Path(path)
        except Exception:
            logger.exception("PDF regeneration failed")
            QMessageBox.critical(self, "Error", "Could not generate the PDF. See logs for details.")
            return None

    def _open_pdf(self) -> None:
        path = self._ensure_pdf()
        if path is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _print(self) -> None:
        path = self._ensure_pdf()
        if path is None:
            return
        try:
            os.startfile(str(path), "print")  # noqa: S606 - Windows print verb
        except OSError:
            logger.warning("Printing not available for %s", path)
            QMessageBox.warning(
                self,
                "Printing Unavailable",
                "The system could not start printing for this invoice.\n\n"
                "Open the PDF and print it manually instead.",
            )

    def _regenerate(self) -> None:
        try:
            with self.database.session_scope() as session:
                path = invoice_service.regenerate_pdf(session, self.invoice_id, self.invoice_dir)
        except Exception:
            logger.exception("PDF regeneration failed")
            QMessageBox.critical(self, "Error", "Could not generate the PDF. See logs for details.")
            return
        self._load()
        answer = QMessageBox.question(
            self,
            "PDF Generated",
            f"The PDF was regenerated from the stored invoice data.\n\n"
            f"{path}\n\nOpen it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _notify(self) -> None:
        if self.on_changed is not None:
            self.on_changed()
