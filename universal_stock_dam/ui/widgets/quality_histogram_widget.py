from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class QualityHistogramWidget(QWidget):
    def __init__(self, bins: list[int] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.bins = bins or [0] * 10
        self.setMinimumHeight(140)

    def set_bins(self, bins: list[int]) -> None:
        self.bins = bins
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor("#1b2028"))

        if not self.bins:
            return

        max_count = max(self.bins) if max(self.bins) > 0 else 1
        bar_width = max(1, rect.width() // len(self.bins))

        for i, count in enumerate(self.bins):
            h = int((count / max_count) * (rect.height() - 18))
            x = rect.left() + i * bar_width + 2
            y = rect.bottom() - h
            painter.fillRect(x, y, bar_width - 4, h, QColor("#4da3ff"))

        painter.setPen(QColor("#a8b3c2"))
        painter.drawText(rect.adjusted(0, 0, -4, -4), Qt.AlignBottom | Qt.AlignRight, "Quality Distribution")
