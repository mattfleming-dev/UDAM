from __future__ import annotations

from PySide6.QtCore import QDir
from PySide6.QtWidgets import (
    QCheckBox,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class CatalogView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)

        self.tree = QTreeView()
        self.model = QFileSystemModel(self)
        self.model.setRootPath(QDir.rootPath())
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(QDir.homePath()))
        root.addWidget(self.tree)

        options = QHBoxLayout()
        self.recursive = QCheckBox("Recursive")
        self.recursive.setChecked(True)
        self.auto_quality = QCheckBox("Analyze During Scan")
        self.start_scan = QPushButton("Scan Selected Folder")
        options.addWidget(self.recursive)
        options.addWidget(self.auto_quality)
        options.addWidget(self.start_scan)
        root.addLayout(options)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        root.addWidget(QLabel("Scan Log"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log)

    def selected_path(self) -> str:
        idx = self.tree.currentIndex()
        return self.model.filePath(idx)
