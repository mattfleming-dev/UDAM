from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.ui.widgets.filter_sidebar_widget import FilterSidebarWidget
from universal_stock_dam.ui.widgets.thumbnail_card_widget import ThumbnailCardWidget
from universal_stock_dam.core.raw_loader import extract_preview_rgb, is_raw_format


class GalleryView(QWidget):
    candidate_selected = Signal(int)
    page_requested = Signal(int)
    performance_updated = Signal(dict)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_page = 1
        self.total_items = 0
        self.page_size = 60
        self.thumbnail_cache_enabled = True
        self._thumbnail_cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._thumbnail_cache_max_items = 1200
        self._thumbnail_cache_auto_enabled = True
        self._thumbnail_cache_auto_threshold_pct = 90.0
        self._thumbnail_cache_auto_keep_ratio = 0.5
        self._animations: list[QPropertyAnimation] = []
        self._cache_hits_total = 0
        self._cache_misses_total = 0
        self._cache_hits_page = 0
        self._cache_misses_page = 0
        self._cache_auto_runs_total = 0
        self._cache_auto_removed_total = 0
        self._cache_auto_runs_page = 0
        self._cache_auto_removed_page = 0
        self._last_candidates: list[dict[str, object]] = []
        self._candidate_lookup: dict[int, dict[str, object]] = {}
        self._active_candidate_id: int | None = None

        root = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.view_toggle = QComboBox()
        self.view_toggle.addItems(["Single", "Grid", "List"])
        self.view_toggle.setCurrentText("Single")
        self.preview_size_toggle = QComboBox()
        self.preview_size_toggle.addItems(["Small", "Medium", "Large"])
        self.preview_size_toggle.setCurrentText("Medium")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Newest", "Oldest", "Quality High-Low", "Quality Low-High"])
        self.refresh_btn = QPushButton("Refresh")
        self.ai_selected_btn = QPushButton("AI Tag Selected")
        self.rename_selected_btn = QPushButton("Batch Rename")
        self.move_selected_btn = QPushButton("Move Selected")

        toolbar.addWidget(QLabel("View"))
        toolbar.addWidget(self.view_toggle)
        toolbar.addWidget(QLabel("Preview Size"))
        toolbar.addWidget(self.preview_size_toggle)
        toolbar.addWidget(QLabel("Sort"))
        toolbar.addWidget(self.sort_combo)
        toolbar.addWidget(self.ai_selected_btn)
        toolbar.addWidget(self.rename_selected_btn)
        toolbar.addWidget(self.move_selected_btn)
        toolbar.addStretch(1)
        toolbar.addWidget(self.refresh_btn)
        root.addLayout(toolbar)

        self.filters = FilterSidebarWidget()
        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setIconSize(QPixmap(220, 140).size())
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setMovement(QListWidget.Static)
        self.list.setSpacing(10)

        self.single_view = QFrame()
        single_layout = QVBoxLayout(self.single_view)
        single_layout.setContentsMargins(16, 10, 16, 10)
        single_layout.setSpacing(10)
        self.single_meta = QLabel("Select an image from the filmstrip")
        self.single_image = QLabel("No preview")
        self.single_image.setAlignment(Qt.AlignCenter)
        self.single_image.setMinimumHeight(360)
        single_layout.addWidget(self.single_meta)
        single_layout.addWidget(self.single_image, 1)

        root.addWidget(self.single_view, 1)
        root.addWidget(self.list, 1)

        pager = QHBoxLayout()
        self.prev_btn = QPushButton("Prev")
        self.next_btn = QPushButton("Next")
        self.page_label = QLabel("Page 1")
        self.total_label = QLabel("0 items")

        pager.addWidget(self.prev_btn)
        pager.addWidget(self.next_btn)
        pager.addWidget(self.page_label)
        pager.addStretch(1)
        pager.addWidget(self.total_label)
        root.addLayout(pager)

        self.list.itemDoubleClicked.connect(self._on_item_activated)
        self.list.itemClicked.connect(self._on_item_activated)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)
        self.prev_btn.clicked.connect(lambda: self._request_page(self.current_page - 1))
        self.next_btn.clicked.connect(lambda: self._request_page(self.current_page + 1))
        self.view_toggle.currentIndexChanged.connect(self._apply_view_mode)
        self.preview_size_toggle.currentIndexChanged.connect(self._on_preview_size_changed)
        self._apply_view_mode()

    def _preview_dimensions(self) -> tuple[int, int, int, int]:
        size = self.preview_size_toggle.currentText()
        if size == "Small":
            return 160, 100, 210, 190
        if size == "Large":
            return 320, 200, 360, 300
        return 220, 140, 268, 242

    def _on_preview_size_changed(self) -> None:
        self._apply_view_mode()
        self.page_requested.emit(self.current_page)

    def set_thumbnail_cache_enabled(self, enabled: bool) -> None:
        self.thumbnail_cache_enabled = bool(enabled)
        if not self.thumbnail_cache_enabled:
            self._thumbnail_cache.clear()

    def set_thumbnail_cache_max_items(self, max_items: int) -> None:
        self._thumbnail_cache_max_items = max(50, int(max_items))
        while len(self._thumbnail_cache) > self._thumbnail_cache_max_items:
            self._thumbnail_cache.popitem(last=False)

    def set_thumbnail_cache_auto_maintenance(
        self,
        *,
        enabled: bool,
        threshold_pct: float,
        keep_ratio: float,
    ) -> None:
        self._thumbnail_cache_auto_enabled = bool(enabled)
        self._thumbnail_cache_auto_threshold_pct = min(100.0, max(50.0, float(threshold_pct)))
        self._thumbnail_cache_auto_keep_ratio = min(0.95, max(0.1, float(keep_ratio)))

    def clear_thumbnail_cache(self) -> None:
        self._thumbnail_cache.clear()

    def trim_thumbnail_cache(self, keep_ratio: float = 0.5) -> int:
        if not self._thumbnail_cache:
            return 0
        bounded_ratio = min(1.0, max(0.05, float(keep_ratio)))
        target = max(1, int(len(self._thumbnail_cache) * bounded_ratio))
        removed = 0
        while len(self._thumbnail_cache) > target:
            self._thumbnail_cache.popitem(last=False)
            removed += 1
        return removed

    def reset_thumbnail_cache_metrics(self) -> None:
        self._cache_hits_total = 0
        self._cache_misses_total = 0
        self._cache_hits_page = 0
        self._cache_misses_page = 0
        self._cache_auto_runs_total = 0
        self._cache_auto_removed_total = 0
        self._cache_auto_runs_page = 0
        self._cache_auto_removed_page = 0

    def _apply_auto_cache_maintenance(self) -> None:
        if not self.thumbnail_cache_enabled:
            return
        if not self._thumbnail_cache_auto_enabled:
            return
        if self._thumbnail_cache_max_items <= 0:
            return
        occupancy = len(self._thumbnail_cache) * 100.0 / float(self._thumbnail_cache_max_items)
        if occupancy < self._thumbnail_cache_auto_threshold_pct:
            return
        removed = self.trim_thumbnail_cache(self._thumbnail_cache_auto_keep_ratio)
        if removed > 0:
            self._cache_auto_runs_total += 1
            self._cache_auto_removed_total += removed
            self._cache_auto_runs_page += 1
            self._cache_auto_removed_page += removed

    def _apply_view_mode(self) -> None:
        thumb_w, thumb_h, cell_w, cell_h = self._preview_dimensions()
        self.list.setIconSize(QSize(thumb_w, thumb_h))
        mode = self.view_toggle.currentText()

        if mode == "Single":
            self.single_view.setVisible(True)
            self.list.setVisible(False)
            self._render_single_candidate()
            return

        self.single_view.setVisible(False)
        self.list.setVisible(True)

        if mode == "Grid":
            self.list.setViewMode(QListWidget.IconMode)
            self.list.setWordWrap(True)
            self.list.setGridSize(QSize(cell_w, cell_h))
        else:
            self.list.setViewMode(QListWidget.ListMode)
            self.list.setWordWrap(False)
            self.list.setGridSize(QSize())

    def set_active_candidate(self, candidate_id: int) -> None:
        self._active_candidate_id = int(candidate_id)
        self._render_single_candidate()

    def select_candidate_item(self, candidate_id: int) -> None:
        self.list.blockSignals(True)
        for index in range(self.list.count()):
            item = self.list.item(index)
            current_id = item.data(Qt.UserRole)
            if isinstance(current_id, int) and current_id == int(candidate_id):
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                break
        self.list.blockSignals(False)

    def _render_single_candidate(self) -> None:
        if self.view_toggle.currentText() != "Single":
            return

        if not self._last_candidates:
            self.single_meta.setText("No images on this page")
            self.single_image.setPixmap(QPixmap())
            self.single_image.setText("No preview")
            return

        candidate = None
        if self._active_candidate_id is not None:
            candidate = self._candidate_lookup.get(self._active_candidate_id)
        if candidate is None:
            candidate = self._last_candidates[0]
            self._active_candidate_id = int(candidate["id"])

        name = str(candidate.get("filename", "Untitled"))
        ext = str(candidate.get("ext", "")).upper()
        quality = candidate.get("overall_score")
        quality_text = "-" if quality is None else f"{float(quality):.1f}"
        self.single_meta.setText(f"{name} [{ext}]  Quality: {quality_text}")

        path_text = str(candidate.get("path", ""))
        preview_w = max(640, self.single_image.width() - 24)
        preview_h = max(360, self.single_image.height() - 24)
        thumb = self._load_scaled_thumbnail(path_text, preview_w, preview_h)
        if thumb.isNull():
            self.single_image.setPixmap(QPixmap())
            self.single_image.setText("No Preview")
        else:
            self.single_image.setText("")
            self.single_image.setPixmap(thumb)

    def _thumbnail_key(self, image_path: str, width: int, height: int) -> str:
        return f"{Path(image_path)}::{width}x{height}"

    @staticmethod
    def _load_raw_preview_pixmap(image_path: str) -> QPixmap:
        try:
            rgb = extract_preview_rgb(image_path, half_size=True)
        except Exception:
            return QPixmap()

        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return QPixmap()

        height, width, _ = rgb.shape
        bytes_per_line = rgb.strides[0]
        image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888)
        # Copy detaches from numpy memory that goes out of scope after this method.
        return QPixmap.fromImage(image.copy())

    def load_scaled_thumbnail(self, image_path: str, width: int, height: int) -> QPixmap:
        return self._load_scaled_thumbnail(image_path, width, height)

    def _load_scaled_thumbnail(self, image_path: str, width: int, height: int) -> QPixmap:
        cache_key = self._thumbnail_key(image_path, width, height)
        if self.thumbnail_cache_enabled and cache_key in self._thumbnail_cache:
            cached = self._thumbnail_cache.pop(cache_key)
            self._thumbnail_cache[cache_key] = cached
            self._cache_hits_total += 1
            self._cache_hits_page += 1
            return cached

        if is_raw_format(image_path):
            pixmap = self._load_raw_preview_pixmap(image_path)
        else:
            pixmap = QPixmap(image_path)

        if pixmap.isNull():
            return QPixmap()
        thumb = pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._cache_misses_total += 1
        self._cache_misses_page += 1

        if self.thumbnail_cache_enabled:
            self._thumbnail_cache[cache_key] = thumb
            while len(self._thumbnail_cache) > self._thumbnail_cache_max_items:
                self._thumbnail_cache.popitem(last=False)
            self._apply_auto_cache_maintenance()
        return thumb

    def _animate_page_repopulate(self, card_widgets: list[QWidget]) -> None:
        viewport_effect = QGraphicsOpacityEffect(self.list.viewport())
        self.list.viewport().setGraphicsEffect(viewport_effect)
        viewport_fade = QPropertyAnimation(viewport_effect, b"opacity", self)
        viewport_fade.setDuration(180)
        viewport_fade.setStartValue(0.78)
        viewport_fade.setEndValue(1.0)
        viewport_fade.setEasingCurve(QEasingCurve.InOutCubic)
        viewport_fade.finished.connect(lambda: self.list.viewport().setGraphicsEffect(None))
        self._animations.append(viewport_fade)
        viewport_fade.finished.connect(lambda: self._animations.remove(viewport_fade) if viewport_fade in self._animations else None)
        viewport_fade.start()

        for index, widget in enumerate(card_widgets[:24]):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(180)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(lambda w=widget: w.setGraphicsEffect(None))
            self._animations.append(anim)
            anim.finished.connect(lambda a=anim: self._animations.remove(a) if a in self._animations else None)
            QTimer.singleShot(index * 24, anim.start)

    def populate_candidates(
        self,
        candidates: list[dict[str, object]],
        total_items: int,
        page: int,
        page_size: int,
    ) -> None:
        self._last_candidates = list(candidates)
        self._candidate_lookup = {
            int(candidate["id"]): candidate
            for candidate in candidates
            if isinstance(candidate.get("id"), int)
        }
        if self._active_candidate_id is None and candidates:
            self._active_candidate_id = int(candidates[0]["id"])
        elif self._active_candidate_id not in self._candidate_lookup and candidates:
            self._active_candidate_id = int(candidates[0]["id"])

        start = perf_counter()
        self.list.clear()
        self.current_page = max(1, page)
        self.total_items = max(0, total_items)
        self.page_size = max(1, page_size)
        is_grid = self.view_toggle.currentText() == "Grid"
        card_widgets: list[QWidget] = []
        thumb_w, thumb_h, cell_w, cell_h = self._preview_dimensions()
        self._cache_hits_page = 0
        self._cache_misses_page = 0
        self._cache_auto_runs_page = 0
        self._cache_auto_removed_page = 0

        for candidate in candidates:
            name = str(candidate.get("filename", "Untitled"))
            quality = candidate.get("overall_score")
            quality_text = "-" if quality is None else f"{float(quality):.1f}"
            ext = str(candidate.get("ext", "")).upper()
            path_text = str(candidate.get("path", ""))
            candidate_id = int(candidate["id"])

            if is_grid:
                label = ""
            else:
                label = f"{name}   [{ext}]   Quality: {quality_text}"

            item = QListWidgetItem(label, self.list)
            item.setData(Qt.UserRole, candidate_id)

            if is_grid:
                thumb = self._load_scaled_thumbnail(path_text, thumb_w, thumb_h)
                flags: list[str] = []
                if bool(candidate.get("recommended", False)):
                    flags.append("Recommended")
                tags = candidate.get("tags", [])
                if isinstance(tags, list) and tags:
                    flags.append(f"{len(tags)} tags")

                card = ThumbnailCardWidget(
                    image_path=path_text,
                    title=f"{name} [{ext}]",
                    quality_score=float(quality) if isinstance(quality, (int, float)) else None,
                    is_favorite=bool(candidate.get("is_favorite", False)),
                    flags=flags,
                    preview_pixmap=thumb,
                )
                item.setSizeHint(QSize(cell_w - 18, cell_h - 14))
                self.list.setItemWidget(item, card)
                card_widgets.append(card)
            else:
                thumb = self._load_scaled_thumbnail(path_text, thumb_w, thumb_h)
                if not thumb.isNull():
                    item.setIcon(QIcon(thumb))

        total_pages = max(1, (self.total_items + self.page_size - 1) // self.page_size)
        self.page_label.setText(f"Page {self.current_page} / {total_pages}")
        self.total_label.setText(f"{self.total_items} items")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < total_pages)
        self._animate_page_repopulate(card_widgets)
        self._render_single_candidate()

        elapsed_ms = round((perf_counter() - start) * 1000, 1)
        page_total = self._cache_hits_page + self._cache_misses_page
        page_hit_rate = (self._cache_hits_page * 100.0 / page_total) if page_total > 0 else 0.0
        total_lookups = self._cache_hits_total + self._cache_misses_total
        total_hit_rate = (self._cache_hits_total * 100.0 / total_lookups) if total_lookups > 0 else 0.0
        self.performance_updated.emit(
            {
                "render_ms": elapsed_ms,
                "cache_enabled": self.thumbnail_cache_enabled,
                "cache_items": len(self._thumbnail_cache),
                "cache_max_items": self._thumbnail_cache_max_items,
                "cache_hits_page": self._cache_hits_page,
                "cache_misses_page": self._cache_misses_page,
                "cache_hit_rate_page": round(page_hit_rate, 1),
                "cache_hits_total": self._cache_hits_total,
                "cache_misses_total": self._cache_misses_total,
                "cache_hit_rate_total": round(total_hit_rate, 1),
                "cache_auto_runs_page": self._cache_auto_runs_page,
                "cache_auto_removed_page": self._cache_auto_removed_page,
                "cache_auto_runs_total": self._cache_auto_runs_total,
                "cache_auto_removed_total": self._cache_auto_removed_total,
            }
        )

    def populate(self, items: list[str]) -> None:
        self.list.clear()
        for item in items:
            QListWidgetItem(item, self.list)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        candidate_id = item.data(Qt.UserRole)
        if isinstance(candidate_id, int):
            self.candidate_selected.emit(candidate_id)

    def _on_selection_changed(self) -> None:
        current = self.list.currentItem()
        if current is None:
            return
        candidate_id = current.data(Qt.UserRole)
        if isinstance(candidate_id, int):
            self.candidate_selected.emit(candidate_id)

    def _request_page(self, page: int) -> None:
        if page < 1:
            return
        self.page_requested.emit(page)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_single_candidate()
