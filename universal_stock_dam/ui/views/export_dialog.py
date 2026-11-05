from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.core.paths import resource_path


class ExportDialog(QDialog):
    def __init__(
        self,
        default_dir: str,
        default_format: str,
        default_quality: int,
        default_lut_path: str = "",
        default_filename_template: str = "{stem}",
        export_presets: list[dict[str, object]] | None = None,
        default_preset_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Options")
        self._presets = [dict(preset) for preset in (export_presets or [])]

        root = QVBoxLayout(self)

        preset_row = QHBoxLayout()
        self.preset_name = QLineEdit(default_preset_name)
        self.save_preset_btn = QPushButton("Save Preset")
        self.delete_preset_btn = QPushButton("Delete Preset")
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Custom", None)
        for preset in self._presets:
            self.preset_combo.addItem(str(preset.get("name", "Unnamed")), str(preset.get("name", "")))
        if default_preset_name and self.preset_combo.findData(default_preset_name) >= 0:
            self.preset_combo.setCurrentIndex(self.preset_combo.findData(default_preset_name))
        self.preset_combo.currentIndexChanged.connect(self._apply_selected_preset)
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.delete_preset_btn.clicked.connect(self._delete_preset)
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(self.preset_name)
        preset_row.addWidget(self.save_preset_btn)
        preset_row.addWidget(self.delete_preset_btn)
        root.addLayout(preset_row)

        layout = QFormLayout()
        root.addLayout(layout)

        self.output_dir = QLineEdit(default_dir)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_output_dir)

        output_row = QHBoxLayout()
        output_row.addWidget(self.output_dir, 1)
        output_row.addWidget(browse_btn)
        layout.addRow("Output Folder", output_row)

        self.output_format = QComboBox()
        self.output_format.addItems(["jpg", "png", "tiff", "webp"])
        self.output_format.setCurrentText(default_format.lower().lstrip("."))
        self.output_format.currentTextChanged.connect(self._sync_quality_state)
        layout.addRow("Format", self.output_format)

        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(int(max(1, min(default_quality, 100))))
        layout.addRow("JPEG Quality", self.jpeg_quality)

        self.lut_path = QComboBox()
        self.lut_path.setEditable(True)
        self._populate_lut_choices(default_lut_path)
        layout.addRow("LUT", self.lut_path)

        self.filename_template = QLineEdit(default_filename_template or "{stem}")
        self.filename_template.setPlaceholderText("{stem} or {stem}_{index}")
        layout.addRow("Filename Template", self.filename_template)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._sync_quality_state(self.output_format.currentText())
        self._apply_selected_preset(self.preset_combo.currentIndex())

    def values(self) -> dict[str, object]:
        return {
            "output_dir": self.output_dir.text().strip(),
            "output_format": self.output_format.currentText().strip().lower(),
            "jpeg_quality": int(self.jpeg_quality.value()),
            "lut_path": self.lut_path.currentText().strip(),
            "filename_template": self.filename_template.text().strip() or "{stem}",
            "export_presets": self._presets,
            "default_preset_name": self.preset_name.text().strip(),
        }

    def _browse_output_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Select Export Folder", self.output_dir.text().strip())
        if selected:
            self.output_dir.setText(selected)

    def _sync_quality_state(self, output_format: str) -> None:
        self.jpeg_quality.setEnabled(output_format in {"jpg", "jpeg"})

    def _populate_lut_choices(self, default_lut_path: str) -> None:
        self.lut_path.addItem("")
        lut_root = resource_path("luts")
        lut_files: list[Path] = []
        if lut_root.exists():
            lut_files.extend(sorted(lut_root.glob("*.npy")))
            lut_files.extend(sorted(lut_root.glob("*.cube")))

        seen: set[str] = set()
        for lut_file in lut_files:
            path = str(lut_file.expanduser().resolve())
            if path in seen:
                continue
            seen.add(path)
            self.lut_path.addItem(path)

        if default_lut_path:
            default_path = str(Path(default_lut_path).expanduser().resolve()) if Path(default_lut_path).exists() else default_lut_path
            if self.lut_path.findText(default_path) < 0:
                self.lut_path.addItem(default_path)
            self.lut_path.setCurrentText(default_path)

    def _preset_payload(self) -> dict[str, object]:
        return {
            "name": self.preset_name.text().strip() or "Preset",
            "output_dir": self.output_dir.text().strip(),
            "output_format": self.output_format.currentText().strip().lower(),
            "jpeg_quality": int(self.jpeg_quality.value()),
            "lut_path": self.lut_path.currentText().strip(),
            "filename_template": self.filename_template.text().strip() or "{stem}",
        }

    def _apply_preset_payload(self, payload: dict[str, object]) -> None:
        self.preset_name.setText(str(payload.get("name", "")))
        self.output_dir.setText(str(payload.get("output_dir", self.output_dir.text())))
        self.output_format.setCurrentText(str(payload.get("output_format", self.output_format.currentText())))
        self.jpeg_quality.setValue(int(payload.get("jpeg_quality", self.jpeg_quality.value())))
        self.lut_path.setCurrentText(str(payload.get("lut_path", self.lut_path.currentText())))
        self.filename_template.setText(str(payload.get("filename_template", self.filename_template.text())))

    def _apply_selected_preset(self, index: int) -> None:
        payload_name = self.preset_combo.itemData(index)
        if not payload_name:
            return
        preset = next((preset for preset in self._presets if str(preset.get("name", "")) == str(payload_name)), None)
        if preset is not None:
            self._apply_preset_payload(preset)

    def _save_preset(self) -> None:
        payload = self._preset_payload()
        preset_name = str(payload.get("name", "")).strip()
        if not preset_name:
            return
        existing = next((preset for preset in self._presets if str(preset.get("name", "")) == preset_name), None)
        if existing is not None:
            existing.update(payload)
        else:
            self._presets.append(payload)
            self.preset_combo.addItem(preset_name, preset_name)
        self.preset_combo.setCurrentIndex(self.preset_combo.findData(preset_name))

    def _delete_preset(self) -> None:
        preset_name = self.preset_name.text().strip()
        if not preset_name:
            return
        self._presets = [preset for preset in self._presets if str(preset.get("name", "")) != preset_name]
        index = self.preset_combo.findData(preset_name)
        if index >= 0:
            self.preset_combo.removeItem(index)
        self.preset_combo.setCurrentIndex(0)
