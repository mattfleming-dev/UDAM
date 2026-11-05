from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QLabel,
    QComboBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)


class FilterSidebarWidget(QFrame):
    filters_changed = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)

        title = QLabel("Filters")
        root.addWidget(title)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.min_quality = QSpinBox()
        self.min_quality.setRange(0, 100)
        self.min_quality.setValue(0)

        self.max_quality = QSpinBox()
        self.max_quality.setRange(0, 100)
        self.max_quality.setValue(100)

        form.addRow("Min quality", self.min_quality)
        form.addRow("Max quality", self.max_quality)
        root.addLayout(form)

        self.jpg_cb = QCheckBox("JPEG")
        self.raw_cb = QCheckBox("RAW")
        self.png_cb = QCheckBox("PNG")
        for cb in (self.jpg_cb, self.raw_cb, self.png_cb):
            cb.setChecked(True)
            root.addWidget(cb)

        self.favorite_only = QCheckBox("Favorites only")
        self.recommended_only = QCheckBox("Recommended only")
        root.addWidget(self.favorite_only)
        root.addWidget(self.recommended_only)

        advanced = QFormLayout()
        advanced.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.tag_query = QLineEdit()
        self.camera_query = QLineEdit()
        self.lens_query = QLineEdit()
        self.collection_combo = QComboBox()
        self.collection_combo.addItem("All collections", None)
        advanced.addRow("Tags", self.tag_query)
        advanced.addRow("Collection", self.collection_combo)
        advanced.addRow("Camera", self.camera_query)
        advanced.addRow("Lens", self.lens_query)
        root.addLayout(advanced)

        for widget in (
            self.min_quality,
            self.max_quality,
            self.jpg_cb,
            self.raw_cb,
            self.png_cb,
            self.favorite_only,
            self.recommended_only,
            self.tag_query,
            self.camera_query,
            self.lens_query,
            self.collection_combo,
        ):
            if isinstance(widget, QSpinBox):
                widget.valueChanged.connect(self._emit_filters)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._emit_filters)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._emit_filters)
            else:
                widget.toggled.connect(self._emit_filters)

    def set_collection_options(self, collections: list[dict[str, object]]) -> None:
        current_value = self.collection_combo.currentData()
        self.collection_combo.blockSignals(True)
        self.collection_combo.clear()
        self.collection_combo.addItem("All collections", None)
        for collection in collections:
            self.collection_combo.addItem(str(collection.get("name", "Unnamed")), int(collection.get("id", 0)))
        if current_value is not None and self.collection_combo.findData(current_value) >= 0:
            self.collection_combo.setCurrentIndex(self.collection_combo.findData(current_value))
        self.collection_combo.blockSignals(False)

    def _emit_filters(self) -> None:
        self.filters_changed.emit(
            {
                "min_quality": int(self.min_quality.value()),
                "max_quality": int(self.max_quality.value()),
                "formats": {
                    "jpg": self.jpg_cb.isChecked(),
                    "raw": self.raw_cb.isChecked(),
                    "png": self.png_cb.isChecked(),
                },
                "favorite_only": self.favorite_only.isChecked(),
                "recommended_only": self.recommended_only.isChecked(),
                "tag_query": self.tag_query.text().strip(),
                "collection_id": self.collection_combo.currentData(),
                "camera_query": self.camera_query.text().strip(),
                "lens_query": self.lens_query.text().strip(),
            }
        )
