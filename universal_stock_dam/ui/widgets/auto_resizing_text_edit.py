from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QTextEdit


class AutoResizingTextEdit(QTextEdit):
    """A QTextEdit that grows to fit its content instead of showing its own
    vertical scrollbar. Intended for use inside a scrollable parent panel
    (e.g. a CollapsibleSection within a QScrollArea), so overflow is handled
    by the outer scroll area rather than a nested scrollbar.
    """

    def __init__(self, parent=None, min_height: int = 60, max_height: int = 800) -> None:
        super().__init__(parent)
        self._min_height = min_height
        self._max_height = max_height
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.WidgetWidth)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self._min_height)
        self.document().documentLayout().documentSizeChanged.connect(self._resize_to_content)
        self._resize_to_content()

    def _resize_to_content(self, *_args) -> None:
        margins = self.contentsMargins()
        frame = self.frameWidth() * 2
        content_height = int(self.document().size().height())
        target = content_height + margins.top() + margins.bottom() + frame + 8
        target = max(self._min_height, min(target, self._max_height))
        self.setFixedHeight(target)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._resize_to_content()
