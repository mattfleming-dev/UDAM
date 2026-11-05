from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDir, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class FolderTreeWidget(QWidget):
    folder_selected = Signal(str)
    add_to_library_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("FolderTree")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("DockHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(8, 6, 8, 6)
        header_row.addWidget(QLabel("Folders"))
        header_row.addStretch(1)
        self._add_btn = QPushButton("＋ Library")
        self._add_btn.setToolTip("Scan selected folder into library")
        header_row.addWidget(self._add_btn)
        layout.addWidget(header)

        self._model = QFileSystemModel()
        self._model.setFilter(QDir.Dirs | QDir.NoDotAndDotDot)
        self._model.setRootPath("")

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setRootIndex(self._model.index(QDir.homePath()))
        self._tree.hideColumn(1)
        self._tree.hideColumn(2)
        self._tree.hideColumn(3)
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        layout.addWidget(self._tree, 1)

        self._tree.selectionModel().currentChanged.connect(self._on_selection_changed)
        self._add_btn.clicked.connect(self._on_add_to_library)

    def _on_selection_changed(self, current, _previous) -> None:
        path = self._model.filePath(current)
        if path and Path(path).is_dir():
            self.folder_selected.emit(path)

    def _on_add_to_library(self) -> None:
        path = self._current_path()
        if not path:
            path = QFileDialog.getExistingDirectory(self, "Select folder to add to library")
        if path:
            self.add_to_library_requested.emit(path)

    def _current_path(self) -> str:
        idx = self._tree.currentIndex()
        return self._model.filePath(idx) if idx.isValid() else ""

    def navigate_to(self, path: str) -> None:
        idx = self._model.index(path)
        if idx.isValid():
            self._tree.setCurrentIndex(idx)
            self._tree.expand(idx)
            self._tree.scrollTo(idx)
