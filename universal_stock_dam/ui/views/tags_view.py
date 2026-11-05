from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget


class TagsView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        self.tags_list = QListWidget()
        root.addWidget(QLabel("Tags"))
        self.summary_label = QLabel("0 tags")
        root.addWidget(self.summary_label)
        root.addWidget(self.tags_list)

        self.detail_label = QLabel("Select a tag to view details")
        root.addWidget(self.detail_label)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Selected tag name")
        self.color_edit = QLineEdit()
        self.color_edit.setPlaceholderText("#RRGGBB")
        root.addWidget(self.name_edit)
        root.addWidget(self.color_edit)

        row1 = QHBoxLayout()
        row2 = QHBoxLayout()
        self.save_tag_btn = QPushButton("Save")
        self.add_tag_btn = QPushButton("Add")
        self.rename_tag_btn = QPushButton("Rename")
        self.edit_color_btn = QPushButton("Color")
        self.delete_tag_btn = QPushButton("Delete")
        self.ai_batch = QPushButton("AI Batch")
        for b in (self.add_tag_btn, self.rename_tag_btn, self.edit_color_btn):
            row1.addWidget(b)
        for b in (self.save_tag_btn, self.delete_tag_btn, self.ai_batch):
            row2.addWidget(b)
        root.addLayout(row1)
        root.addLayout(row2)

    def set_summary(self, total_tags: int) -> None:
        self.summary_label.setText(f"{total_tags} tags")

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)
