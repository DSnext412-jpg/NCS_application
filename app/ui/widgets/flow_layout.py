"""A Qt flow layout: children wrap to new lines when space runs out.

Adapted from the classic Qt FlowLayout example. Used for the room grid so
cards rearrange sensibly when the window is resized.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QSizePolicy


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, h_spacing: int = 12, v_spacing: int = 12) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._item_list: list = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:  # noqa: ANN001
        self._item_list.append(item)

    def count(self) -> int:
        return len(self._item_list)

    def itemAt(self, index: int):  # noqa: ANN201
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int):  # noqa: ANN201
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: ANN001
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        x = rect.x() + margins.left()
        y = rect.y() + margins.top()
        line_height = 0
        right = rect.right() - margins.right()

        for item in self._item_list:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if next_x - self._h_space > right and line_height > 0:
                x = rect.x() + margins.left()
                y += line_height + self._v_space
                next_x = x + hint.width() + self._h_space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()
