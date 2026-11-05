from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from universal_stock_dam.core.raw_loader import extract_preview_rgb, is_raw_format


class PreviewView(QWidget):
    """Full-resolution single-image preview that fills available space."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_path: str = ""
        self._full_pixmap: QPixmap | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Select an image from the filmstrip")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setObjectName("PreviewLabel")
        layout.addWidget(self._label, 1)

    def set_image(self, path: str) -> None:
        if path == self._current_path:
            return
        self._current_path = path

        if not path or not Path(path).exists():
            self._full_pixmap = None
            self._label.setPixmap(QPixmap())
            self._label.setText("No image")
            return

        pixmap = self._load_pixmap(path)
        if pixmap is None or pixmap.isNull():
            self._full_pixmap = None
            self._label.setPixmap(QPixmap())
            self._label.setText("Cannot load preview")
            return

        self._full_pixmap = pixmap
        self._label.setText("")
        self._fit_to_label()

    def clear(self) -> None:
        self._current_path = ""
        self._full_pixmap = None
        self._label.setPixmap(QPixmap())
        self._label.setText("Select an image from the filmstrip")

    def _load_pixmap(self, path: str) -> QPixmap | None:
        if is_raw_format(path):
            try:
                rgb: np.ndarray = extract_preview_rgb(path, half_size=False)
            except Exception:
                try:
                    rgb = extract_preview_rgb(path, half_size=True)
                except Exception:
                    return None
            if rgb.ndim == 3 and rgb.shape[2] >= 3:
                h, w = rgb.shape[:2]
                img = QImage(rgb.data, w, h, int(rgb.strides[0]), QImage.Format_RGB888)
                return QPixmap.fromImage(img.copy())
            return None
        pixmap = QPixmap(path)
        return pixmap if not pixmap.isNull() else None

    def _fit_to_label(self) -> None:
        if self._full_pixmap is None:
            return
        w = max(self._label.width(), 1)
        h = max(self._label.height(), 1)
        scaled = self._full_pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_to_label()
