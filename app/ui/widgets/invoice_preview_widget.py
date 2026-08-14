"""Shared invoice preview widget.

Renders the same render model used by the ReportLab PDF generator, so the
on-screen preview and the printed document always match. The widget is
read-only — actions (finalize, print, ...) are handled by the surrounding
dialog.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.constants import APP_NAME


class InvoicePreviewWidget(QWidget):
    """Read-only invoice preview mirroring the printed layout."""

    def __init__(self, render: dict, parent: QWidget | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.render = render
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------ ui

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- hotel header ------------------------------------------------
        header = QHBoxLayout()
        self.logo_label = QLabel()
        header.addWidget(self.logo_label, 0)

        hotel_box = QVBoxLayout()
        hotel_box.setSpacing(1)
        self.hotel_name = self._label("hotelName", 19)
        hotel_box.addWidget(self.hotel_name)
        self.hotel_desc = self._label("hotelDesc", 9.5)
        hotel_box.addWidget(self.hotel_desc)
        self.hotel_address = self._label("hotelLine", 9)
        hotel_box.addWidget(self.hotel_address)
        self.hotel_contact = self._label("hotelLine", 9)
        hotel_box.addWidget(self.hotel_contact)
        header.addLayout(hotel_box, 1)
        layout.addLayout(header)

        self.rule = QFrame()
        self.rule.setFrameShape(QFrame.Shape.HLine)
        self.rule.setStyleSheet("color: #334155; background: #334155; height: 1px;")
        layout.addWidget(self.rule)

        # --- title + invoice numbers --------------------------------------
        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.title_label = QLabel("INVOICE")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #0f172a;")
        title_box.addWidget(self.title_label)
        title_row.addLayout(title_box)
        title_row.addStretch(1)
        meta_box = QGridLayout()
        meta_box.setHorizontalSpacing(12)
        self.invoice_number_value = self._meta_label(meta_box, 0, "Invoice No:")
        self.invoice_date_value = self._meta_label(meta_box, 1, "Invoice Date:")
        self.invoice_status_value = self._meta_label(meta_box, 2, "Invoice Status:")
        title_row.addLayout(meta_box)
        layout.addLayout(title_row)

        self.rule2 = QFrame()
        self.rule2.setFrameShape(QFrame.Shape.HLine)
        self.rule2.setStyleSheet("color: #334155; background: #334155; height: 1px;")
        layout.addWidget(self.rule2)

        # --- billing details ----------------------------------------------
        layout.addWidget(self._section("Billing Details"))
        self.details_card = QFrame()
        self.details_card.setObjectName("DetailsCard")
        self.details_grid = QGridLayout(self.details_card)
        self.details_grid.setContentsMargins(14, 10, 14, 10)
        self.details_grid.setHorizontalSpacing(30)
        self.details_grid.setVerticalSpacing(4)
        layout.addWidget(self.details_card)

        # --- charges table ------------------------------------------------
        layout.addWidget(self._section("Charges"))
        self.charges_table = QTableWidget(0, 4)
        self.charges_table.setHorizontalHeaderLabels(["Description", "Qty", "Rate", "Amount"])
        self.charges_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.charges_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.charges_table.verticalHeader().setVisible(False)
        header_view = self.charges_table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.charges_table)

        # --- totals -------------------------------------------------------
        totals_row = QHBoxLayout()
        totals_row.addStretch(1)
        self.totals_box = QVBoxLayout()
        self.totals_box.setSpacing(2)
        totals_row.addLayout(self.totals_box)
        layout.addLayout(totals_row)

        # --- payment information ------------------------------------------
        self.payment_card = QFrame()
        self.payment_card.setObjectName("DetailsCard")
        self.payment_layout = QVBoxLayout(self.payment_card)
        self.payment_layout.setContentsMargins(14, 10, 14, 10)
        self.payment_layout.setSpacing(2)
        self.payment_card.hide()
        layout.addWidget(self.payment_card)

        # --- footer -------------------------------------------------------
        layout.addStretch(1)
        self.footer_message = QLabel()
        self.footer_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_message.setWordWrap(True)
        self.footer_message.setStyleSheet("font-size: 10px; color: #0f172a; margin-top: 8px;")
        layout.addWidget(self.footer_message)

        self.terms_label = QLabel()
        self.terms_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.terms_label.setWordWrap(True)
        self.terms_label.setProperty("detailLabel", True)
        layout.addWidget(self.terms_label)

        layout.addSpacing(24)
        self.sig_row = QHBoxLayout()
        self.guest_sig = self._label("sig", 9.5)
        self.receptionist_sig = self._label("sig", 9.5)
        self.sig_row.addWidget(self.guest_sig)
        self.sig_row.addWidget(self.receptionist_sig)
        layout.addLayout(self.sig_row)

    def _label(self, name: str, size: float) -> QLabel:
        label = QLabel()
        label.setStyleSheet(f"font-size: {size}px; color: #0f172a;")
        label.setWordWrap(True)
        return label

    def _meta_label(self, grid: QGridLayout, row: int, title: str) -> QLabel:
        title_label = QLabel(title)
        title_label.setProperty("detailLabel", True)
        grid.addWidget(title_label, row, 0)
        value = QLabel("—")
        value.setProperty("detailValue", True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(value, row, 1)
        return value

    def _section(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionHeading")
        label.setStyleSheet("color: #2563eb;")
        return label

    def _detail(self, row: int, col: int, title: str, value: str) -> None:
        title_label = QLabel(title)
        title_label.setProperty("detailLabel", True)
        self.details_grid.addWidget(title_label, row, col * 2)
        value_label = QLabel(value or "—")
        value_label.setProperty("detailValue", True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(True)
        self.details_grid.addWidget(value_label, row, col * 2 + 1)

    def _total_row(self, title: str, value: str, bold: bool = False, rule: bool = False) -> None:
        row = QHBoxLayout()
        row.setSpacing(24)
        label = QLabel(title)
        label.setStyleSheet(
            "font-size: 10px; font-weight: 600;" if bold else "font-size: 10px; color: #0f172a;"
        )
        value_label = QLabel(value)
        value_label.setStyleSheet(
            "font-size: 10px; font-weight: 600;" if bold else "font-size: 10px; color: #0f172a;"
        )
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(label)
        row.addWidget(value_label)
        if rule:
            frame = QFrame()
            frame.setFrameShape(QFrame.Shape.HLine)
            frame.setStyleSheet("color: #cbd5e1; background: #cbd5e1; height: 1px;")
            row.addWidget(frame, 1)
        self.totals_box.addLayout(row)

    # ---------------------------------------------------------------- data

    def _populate(self) -> None:
        render = self.render
        hotel_name = render["hotel_name"] or APP_NAME

        # Logo (text header used when there is no usable logo — never broken).
        logo_shown = self._load_logo(render.get("logo_path"))
        if logo_shown:
            self.logo_label.show()
        else:
            self.logo_label.hide()

        self.hotel_name.setText(hotel_name)
        if render["hotel_description"]:
            self.hotel_desc.setText(render["hotel_description"])
            self.hotel_desc.show()
        else:
            self.hotel_desc.hide()

        address_lines = render["hotel_address_lines"] or []
        address_text = "\n".join(address_lines)
        self.hotel_address.setText(address_text)
        self.hotel_address.setVisible(bool(address_text))

        contact_parts = []
        if render["hotel_phone"]:
            contact_parts.append(f"Phone: {render['hotel_phone']}")
        if render["hotel_email"]:
            contact_parts.append(f"Email: {render['hotel_email']}")
        self.hotel_contact.setText("\n".join(contact_parts))
        self.hotel_contact.setVisible(bool(contact_parts))

        self.invoice_number_value.setText(render["invoice_number"])
        self.invoice_date_value.setText(render["invoice_date"])
        self.invoice_status_value.setText(render["invoice_status_label"])

        # Billing details.
        guest_rows = [
            ("Guest", render["guest_name"]),
            ("Mobile", render["guest_mobile"]),
            ("Address", render["guest_address"]),
        ]
        stay_rows = [
            ("Room", render["room_number"]),
            ("Room Type", render["room_type"]),
            ("Booking Source", render["booking_source"]),
            ("Check-in", render["check_in"]),
            ("Check-out", render["check_out"]),
            ("Nights", str(render["nights"])),
        ]
        for row, (title, value) in enumerate(guest_rows):
            self._detail(row, 0, title, value)
        for row, (title, value) in enumerate(stay_rows):
            self._detail(row, 1, title, value)

        # Charges.
        self.charges_table.setRowCount(0)
        for row_index, item in enumerate(render["line_items"]):
            self.charges_table.insertRow(row_index)
            values = [
                item["description"],
                str(item["quantity"]),
                str(item["unit_amount"]),
                str(item["amount"]),
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col > 0:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.charges_table.setItem(row_index, col, cell)

        # Totals.
        self._total_row("Subtotal", render["subtotal"])
        if render["discount"] is not None:
            self._total_row("Discount", render["discount"])
        self._total_row("Grand Total", render["grand_total"], bold=True, rule=True)
        self._total_row("Paid", render["total_paid"])
        self._total_row("Remaining", render["remaining"], bold=True)
        self._total_row("Payment Status", render["payment_status_label"], bold=True)

        # Payments.
        self._populate_payments(render["payments"])

        self.footer_message.setText(render["footer_message"])
        self.terms_label.setText(render["terms"])
        self.terms_label.setVisible(bool(render["terms"]))

        self.guest_sig.setText("Guest Signature: ____________________")
        self.receptionist_sig.setText("Receptionist: ______________________")

    def _populate_payments(self, payments: list) -> None:  # noqa: ANN001
        if not payments:
            self.payment_card.hide()
            return
        while self.payment_layout.count():
            item = self.payment_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        heading = QLabel("Payment Information")
        heading.setObjectName("SectionHeading")
        heading.setStyleSheet("color: #2563eb;")
        self.payment_layout.addWidget(heading)

        if len(payments) == 1:
            payment = payments[0]
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            rows = [
                ("Payment Method", payment["method"]),
                ("Amount", payment["amount"]),
            ]
            if payment["reference"]:
                rows.append(("Reference No.", payment["reference"]))
            for row_index, (title, value) in enumerate(rows):
                label = QLabel(title)
                label.setProperty("detailLabel", True)
                grid.addWidget(label, row_index, 0)
                value_label = QLabel(value)
                value_label.setProperty("detailValue", True)
                grid.addWidget(value_label, row_index, 1)
            self.payment_layout.addLayout(grid)
        else:
            summary_label = QLabel("Payment Summary")
            summary_label.setProperty("detailLabel", True)
            self.payment_layout.addWidget(summary_label)
            for payment in payments:
                line = f"{payment['date']} — {payment['method']} — {payment['amount']}"
                if payment["reference"]:
                    line += f" — Ref: {payment['reference']}"
                item_label = QLabel(line)
                item_label.setProperty("detailValue", True)
                item_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                self.payment_layout.addWidget(item_label)
        self.payment_card.show()

    def _load_logo(self, logo_path: str | None) -> bool:
        if not logo_path:
            return False
        path = Path(logo_path)
        if not path.exists():
            return False
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return False
        self.logo_label.setPixmap(pixmap.scaledToHeight(72, Qt.TransformationMode.SmoothTransformation))
        return True
