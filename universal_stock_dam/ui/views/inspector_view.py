from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.ui.widgets.auto_resizing_text_edit import AutoResizingTextEdit


class InspectorView(QWidget):
    ai_generate_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_candidate_id: int | None = None
        self._tab_animations: list[QPropertyAnimation] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.filename = QLabel("No image selected")
        self.filename.setWordWrap(True)
        self.feedback = QLabel("")
        root.addWidget(self.filename)
        root.addWidget(self.feedback)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # ── Metadata & Quality tab ────────────────────────────────
        metadata_tab = QWidget()
        metadata_layout = QVBoxLayout(metadata_tab)
        metadata_layout.setContentsMargins(2, 2, 2, 2)
        metadata_layout.setSpacing(3)

        # Quality metrics
        self.score_label = QLabel("Quality: -")
        metadata_layout.addWidget(self.score_label)

        _METRIC_LABELS: list[tuple[str, str]] = [
            ("sharpness", "Sharpness"),
            ("contrast", "Contrast"),
            ("exposure", "Exposure"),
            ("noise_level", "Noise"),
            ("dynamic_range", "Dynamic Range"),
            ("edge_density", "Edge Density"),
            ("color_cast_deviation", "Color Cast"),
        ]

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(2)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
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
        metadata_layout.addLayout(form)

        # Analyze button
        self.analyze_btn = QPushButton("Analyze Image")
        self.analyze_btn.setMaximumHeight(28)
        metadata_layout.addWidget(self.analyze_btn)

        # EXIF data
        metadata_layout.addWidget(QLabel("Camera EXIF"))
        exif_form = QFormLayout()
        exif_form.setContentsMargins(0, 0, 0, 0)
        exif_form.setSpacing(2)
        exif_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.camera = QLabel("-")
        self.lens = QLabel("-")
        self.iso = QLabel("-")
        self.aperture = QLabel("-")
        self.focal_length = QLabel("-")
        self.shutter_speed = QLabel("-")
        self.camera.setWordWrap(True)
        self.lens.setWordWrap(True)
        for label, widget in (
            ("Camera", self.camera),
            ("Lens", self.lens),
            ("Focal Length", self.focal_length),
            ("Aperture", self.aperture),
            ("Shutter", self.shutter_speed),
            ("ISO", self.iso),
        ):
            exif_form.addRow(label, widget)
        metadata_layout.addLayout(exif_form)

        btn_row = QHBoxLayout()
        self.favorite_btn = QPushButton("Favorite")
        self.add_collection_btn = QPushButton("Collection")
        self.delete_btn = QPushButton("Delete")
        for b in (self.favorite_btn, self.add_collection_btn, self.delete_btn):
            btn_row.addWidget(b)
        metadata_layout.addLayout(btn_row)
        metadata_layout.addStretch(1)

        # AI metadata + stock metadata
        metadata_layout.addWidget(QLabel("AI Metadata"))
        ai_button_row = QHBoxLayout()
        self.ai_generate_btn = QPushButton("⚡  Generate with AI")
        self.ai_saved_badge = QLabel("AI saved")
        self.ai_saved_badge.setVisible(False)
        self.ai_saved_badge.setStyleSheet(
            "QLabel { background: #1f7a3e; color: white; border-radius: 6px; padding: 1px 6px; font-size: 10px; }"
        )
        ai_button_row.addWidget(self.ai_generate_btn)
        ai_button_row.addWidget(self.ai_saved_badge)
        ai_button_row.addStretch(1)
        metadata_layout.addLayout(ai_button_row)

        metadata_layout.addWidget(QLabel("Title"))
        self.title_edit = AutoResizingTextEdit(min_height=32, max_height=200)
        self.title_edit.setPlaceholderText("Title")
        metadata_layout.addWidget(self.title_edit)

        metadata_layout.addWidget(QLabel("Description"))
        self.description_edit = AutoResizingTextEdit(min_height=48, max_height=400)
        self.description_edit.setPlaceholderText("Description / caption")
        metadata_layout.addWidget(self.description_edit)

        metadata_layout.addWidget(QLabel("Keywords"))
        self.keywords_edit = AutoResizingTextEdit(min_height=32, max_height=300)
        self.keywords_edit.setPlaceholderText("Comma-separated keywords")
        metadata_layout.addWidget(self.keywords_edit)

        metadata_layout.addWidget(QLabel("Stock Site"))
        self.stock_site = QComboBox()
        self.stock_site.setEditable(True)
        metadata_layout.addWidget(self.stock_site)

        metadata_layout.addWidget(QLabel("Stock Notes"))
        self.stock_notes_edit = AutoResizingTextEdit(min_height=48, max_height=400)
        self.stock_notes_edit.setPlaceholderText("Personal notes, concepts, or production notes")
        metadata_layout.addWidget(self.stock_notes_edit)

        metadata_layout.addWidget(QLabel("Location"))
        self.stock_location_edit = QLineEdit()
        self.stock_location_edit.setPlaceholderText("Location")
        metadata_layout.addWidget(self.stock_location_edit)

        metadata_layout.addWidget(QLabel("Usage / License Notes"))
        self.stock_usage_edit = AutoResizingTextEdit(min_height=48, max_height=400)
        self.stock_usage_edit.setPlaceholderText("Usage or licensing notes")
        metadata_layout.addWidget(self.stock_usage_edit)

        self.save_data_btn = QPushButton("Save Data")
        metadata_layout.addWidget(self.save_data_btn)
        metadata_layout.addStretch(1)

        # ── Export tab ────────────────────────────────────────────
        export_tab = QWidget()
        export_layout = QVBoxLayout(export_tab)
        export_layout.setContentsMargins(2, 2, 2, 2)
        self.export_btn = QPushButton("Export…")
        export_layout.addWidget(self.export_btn)
        export_layout.addWidget(QLabel("Opens export options dialog."))
        export_layout.addStretch(1)

        self.tabs.addTab(metadata_tab, "Metadata")
        self.tabs.addTab(export_tab, "Export")
        self.tabs.currentChanged.connect(self._animate_tab_transition)

        self.ai_generate_btn.clicked.connect(self._emit_ai_generate_requested)

    def _animate_tab_transition(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if tab is None:
            return
        effect = QGraphicsOpacityEffect(tab)
        tab.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(150)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _finish() -> None:
            tab.setGraphicsEffect(None)
            if anim in self._tab_animations:
                self._tab_animations.remove(anim)

        anim.finished.connect(_finish)
        self._tab_animations.append(anim)
        anim.start()

    def set_preview(self, _image_path: str) -> None:
        pass

    def _emit_ai_generate_requested(self, checked: bool = False) -> None:
        self.ai_generate_requested.emit()

    def set_ai_result(self, result) -> None:
        """Populate AI metadata fields from an AIAnalysisResult without saving."""
        self.title_edit.setPlainText(result.title)
        self.description_edit.setPlainText(result.description or result.caption)
        self.keywords_edit.setPlainText(", ".join(result.keywords[:50]))
        self.set_ai_saved(False)
        self.tabs.setCurrentIndex(0)

    def set_stock_sites(self, sites: list[str], current: str = "") -> None:
        selected = current.strip()
        self.stock_site.blockSignals(True)
        self.stock_site.clear()
        for site in sites:
            text = site.strip()
            if text:
                self.stock_site.addItem(text)
        if selected:
            self._set_combo_text(self.stock_site, selected)
        else:
            self.stock_site.setCurrentIndex(-1)
        self.stock_site.blockSignals(False)

    def set_candidate(self, payload: dict[str, object]) -> None:
        candidate_id = payload.get("candidate_id")
        self.current_candidate_id = int(candidate_id) if isinstance(candidate_id, int) else None

        path = str(payload.get("path", ""))
        self.filename.setText(str(payload.get("filename", path or "No image selected")))

        # Quality score and metrics
        overall_score = payload.get("overall_score")
        if overall_score is not None:
            self.score_label.setText(f"Quality: {float(overall_score):.1f} / 100")
        else:
            self.score_label.setText("Quality: Not analyzed")

        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            for key, bar in self._bars.items():
                val = metrics.get(key)
                bar.setValue(int(float(val)) if val is not None else 0)
        else:
            for bar in self._bars.values():
                bar.setValue(0)

        # EXIF data
        exif = payload.get("exif") or {}
        camera_make = self._display_value(exif.get("camera_make"))
        camera_model = self._display_value(exif.get("camera_model"))
        if camera_make != "Unavailable" and camera_model != "Unavailable":
            camera_text = f"{camera_make} {camera_model}".strip()
        else:
            camera_text = camera_model if camera_model != "Unavailable" else camera_make
        self.camera.setText(camera_text)
        self.lens.setText(self._display_value(exif.get("lens")))
        self.iso.setText(self._display_value(exif.get("iso")))
        self.aperture.setText(self._display_value(exif.get("aperture")))
        self.focal_length.setText(self._display_value(exif.get("focal_length")))
        self.shutter_speed.setText(self._display_value(exif.get("shutter_speed")))

        # AI metadata
        self.title_edit.setPlainText(str(payload.get("title") or ""))
        self.description_edit.setPlainText(str(payload.get("description") or ""))
        keywords = payload.get("keywords", [])
        if isinstance(keywords, list):
            keyword_list = [str(k).strip() for k in keywords if str(k).strip()]
            self.keywords_edit.setPlainText(", ".join(keyword_list[:50]))

        self._set_combo_text(self.stock_site, str(payload.get("stock_site") or ""))
        self.stock_notes_edit.setPlainText(str(payload.get("stock_notes") or ""))
        self.stock_location_edit.setText(str(payload.get("stock_location") or ""))
        self.stock_usage_edit.setPlainText(str(payload.get("stock_usage_notes") or ""))

        self.set_feedback("")
        self.set_ai_saved(False)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        text = value.strip()
        if not text:
            combo.setCurrentIndex(-1)
            return
        index = combo.findText(text)
        if index < 0:
            combo.addItem(text)
            index = combo.findText(text)
        combo.setCurrentIndex(index)

    @staticmethod
    def _display_value(value: object) -> str:
        text = str(value).strip()
        return text if text else "Unavailable"

    def set_feedback(self, message: str, *, success: bool | None = None) -> None:
        self.feedback.setText(message)
        if success is None:
            self.feedback.setStyleSheet("")
        elif success:
            self.feedback.setStyleSheet("color: #6ee7b7;")
        else:
            self.feedback.setStyleSheet("color: #fda4af;")

    def set_ai_saved(self, saved: bool) -> None:
        self.ai_saved_badge.setVisible(saved)
