"""Read-only date field that opens a polished calendar popup on click.

Extends :class:`QDateEdit` so that clicking anywhere on the field opens the
calendar instead of allowing direct keyboard entry. The date value itself is
still settable programmatically (e.g. when loading a booking for editing).
"""

from __future__ import annotations

from datetime import date as date_type

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QDateEdit

from app.ui.widgets.calendar_popup import CalendarPopup


class _CalendarClickFilter(QObject):
    """Swallow typing and open the calendar when the field is clicked.

    Clicks inside the field land on the internal QLineEdit, not on the
    QDateEdit itself, so the filter forwards them to open the popup.
    """

    def __init__(self, date_edit: "CalendarDateEdit") -> None:
        super().__init__(date_edit)
        self._date_edit = date_edit

    def eventFilter(self, obj, event):  # noqa: ANN001
        if event.type() in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return True
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._date_edit.open_calendar_popup()
                event.accept()
                return True
        return False


class CalendarDateEdit(QDateEdit):
    """A :class:`QDateEdit` that shows a calendar when clicked anywhere."""

    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.setCalendarPopup(True)
        self._click_filter = _CalendarClickFilter(self)
        self.lineEdit().installEventFilter(self._click_filter)
        self._popup: CalendarPopup | None = None

    def _ensure_popup(self) -> CalendarPopup:
        if self._popup is None:
            self._popup = CalendarPopup(self)
            self._popup.date_selected.connect(self._on_popup_date_selected)
        return self._popup

    def _on_popup_date_selected(self, value: date_type) -> None:
        qdate = self.dateFromText(value.isoformat())
        self.setDate(qdate)

    def open_calendar_popup(self) -> None:
        """Open the calendar popup below the field."""
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()
            return
        popup = self._ensure_popup()
        qdate = self.date()
        popup.set_selected_date(date_type(qdate.year(), qdate.month(), qdate.day()))
        popup.show_below(self)

    def dateFromText(self, text: str):  # noqa: ANN201
        from PySide6.QtCore import QDate

        return QDate.fromString(text, "yyyy-MM-dd")

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_calendar_popup()
            event.accept()
            return
        super().mousePressEvent(event)
