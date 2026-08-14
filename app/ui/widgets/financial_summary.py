"""Financial summary widget.

Shows the complete billing breakdown for a booking: derived charges,
manual charges, discount, GST and the payment status. The widget is
read-only; payments/charges are managed from the booking details dialog.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel

from app.core.constants import DEFAULT_CURRENCY
from app.ui.formatters import format_money
from app.ui.widgets.status_badge import make_status_badge


class FinancialSummaryWidget(QFrame):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setObjectName("DetailsCard")

        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(16, 12, 16, 12)
        self.grid.setHorizontalSpacing(24)
        self.grid.setVerticalSpacing(6)

        self.payment_badge = make_status_badge("unpaid", compact=True)
        self._rows: list[str] = []
        self._populate()

    # ------------------------------------------------------------------ ui

    def _add_row(self, row: int, title: str) -> QLabel:
        label = QLabel(title)
        label.setProperty("detailLabel", True)
        self.grid.addWidget(label, row, 0)
        value_label = QLabel()
        value_label.setProperty("detailValue", True)
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.grid.addWidget(value_label, row, 1)
        return value_label

    def _populate(self) -> None:
        # Row 0 is the payment status (badge spans the value column).
        title = QLabel("Payment Status")
        title.setProperty("detailLabel", True)
        self.grid.addWidget(title, 0, 0)
        self.grid.addWidget(self.payment_badge, 0, 1)

        rows = [
            "Nights",
            "Room Charges",
            "Extra Person",
            "Early Check-in",
            "Late Check-out",
            "Extra Mattress",
            "Miscellaneous",
            "Other Charges",
            "Subtotal",
            "Discount",
            "GST",
            "Grand Total",
            "Total Paid",
            "Balance",
        ]
        self._rows = []
        for i, key in enumerate(rows):
            label = QLabel(key)
            label.setProperty("detailLabel", True)
            if key in ("Grand Total", "Balance"):
                label.setStyleSheet("font-weight: 600;")
            self.grid.addWidget(label, i + 1, 0)
            value_label = QLabel("—")
            value_label.setProperty("detailValue", True)
            if key in ("Grand Total", "Balance"):
                value_label.setStyleSheet("font-weight: 600;")
            self.grid.addWidget(value_label, i + 1, 1)
            self._rows.append((key, value_label))

    # ---------------------------------------------------------------- data

    def load(self, summary) -> None:  # noqa: ANN001
        self.payment_badge.setText(summary.payment_status.label)
        self.payment_badge.setStyleSheet(
            make_status_badge(summary.payment_status.value, compact=True).styleSheet()
        )

        values = {
            "Nights": str(summary.nights),
            "Room Charges": format_money(summary.room_charges),
            "Extra Person": format_money(summary.extra_person_charges),
            "Early Check-in": format_money(summary.early_check_in_charges),
            "Late Check-out": format_money(summary.late_check_out_charges),
            "Extra Mattress": format_money(summary.mattress_charges),
            "Miscellaneous": format_money(summary.miscellaneous_charges),
            "Other Charges": format_money(summary.other_charges),
            "Subtotal": format_money(summary.subtotal),
            "Discount": format_money(summary.discount),
            "GST": format_money(summary.gst),
            "Grand Total": format_money(summary.grand_total),
            "Total Paid": format_money(summary.total_paid),
            "Balance": format_money(summary.remaining),
        }
        for key, label in self._rows:
            label.setText(values[key])

    @staticmethod
    def currency_symbol() -> str:
        return DEFAULT_CURRENCY
