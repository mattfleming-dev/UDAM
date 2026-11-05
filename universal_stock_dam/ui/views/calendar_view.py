from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QDate, QDateTime, QTime, Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.db.manager import DatabaseManager


class CalendarEventDialog(QDialog):
    def __init__(
        self,
        database_manager: DatabaseManager,
        selected_date: QDate,
        *,
        event: dict[str, object] | None = None,
        default_candidate_id: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Scheduled Event" if event else "Schedule Event")
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit(str(event.get("title", "")) if event else "")
        self.title_edit.setPlaceholderText("Event title")
        self.title_edit.setMaxLength(256)
        self.starts_at = QDateTimeEdit()
        self.starts_at.setCalendarPopup(True)
        self.starts_at.setDisplayFormat("ddd, MMM d yyyy h:mm AP")
        self.ends_at = QDateTimeEdit()
        self.ends_at.setCalendarPopup(True)
        self.ends_at.setDisplayFormat("ddd, MMM d yyyy h:mm AP")
        if event:
            self.starts_at.setDateTime(self._qt_datetime(event["starts_at"]))
            self.ends_at.setDateTime(self._qt_datetime(event["ends_at"]))
        else:
            start = QDateTime(selected_date, QTime(9, 0))
            self.starts_at.setDateTime(start)
            self.ends_at.setDateTime(start.addSecs(3600))

        self.description_edit = QPlainTextEdit(str(event.get("description", "")) if event else "")
        self.description_edit.setPlaceholderText("Notes or preparation details")
        self.description_edit.setMaximumHeight(100)
        self.asset_combo = QComboBox()
        self.asset_combo.addItem("No asset linked", None)
        for asset in database_manager.list_calendar_asset_choices():
            self.asset_combo.addItem(f"{asset['filename']}  |  {asset['path']}", int(asset["id"]))

        form.addRow("Title", self.title_edit)
        form.addRow("Starts", self.starts_at)
        form.addRow("Ends", self.ends_at)
        form.addRow("Digital asset", self.asset_combo)
        form.addRow("Notes", self.description_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        candidate_id = event.get("candidate_id") if event else default_candidate_id
        if candidate_id is not None:
            index = self.asset_combo.findData(int(candidate_id))
            if index >= 0:
                self.asset_combo.setCurrentIndex(index)

    @staticmethod
    def _qt_datetime(value: object) -> QDateTime:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        return QDateTime(
            QDate(parsed.year, parsed.month, parsed.day),
            QTime(parsed.hour, parsed.minute, parsed.second),
        )

    def _accept_if_valid(self) -> None:
        if not self.title_edit.text().strip():
            QMessageBox.warning(self, "Event title required", "Enter a title for this event.")
            return
        if self.ends_at.dateTime() <= self.starts_at.dateTime():
            QMessageBox.warning(self, "Invalid event time", "The end time must be after the start time.")
            return
        self.accept()

    def values(self) -> dict[str, object]:
        candidate_id = self.asset_combo.currentData()
        return {
            "title": self.title_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
            "starts_at": self.starts_at.dateTime().toPython(),
            "ends_at": self.ends_at.dateTime().toPython(),
            "candidate_id": int(candidate_id) if candidate_id is not None else None,
        }


class CalendarView(QWidget):
    asset_open_requested = Signal(int)

    def __init__(self, database_manager: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.database_manager = database_manager
        self.current_candidate_id: int | None = None
        self._marked_dates: list[QDate] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)
        root.addWidget(QLabel("Schedule"))

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.setFirstDayOfWeek(Qt.Monday)
        self.calendar.setMinimumHeight(250)
        root.addWidget(self.calendar)

        self.day_label = QLabel()
        self.day_label.setObjectName("CalendarDayLabel")
        root.addWidget(self.day_label)

        self.events = QListWidget()
        self.events.setObjectName("CalendarEvents")
        root.addWidget(self.events, 1)

        actions = QHBoxLayout()
        self.add_btn = QPushButton("New")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.open_asset_btn = QPushButton("Open Asset")
        for button in (self.add_btn, self.edit_btn, self.delete_btn, self.open_asset_btn):
            actions.addWidget(button)
        root.addLayout(actions)

        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.open_asset_btn.setEnabled(False)
        self.calendar.selectionChanged.connect(self.refresh_day)
        self.calendar.currentPageChanged.connect(lambda _year, _month: self.refresh())
        self.events.itemSelectionChanged.connect(self._update_actions)
        self.events.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        self.add_btn.clicked.connect(self._create_event)
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.open_asset_btn.clicked.connect(self._open_selected_asset)
        self.refresh()

    def set_current_candidate(self, candidate_id: int | None) -> None:
        self.current_candidate_id = candidate_id

    def refresh(self) -> None:
        for old_date in self._marked_dates:
            self.calendar.setDateTextFormat(old_date, QTextCharFormat())
        self._marked_dates.clear()

        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        month_start = datetime(year, month, 1)
        month_end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1)
        for event in self.database_manager.list_calendar_events(month_end, month_start):
            starts_at = event["starts_at"]
            if not isinstance(starts_at, datetime):
                continue
            marked = QDate(starts_at.year, starts_at.month, starts_at.day)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#8fd4b0"))
            fmt.setFontWeight(QFont.Weight.Bold)
            self.calendar.setDateTextFormat(marked, fmt)
            self._marked_dates.append(marked)
        self.refresh_day()

    def refresh_day(self) -> None:
        selected = self.calendar.selectedDate()
        self.day_label.setText(selected.toString("dddd, MMMM d"))
        day_start = datetime(selected.year(), selected.month(), selected.day())
        day_end = day_start + timedelta(days=1)
        self.events.clear()
        for event in self.database_manager.list_calendar_events(day_end, day_start):
            starts_at = event["starts_at"]
            ends_at = event["ends_at"]
            if not isinstance(starts_at, datetime) or not isinstance(ends_at, datetime):
                continue
            asset = str(event.get("candidate_filename") or "No linked asset")
            item = QListWidgetItem(f"{starts_at:%I:%M %p}  {event['title']}\n{asset}")
            item.setData(Qt.UserRole, int(event["id"]))
            item.setData(Qt.UserRole + 1, event.get("candidate_id"))
            item.setData(Qt.UserRole + 2, event)
            self.events.addItem(item)
        self._update_actions()

    def _selected_event(self) -> dict[str, object] | None:
        item = self.events.currentItem()
        payload = item.data(Qt.UserRole + 2) if item else None
        return payload if isinstance(payload, dict) else None

    def _update_actions(self) -> None:
        event = self._selected_event()
        self.edit_btn.setEnabled(event is not None)
        self.delete_btn.setEnabled(event is not None)
        self.open_asset_btn.setEnabled(bool(event and event.get("candidate_id")))

    def _create_event(self) -> None:
        self._show_event_dialog(None)

    def _edit_selected(self) -> None:
        event = self._selected_event()
        if event is not None:
            self._show_event_dialog(event)

    def _show_event_dialog(self, event: dict[str, object] | None) -> None:
        dialog = CalendarEventDialog(
            self.database_manager,
            self.calendar.selectedDate(),
            event=event,
            default_candidate_id=self.current_candidate_id,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if event:
            values["event_id"] = int(event["id"])
        try:
            self.database_manager.save_calendar_event(**values)
        except Exception as exc:
            QMessageBox.warning(self, "Unable to save event", str(exc))
            return
        self.refresh()

    def _delete_selected(self) -> None:
        event = self._selected_event()
        if event is None:
            return
        if QMessageBox.question(self, "Delete event", f"Delete '{event['title']}'?") != QMessageBox.StandardButton.Yes:
            return
        self.database_manager.delete_calendar_event(int(event["id"]))
        self.refresh()

    def _open_selected_asset(self) -> None:
        event = self._selected_event()
        candidate_id = event.get("candidate_id") if event else None
        if candidate_id is not None:
            self.asset_open_requested.emit(int(candidate_id))