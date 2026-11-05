from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.core.settings import DamSettings, available_llamacpp_backends
from universal_stock_dam.ui.widgets.auto_resizing_text_edit import AutoResizingTextEdit


class SettingsView(QWidget):
    refresh_models_requested = Signal()
    test_provider_requested = Signal()
    save_test_profile_requested = Signal()
    clear_thumbnail_cache_requested = Signal()
    trim_thumbnail_cache_requested = Signal()
    reset_thumbnail_cache_stats_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        layout = QFormLayout()
        layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
        layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        root.addLayout(layout)
        self.settings_form = layout

        self.ai_provider = QComboBox()
        self.ai_provider.addItem("Llama.cpp", "llamacpp")
        self.ai_provider.addItem("AI-Core", "aicore")
        self.ai_core_base_url = QLineEdit("http://127.0.0.1:8080")
        self.ai_core_base_url.setPlaceholderText("http://127.0.0.1:8080")
        self.ai_core_model = QLineEdit("auto")
        self.ai_core_model.setPlaceholderText("auto")

        self.llamacpp_binary = QLineEdit()
        self.llamacpp_binary.setPlaceholderText("Path to llama-server.exe")
        self.llamacpp_backend = QComboBox()
        self._available_backends = available_llamacpp_backends()
        backend_labels = {"cpu": "CPU", "cuda": "CUDA (NVIDIA GPU)"}
        for backend_id in ("cpu", "cuda"):
            label = backend_labels[backend_id]
            if backend_id not in self._available_backends:
                label += " (not bundled)"
            self.llamacpp_backend.addItem(label, backend_id)
        self.llamacpp_backend.currentIndexChanged.connect(self._on_backend_changed)
        self.llamacpp_model = QComboBox()
        self.llamacpp_model.setEditable(True)
        self.llamacpp_model.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.llamacpp_model.setMinimumContentsLength(24)
        self.llamacpp_model.lineEdit().setToolTip("Full path to the .gguf model file")
        self.llamacpp_model.currentTextChanged.connect(self.llamacpp_model.lineEdit().setToolTip)
        self.browse_model_btn = QPushButton("Browse")
        self.browse_model_btn.setToolTip("Browse for a .gguf model file")
        self.llamacpp_mmproj = QLineEdit()
        self.llamacpp_mmproj.setPlaceholderText("Optional: mmproj-*.gguf for vision support")
        self.browse_mmproj_btn = QPushButton("Browse")
        self.browse_mmproj_btn.setToolTip("Browse for a mmproj-*.gguf vision projector file")
        self.open_models_folder_btn = QPushButton("Open Models Folder")
        self.open_models_folder_btn.setToolTip(
            "Opens the folder where you can drop your own .gguf model / mmproj files "
            "(used when no model is bundled with the installer)."
        )
        self.llamacpp_host = QLineEdit()
        self.llamacpp_port = QSpinBox()
        self.llamacpp_port.setRange(1, 65535)
        self.llamacpp_context = QSpinBox()
        self.llamacpp_context.setRange(512, 131072)
        self.llamacpp_context.setSingleStep(512)
        self.llamacpp_gpu_layers = QSpinBox()
        self.llamacpp_gpu_layers.setRange(-1, 999)
        self.refresh_models_btn = QPushButton("Refresh Models")
        self.ai_prompt_preset = QComboBox()
        self.ai_prompt_preset.addItems(["stock", "descriptive", "minimal", "custom"])
        self.ai_prompt_custom = AutoResizingTextEdit(min_height=48, max_height=240)
        self.ai_prompt_custom.setPlaceholderText("Optional custom AI prompt used when preset is 'custom'")
        self.exiftool = QLineEdit()
        self.cache_dir = QLineEdit()
        self.cache_enabled = QCheckBox("Enable in-memory thumbnail cache")
        self.cache_enabled.setChecked(True)
        self.export_dir = QLineEdit()
        self.browse_export_dir_btn = QPushButton("Browse")
        self.browse_export_dir_btn.setToolTip("Browse for the default export output folder")
        self.export_format = QComboBox()
        self.export_format.addItems(["jpg", "png", "tiff", "webp"])
        self.export_lut = QLineEdit()
        self.browse_export_lut_btn = QPushButton("Browse")
        self.browse_export_lut_btn.setToolTip("Browse for a LUT file (.cube or .npy)")
        self.export_filename_template = QLineEdit()
        self.export_filename_template.setPlaceholderText("{stem}")
        self.stock_site_name = QLineEdit()
        self.stock_sites = QListWidget()
        self.stock_sites.setSelectionMode(QAbstractItemView.SingleSelection)
        self.stock_site_add_btn = QPushButton("Add")
        self.stock_site_remove_btn = QPushButton("Remove")

        self.cache_gb = QDoubleSpinBox()
        self.cache_gb.setRange(0.1, 500.0)
        self.cache_gb.setDecimals(1)

        self.cache_items = QSpinBox()
        self.cache_items.setRange(50, 50000)
        self.cache_items.setSingleStep(50)
        self.cache_items.setValue(1200)
        self.cache_auto_maintenance = QCheckBox("Enable auto cache maintenance")
        self.cache_auto_maintenance.setChecked(True)
        self.cache_auto_threshold = QDoubleSpinBox()
        self.cache_auto_threshold.setRange(50.0, 100.0)
        self.cache_auto_threshold.setDecimals(0)
        self.cache_auto_threshold.setSingleStep(5.0)
        self.cache_auto_threshold.setValue(90.0)
        self.cache_auto_keep = QDoubleSpinBox()
        self.cache_auto_keep.setRange(0.1, 0.95)
        self.cache_auto_keep.setDecimals(2)
        self.cache_auto_keep.setSingleStep(0.05)
        self.cache_auto_keep.setValue(0.5)
        self.clear_cache_btn = QPushButton("Clear In-Memory Cache")
        self.trim_cache_btn = QPushButton("Trim Cache to 50%")
        self.reset_cache_stats_btn = QPushButton("Reset Cache Stats")
        self.cache_status = QLabel("Cache status: not available yet")
        self.cache_status.setWordWrap(True)

        self.export_quality = QDoubleSpinBox()
        self.export_quality.setRange(1, 100)
        self.export_quality.setDecimals(0)

        layout.addRow("AI Provider", self.ai_provider)
        self._llamacpp_rows = list(range(layout.rowCount(), layout.rowCount() + 8))
        layout.addRow("Compute Backend", self.llamacpp_backend)
        layout.addRow("Llama.cpp Server Binary", self.llamacpp_binary)
        llamacpp_model_row = QHBoxLayout()
        llamacpp_model_row.addWidget(self.llamacpp_model, 1)
        llamacpp_model_row.addWidget(self.browse_model_btn)
        llamacpp_model_row.addWidget(self.refresh_models_btn)
        layout.addRow("Llama.cpp Model (.gguf)", llamacpp_model_row)
        llamacpp_mmproj_row = QHBoxLayout()
        llamacpp_mmproj_row.addWidget(self.llamacpp_mmproj, 1)
        llamacpp_mmproj_row.addWidget(self.browse_mmproj_btn)
        layout.addRow("Vision Projector (mmproj, optional)", llamacpp_mmproj_row)
        layout.addRow("No model found?", self.open_models_folder_btn)
        llamacpp_net_row = QHBoxLayout()
        llamacpp_net_row.addWidget(QLabel("Host"))
        llamacpp_net_row.addWidget(self.llamacpp_host)
        llamacpp_net_row.addWidget(QLabel("Port"))
        llamacpp_net_row.addWidget(self.llamacpp_port)
        layout.addRow("Llama.cpp Server Address", llamacpp_net_row)
        layout.addRow("Context Size", self.llamacpp_context)
        layout.addRow("GPU Layers (-1 = all)", self.llamacpp_gpu_layers)
        self._aicore_rows = [layout.rowCount(), layout.rowCount() + 1]
        layout.addRow("AI-Core API URL", self.ai_core_base_url)
        layout.addRow("AI-Core Model", self.ai_core_model)
        layout.addRow("AI Prompt Preset", self.ai_prompt_preset)
        layout.addRow("AI Custom Prompt", self.ai_prompt_custom)
        layout.addRow("ExifTool Path", self.exiftool)
        layout.addRow("Thumbnail Cache Dir", self.cache_dir)
        layout.addRow("Thumbnail Cache", self.cache_enabled)
        layout.addRow("Cache Limit (GB)", self.cache_gb)
        layout.addRow("Cache Max Items", self.cache_items)
        layout.addRow("Auto Maintenance", self.cache_auto_maintenance)
        layout.addRow("Auto Trim Threshold (%)", self.cache_auto_threshold)
        layout.addRow("Auto Keep Ratio", self.cache_auto_keep)
        maintenance_row = QVBoxLayout()
        maintenance_row.setSpacing(2)
        top_row = QHBoxLayout()
        top_row.addWidget(self.clear_cache_btn)
        top_row.addWidget(self.trim_cache_btn)
        maintenance_row.addLayout(top_row)
        maintenance_row.addWidget(self.reset_cache_stats_btn)
        layout.addRow("Cache Maintenance", maintenance_row)
        layout.addRow("Cache Status", self.cache_status)
        export_dir_row = QHBoxLayout()
        export_dir_row.addWidget(self.export_dir, 1)
        export_dir_row.addWidget(self.browse_export_dir_btn)
        layout.addRow("Export Dir", export_dir_row)
        layout.addRow("Export Format", self.export_format)
        layout.addRow("JPEG Quality", self.export_quality)
        export_lut_row = QHBoxLayout()
        export_lut_row.addWidget(self.export_lut, 1)
        export_lut_row.addWidget(self.browse_export_lut_btn)
        layout.addRow("Export LUT", export_lut_row)
        layout.addRow("Filename Template", self.export_filename_template)
        stock_site_row = QHBoxLayout()
        stock_site_row.addWidget(self.stock_site_name, 1)
        stock_site_row.addWidget(self.stock_site_add_btn)
        stock_site_row.addWidget(self.stock_site_remove_btn)
        layout.addRow("Stock Sites", stock_site_row)
        layout.addRow("Available Sites", self.stock_sites)

        button_row = QVBoxLayout()
        button_row.setSpacing(2)
        top_btn_row = QHBoxLayout()
        bottom_btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.reload_btn = QPushButton("Reload")
        self.test_btn = QPushButton("Test Provider")
        self.save_profile_btn = QPushButton("Save Test Profile")
        self.save_profile_btn.setEnabled(False)
        top_btn_row.addWidget(self.save_btn)
        top_btn_row.addWidget(self.reload_btn)
        bottom_btn_row.addWidget(self.test_btn)
        bottom_btn_row.addWidget(self.save_profile_btn)
        button_row.addLayout(top_btn_row)
        button_row.addLayout(bottom_btn_row)
        layout.addRow(button_row)

        self.ai_test_status = QLabel("AI test has not been run yet.")
        self.ai_test_status.setWordWrap(True)
        self.ai_test_output = AutoResizingTextEdit(min_height=48, max_height=500)
        self.ai_test_output.setReadOnly(True)
        self.ai_test_output.setPlaceholderText("Provider test output appears here")
        root.addWidget(self.ai_test_status)
        root.addWidget(self.ai_test_output)

        self.refresh_models_btn.clicked.connect(self.refresh_models_requested)
        self.test_btn.clicked.connect(self.test_provider_requested)
        self.save_profile_btn.clicked.connect(self.save_test_profile_requested)
        self.clear_cache_btn.clicked.connect(self.clear_thumbnail_cache_requested)
        self.trim_cache_btn.clicked.connect(self.trim_thumbnail_cache_requested)
        self.reset_cache_stats_btn.clicked.connect(self.reset_thumbnail_cache_stats_requested)
        self.ai_provider.currentIndexChanged.connect(self._update_ai_provider_fields)
        self.stock_site_add_btn.clicked.connect(self._on_add_stock_site)
        self.stock_site_remove_btn.clicked.connect(self._on_remove_stock_site)
        self.browse_model_btn.clicked.connect(self._on_browse_model)
        self.browse_mmproj_btn.clicked.connect(self._on_browse_mmproj)
        self.browse_export_dir_btn.clicked.connect(self._on_browse_export_dir)
        self.browse_export_lut_btn.clicked.connect(self._on_browse_export_lut)
        self._update_ai_provider_fields()

    def _update_ai_provider_fields(self) -> None:
        use_llamacpp = self.ai_provider.currentData() != "aicore"
        for row in self._llamacpp_rows:
            self.settings_form.setRowVisible(row, use_llamacpp)
        for row in self._aicore_rows:
            self.settings_form.setRowVisible(row, not use_llamacpp)

    def set_cache_status(self, status_text: str) -> None:
        self.cache_status.setText(status_text.strip() or "Cache status: not available yet")

    def _on_backend_changed(self, index: int) -> None:
        backend_id = self.llamacpp_backend.itemData(index)
        path = self._available_backends.get(backend_id, "")
        if path:
            self.llamacpp_binary.setText(path)
        self.llamacpp_gpu_layers.setValue(-1 if backend_id == "cuda" else 0)

    def _set_backend(self, backend_id: str) -> None:
        index = self.llamacpp_backend.findData(backend_id)
        if index < 0:
            index = 0
        self.llamacpp_backend.blockSignals(True)
        self.llamacpp_backend.setCurrentIndex(index)
        self.llamacpp_backend.blockSignals(False)

    def set_settings(self, settings: DamSettings) -> None:
        provider_index = self.ai_provider.findData(settings.ai_provider)
        if provider_index >= 0:
            self.ai_provider.setCurrentIndex(provider_index)
        self.ai_core_base_url.setText(settings.ai_core_base_url)
        self.ai_core_model.setText(settings.ai_core_model)
        self._set_backend(settings.llamacpp_backend)
        self.llamacpp_binary.setText(settings.llamacpp_binary_path)
        self._set_combo_text(self.llamacpp_model, settings.llamacpp_model_path)
        self.llamacpp_mmproj.setText(settings.llamacpp_mmproj_path)
        self.llamacpp_host.setText(settings.llamacpp_host)
        self.llamacpp_port.setValue(int(settings.llamacpp_port))
        self.llamacpp_context.setValue(int(settings.llamacpp_context_size))
        self.llamacpp_gpu_layers.setValue(int(settings.llamacpp_gpu_layers))
        self.ai_prompt_preset.setCurrentText(settings.ai_prompt_preset)
        self.ai_prompt_custom.setPlainText(settings.ai_prompt_custom)
        self.exiftool.setText(settings.exiftool_path)
        self.cache_dir.setText(settings.thumbnail_cache_dir)
        self.cache_enabled.setChecked(settings.thumbnail_cache_enabled)
        self.cache_gb.setValue(settings.thumbnail_cache_max_gb)
        self.cache_items.setValue(max(50, int(settings.thumbnail_cache_max_items)))
        self.cache_auto_maintenance.setChecked(settings.thumbnail_cache_auto_maintenance)
        self.cache_auto_threshold.setValue(float(settings.thumbnail_cache_auto_trim_threshold_pct))
        self.cache_auto_keep.setValue(float(settings.thumbnail_cache_auto_keep_ratio))
        self.export_dir.setText(settings.export_default_dir)
        self.export_format.setCurrentText(settings.export_default_format)
        self.export_quality.setValue(settings.export_jpeg_quality)
        self.export_lut.setText(settings.export_default_lut_path)
        self.export_filename_template.setText(settings.export_filename_template)
        self.stock_sites.clear()
        for site in settings.stock_sites:
            item = QListWidgetItem(site)
            self.stock_sites.addItem(item)

    @staticmethod
    def _set_combo_text(combo: QComboBox, value: str) -> None:
        text = value.strip()
        if not text:
            combo.setCurrentIndex(-1)
            return
        index_by_data = combo.findData(text)
        if index_by_data >= 0:
            combo.setCurrentIndex(index_by_data)
            return

        if combo.findText(text) < 0:
            combo.addItem(text)
        combo.setCurrentText(text)

    def set_model_options(self, gguf_models: list[str]) -> None:
        current = self.llamacpp_model.currentText().strip()
        self.llamacpp_model.blockSignals(True)
        self.llamacpp_model.clear()
        self.llamacpp_model.addItems(gguf_models)
        self._set_combo_text(self.llamacpp_model, current)
        self.llamacpp_model.blockSignals(False)

    def set_ai_test_result(self, success: bool, message: str) -> None:
        if success:
            self.ai_test_status.setText("AI test passed")
            self.ai_test_status.setStyleSheet("color: #6ee7b7;")
            self.save_profile_btn.setEnabled(True)
        else:
            self.ai_test_status.setText("AI test failed")
            self.ai_test_status.setStyleSheet("color: #fda4af;")
            self.save_profile_btn.setEnabled(False)
        self.ai_test_output.setPlainText(message)

    def read_settings(self) -> DamSettings:
        return DamSettings(
            ai_provider=str(self.ai_provider.currentData() or "llamacpp"),
            ai_core_base_url=self.ai_core_base_url.text().strip() or "http://127.0.0.1:8080",
            ai_core_model=self.ai_core_model.text().strip() or "auto",
            llamacpp_backend=str(self.llamacpp_backend.currentData() or "cpu"),
            llamacpp_binary_path=self.llamacpp_binary.text().strip(),
            llamacpp_model_path=self.llamacpp_model.currentText().strip(),
            llamacpp_mmproj_path=self.llamacpp_mmproj.text().strip(),
            llamacpp_host=self.llamacpp_host.text().strip() or "127.0.0.1",
            llamacpp_port=int(self.llamacpp_port.value()),
            llamacpp_context_size=int(self.llamacpp_context.value()),
            llamacpp_gpu_layers=int(self.llamacpp_gpu_layers.value()),
            ai_prompt_preset=self.ai_prompt_preset.currentText(),
            ai_prompt_custom=self.ai_prompt_custom.toPlainText().strip(),
            exiftool_path=self.exiftool.text().strip(),
            thumbnail_cache_dir=self.cache_dir.text().strip(),
            thumbnail_cache_enabled=self.cache_enabled.isChecked(),
            thumbnail_cache_max_gb=float(self.cache_gb.value()),
            thumbnail_cache_max_items=int(self.cache_items.value()),
            thumbnail_cache_auto_maintenance=self.cache_auto_maintenance.isChecked(),
            thumbnail_cache_auto_trim_threshold_pct=float(self.cache_auto_threshold.value()),
            thumbnail_cache_auto_keep_ratio=float(self.cache_auto_keep.value()),
            export_default_dir=self.export_dir.text().strip(),
            export_default_format=self.export_format.currentText(),
            export_jpeg_quality=int(self.export_quality.value()),
            export_default_lut_path=self.export_lut.text().strip(),
            export_filename_template=self.export_filename_template.text().strip() or "{stem}",
            stock_sites=self._stock_sites(),
        )

    def _stock_sites(self) -> list[str]:
        sites: list[str] = []
        for index in range(self.stock_sites.count()):
            text = self.stock_sites.item(index).text().strip()
            if text and text not in sites:
                sites.append(text)
        return sites

    def _on_add_stock_site(self) -> None:
        name = self.stock_site_name.text().strip()
        if not name:
            return
        if name.lower() in {self.stock_sites.item(i).text().strip().lower() for i in range(self.stock_sites.count())}:
            self.stock_site_name.clear()
            return
        self.stock_sites.addItem(QListWidgetItem(name))
        self.stock_site_name.clear()

    def _on_remove_stock_site(self) -> None:
        row = self.stock_sites.currentRow()
        if row < 0:
            return
        self.stock_sites.takeItem(row)

    def _on_browse_model(self) -> None:
        start_dir = str(Path(self.llamacpp_model.currentText().strip()).expanduser().parent) if self.llamacpp_model.currentText().strip() else ""
        selected, _ = QFileDialog.getOpenFileName(self, "Select Model File", start_dir, "GGUF Models (*.gguf);;All Files (*)")
        if selected:
            self._set_combo_text(self.llamacpp_model, selected)

    def _on_browse_mmproj(self) -> None:
        start_dir = str(Path(self.llamacpp_mmproj.text().strip()).expanduser().parent) if self.llamacpp_mmproj.text().strip() else ""
        selected, _ = QFileDialog.getOpenFileName(self, "Select Vision Projector File", start_dir, "GGUF Models (*.gguf);;All Files (*)")
        if selected:
            self.llamacpp_mmproj.setText(selected)

    def _on_browse_export_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select Default Export Folder", self.export_dir.text().strip())
        if selected:
            self.export_dir.setText(selected)

    def _on_browse_export_lut(self) -> None:
        start_dir = str(Path(self.export_lut.text().strip()).expanduser().parent) if self.export_lut.text().strip() else ""
        selected, _ = QFileDialog.getOpenFileName(self, "Select LUT File", start_dir, "LUT Files (*.cube *.npy);;All Files (*)")
        if selected:
            self.export_lut.setText(selected)
