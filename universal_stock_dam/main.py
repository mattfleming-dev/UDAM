from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from universal_stock_dam.db.manager import DatabaseManager
from universal_stock_dam.core.paths import data_path
from universal_stock_dam.ui.main_window import MainWindow


def _configure_qt_font_dir() -> None:
    if os.environ.get("QT_QPA_FONTDIR"):
        return

    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if windows_fonts.exists():
        os.environ["QT_QPA_FONTDIR"] = str(windows_fonts)


def main() -> None:
    _configure_qt_font_dir()
    manager = DatabaseManager(str(data_path("assets.db")))

    app = QApplication([])
    window = MainWindow(db_manager=manager)
    window.show()
    app.exec()


if __name__ == "__main__":
    main()
