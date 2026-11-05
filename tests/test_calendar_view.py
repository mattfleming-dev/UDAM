from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from universal_stock_dam.db.manager import DatabaseManager
from universal_stock_dam.core.settings import DamSettings
from universal_stock_dam.ui.views.calendar_view import CalendarView
from universal_stock_dam.ui.views.settings_view import SettingsView


def test_calendar_shows_event_and_opens_linked_asset(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    manager = DatabaseManager(str(tmp_path / "assets.db"))
    image = tmp_path / "asset.jpg"
    image.write_bytes(b"image")
    candidate = manager.add_or_update_candidate(str(image), image.name, "jpg")
    starts_at = datetime(2032, 4, 12, 14, 0)
    manager.save_calendar_event(
        title="Stock submission",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        candidate_id=candidate.id,
    )

    view = CalendarView(manager)
    view.calendar.setSelectedDate(QDate(2032, 4, 12))
    assert view.events.count() == 1
    assert "Stock submission" in view.events.item(0).text()

    spy = QSignalSpy(view.asset_open_requested)
    view.events.setCurrentRow(0)
    assert view.open_asset_btn.isEnabled()
    view.open_asset_btn.click()
    assert spy.count() == 1
    assert spy.at(0)[0] == candidate.id

    view.close()
    app.processEvents()


def test_settings_view_selects_aicore_provider_and_round_trips_values() -> None:
    app = QApplication.instance() or QApplication([])
    view = SettingsView()
    settings = DamSettings(ai_provider="aicore", ai_core_base_url="http://localhost:8080", ai_core_model="auto")

    view.set_settings(settings)
    read_back = view.read_settings()

    assert read_back.ai_provider == "aicore"
    assert read_back.ai_core_base_url == "http://localhost:8080"
    assert read_back.ai_core_model == "auto"
    assert view.settings_form.isRowVisible(view._aicore_rows[0])
    assert not view.settings_form.isRowVisible(view._llamacpp_rows[0])
    view.close()
    app.processEvents()