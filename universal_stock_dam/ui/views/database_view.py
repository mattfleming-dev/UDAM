from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


class DatabaseView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        root = QVBoxLayout(self)
        grid = QGridLayout()

        self.images_value = QLabel("0")
        self.tags_value = QLabel("0")
        self.collections_value = QLabel("0")
        self.db_size_value = QLabel("0 MB")

        stat_pairs = [
            ("Images", self.images_value),
            ("Tags", self.tags_value),
            ("Collections", self.collections_value),
            ("DB Size", self.db_size_value),
        ]

        for idx, (title, value_label) in enumerate(stat_pairs):
            card = QFrame()
            card.setObjectName("Card")
            card_layout = QVBoxLayout(card)
            card_layout.addWidget(QLabel(title))
            card_layout.addWidget(value_label)
            grid.addWidget(card, idx // 2, idx % 2)

        root.addLayout(grid)

        self.backup_btn = QPushButton("Create Backup")
        self.restore_btn = QPushButton("Restore Backup")
        self.reset_btn = QPushButton("Reset Database")
        self.clean_missing_btn = QPushButton("Clean Missing Files")
        self.vacuum_btn = QPushButton("Vacuum")
        self.enforce_cache_btn = QPushButton("Enforce Thumbnail Cache Limit")
        self.find_duplicates_btn = QPushButton("Find Duplicates")

        root.addWidget(self.backup_btn)
        root.addWidget(self.restore_btn)
        root.addWidget(self.reset_btn)
        root.addWidget(self.clean_missing_btn)
        root.addWidget(self.vacuum_btn)
        root.addWidget(self.enforce_cache_btn)
        root.addWidget(self.find_duplicates_btn)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        root.addWidget(self.log)

    def set_stats(self, stats: dict[str, object]) -> None:
        self.images_value.setText(str(stats.get("images", 0)))
        self.tags_value.setText(str(stats.get("tags", 0)))
        self.collections_value.setText(str(stats.get("collections", 0)))
        self.db_size_value.setText(f"{stats.get('db_size_mb', 0)} MB")
