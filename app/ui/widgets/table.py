"""Shared table helpers: consistent setup and status badge cells.

Centralizes the common QTableWidget configuration used by every page so
tables look identical, read comfortably and never rely on colour alone.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from app.ui.styles import status_tint


def configure_table(
    table: QTableWidget,
    headers: list[str],
    *,
    stretch: bool = True,
    resize_to_contents_cols: list[int] | None = None,
    row_height: int = 38,
) -> QTableWidget:
    """Apply the standard, readable table configuration."""
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setHighlightSections(False)
    if stretch:
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    for col in resize_to_contents_cols or []:
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    return table


def status_item(text: str, status: str) -> QTableWidgetItem:
    """A readable status cell: dark text on a soft tint background."""
    background, foreground = status_tint(status)
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setBackground(QColor(background))
    item.setForeground(QColor(foreground))
    font = item.font()
    font.setBold(True)
    font.setPointSize(12)
    item.setFont(font)
    return item


def money_item(text: str) -> QTableWidgetItem:
    """Right-aligned, bold money cell for easy scanning."""
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    font = item.font()
    font.setBold(True)
    item.setFont(font)
    return item