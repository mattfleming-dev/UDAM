from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_METRIC_LABELS: list[tuple[str, str]] = [
    ("sharpness", "Sharpness"),
    ("contrast", "Contrast"),
    ("exposure", "Exposure"),
    ("noise_level", "Noise"),
    ("dynamic_range", "Dynamic Range"),
    ("edge_density", "Edge Density"),
    ("color_cast_deviation", "Color Cast"),
]


class QualityView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self._path: str = ""

        self.score_label = QLabel("No image selected")
        root.addWidget(self.score_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(3)
        self._bars: dict[str, QProgressBar] = {}
        for key, label in _METRIC_LABELS:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(True)
            bar.setFormat("%v")
            bar.setFixedHeight(14)
            bar.setValue(0)
            self._bars[key] = bar
            form.addRow(label, bar)
        root.addLayout(form)

        self.analyze_btn = QPushButton("Analyze This Image")
        root.addWidget(self.analyze_btn)

        batch_row = QHBoxLayout()
        self.analyze_unanalyzed = QPushButton("Unanalyzed")
        self.reanalyze_all = QPushButton("Re-analyze All")
        self.ai_tag_unanalyzed = QPushButton("AI Tag Unanalyzed")
        batch_row.addWidget(self.analyze_unanalyzed)
        batch_row.addWidget(self.reanalyze_all)
        root.addLayout(batch_row)
        root.addWidget(self.ai_tag_unanalyzed)

    def set_quality(self, path: str, score: float | None, metrics: dict[str, object]) -> None:
        self._path = path
        if score is None:
            self.score_label.setText("Not yet analyzed")
            for bar in self._bars.values():
                bar.setValue(0)
        else:
            self.score_label.setText(f"Overall: {score:.1f} / 100")
            for key, bar in self._bars.items():
                val = metrics.get(key)
                bar.setValue(int(float(val)) if val is not None else 0)

    # kept as no-ops — library-wide stats are no longer shown here
    def set_histogram_bins(self, bins: list[int]) -> None:
        pass

    def set_categories(self, payload: dict) -> None:
        pass
