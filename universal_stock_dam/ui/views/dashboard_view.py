from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from universal_stock_dam.ui.widgets.quality_histogram_widget import QualityHistogramWidget


class DashboardView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        cards = QGridLayout()

        self.total_images_card, self.total_images_value = self._metric_card("Total Images", "0")
        self.avg_quality_card, self.avg_quality_value = self._metric_card("Avg Quality", "0.0")
        self.analyzed_card, self.analyzed_value = self._metric_card("Analyzed %", "0%")
        self.storage_card, self.storage_value = self._metric_card("Storage", "0 MB")

        cards.addWidget(self.total_images_card, 0, 0)
        cards.addWidget(self.avg_quality_card, 0, 1)
        cards.addWidget(self.analyzed_card, 0, 2)
        cards.addWidget(self.storage_card, 0, 3)

        root.addLayout(cards)

        self.histogram = QualityHistogramWidget()
        root.addWidget(self.histogram)

        self.activity = QListWidget()
        self.activity.addItems(["Application initialized", "Ready for catalog scan"])
        root.addWidget(self.activity)

        self.quick_button = QPushButton("Analyze Unanalyzed")
        root.addWidget(self.quick_button)

        self.ai_quick_button = QPushButton("AI Tag Unanalyzed")
        root.addWidget(self.ai_quick_button)

    def _metric_card(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel(title))
        value_label = QLabel(value)
        layout.addWidget(value_label)
        return card, value_label

    def set_metrics(self, *, total_images: int, avg_quality: float, analyzed_pct: float, storage_mb: float) -> None:
        self.total_images_value.setText(str(total_images))
        self.avg_quality_value.setText(f"{avg_quality:.2f}")
        self.analyzed_value.setText(f"{analyzed_pct:.1f}%")
        self.storage_value.setText(f"{storage_mb:.2f} MB")

    def set_histogram_bins(self, bins: list[int]) -> None:
        self.histogram.set_bins(bins)

    def add_activity(self, message: str) -> None:
        self.activity.insertItem(0, message)
