from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QTextEdit, QVBoxLayout, QWidget


class CollectionsView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Collections"))
        self.summary_label = QLabel("0 collections")
        root.addWidget(self.summary_label)

        self.collections = QListWidget()
        root.addWidget(self.collections)

        self.detail_label = QLabel("Select a collection to view details")
        root.addWidget(self.detail_label)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Selected collection name")
        root.addWidget(self.name_edit)

        self.description = QTextEdit()
        self.description.setPlaceholderText("Collection description")
        self.description.setMaximumHeight(60)
        root.addWidget(self.description)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        row3 = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.create_btn = QPushButton("Create")
        self.save_search_btn = QPushButton("Save Search")
        self.open_btn = QPushButton("Open")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.assign_btn = QPushButton("Assign Selected")
        for b in (self.create_btn, self.open_btn, self.edit_btn):
            row1.addWidget(b)
        for b in (self.delete_btn, self.save_btn):
            row2.addWidget(b)
        for b in (self.save_search_btn, self.assign_btn):
            row3.addWidget(b)
        root.addLayout(row1)
        root.addLayout(row2)
        root.addLayout(row3)

    def set_summary(self, total_collections: int) -> None:
        self.summary_label.setText(f"{total_collections} collections")

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)
