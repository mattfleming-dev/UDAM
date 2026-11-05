from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from universal_stock_dam.core.raw_loader import is_raw_format


class ThumbnailCardWidget(QFrame):
    def __init__(
        self,
        image_path: str,
        title: str,
        quality_score: float | None = None,
        is_favorite: bool = False,
        flags: list[str] | None = None,
        preview_pixmap: QPixmap | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        thumb = QLabel()
        thumb.setMinimumHeight(120)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        if preview_pixmap is not None and not preview_pixmap.isNull():
            thumb.setPixmap(preview_pixmap)
        else:
            p = Path(image_path)
            if p.exists():
                if is_raw_format(p):
                    thumb.setText("RAW Preview Unavailable")
                else:
                    pixmap = QPixmap(str(p))
                    if not pixmap.isNull():
                        thumb.setPixmap(pixmap.scaled(220, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    else:
                        thumb.setText("No Preview")
            else:
                thumb.setText("No Preview")

        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        quality_text = "-" if quality_score is None else f"{quality_score:.1f}"
        quality_label = QLabel(f"Quality: {quality_text}")
        quality_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        favorite_label = QLabel("Favorite" if is_favorite else "")
        favorite_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        flags_label = QLabel(", ".join(flags or []))
        flags_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout.addWidget(thumb)
        layout.addWidget(title_label)
        layout.addWidget(quality_label)
        layout.addWidget(favorite_label)
        layout.addWidget(flags_label)
