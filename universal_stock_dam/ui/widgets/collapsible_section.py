from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QPushButton, QWidget


class CollapsibleSection(QWidget):
    """Lightroom-style accordion section with a toggle header."""

    def __init__(self, title: str, collapsed: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._title = title
        self._collapsed = collapsed

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toggle_btn = QPushButton(self._header_text())
        self._toggle_btn.setObjectName("CollapsibleHeader")
        self._toggle_btn.setCheckable(False)
        self._toggle_btn.setCursor(Qt.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle)
        outer.addWidget(self._toggle_btn)

        self._content = QWidget()
        self._content.setObjectName("CollapsibleContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 2, 0, 4)
        self._content_layout.setSpacing(2)
        self._content.setVisible(not self._collapsed)
        outer.addWidget(self._content)

    def add_widget(self, widget: QWidget) -> None:
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._content_layout.addWidget(widget)

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self._content.setVisible(not self._collapsed)
        self._toggle_btn.setText(self._header_text())

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)

    def _header_text(self) -> str:
        arrow = "▶" if self._collapsed else "▼"
        return f"  {arrow}  {self._title}"
