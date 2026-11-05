from __future__ import annotations

from datetime import datetime
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QUrl, Qt
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from universal_stock_dam.core.paths import data_path, models_dir
from universal_stock_dam.core.raw_loader import RAW_EXTENSIONS, STANDARD_IMAGE_EXTENSIONS
from universal_stock_dam.core.settings import load_settings, save_settings
from universal_stock_dam.db.manager import DatabaseManager
from universal_stock_dam.ui.views.catalog_view import CatalogView
from universal_stock_dam.ui.views.calendar_view import CalendarView
from universal_stock_dam.ui.views.collections_view import CollectionsView
from universal_stock_dam.ui.views.dashboard_view import DashboardView
from universal_stock_dam.ui.views.database_view import DatabaseView
from universal_stock_dam.ui.views.gallery_view import GalleryView
from universal_stock_dam.ui.views.inspector_view import InspectorView
from universal_stock_dam.ui.views.preview_view import PreviewView
from universal_stock_dam.ui.views.quality_view import QualityView
from universal_stock_dam.ui.views.settings_view import SettingsView
from universal_stock_dam.ui.views.tags_view import TagsView
from universal_stock_dam.ui.widgets.collapsible_section import CollapsibleSection
from universal_stock_dam.ui.widgets.folder_tree_widget import FolderTreeWidget
from universal_stock_dam.workers.ai_worker import AITaggingWorker
from universal_stock_dam.workers.catalog_scanner import CatalogScannerWorker
from universal_stock_dam.workers.export_worker import BatchExportWorker
from universal_stock_dam.workers.quality_worker import QualityBatchWorker

_ALL_IMAGE_EXTENSIONS = RAW_EXTENSIONS | STANDARD_IMAGE_EXTENSIONS


class MainWindow(QMainWindow):
    def __init__(self, db_manager: DatabaseManager, parent=None) -> None:
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings = load_settings()

        self.setWindowTitle("Universal Stock DAM")
        self.resize(1680, 1000)

        self._scanner_worker: CatalogScannerWorker | None = None
        self._quality_worker: QualityBatchWorker | None = None
        self._ai_worker: AITaggingWorker | None = None
        self._export_worker: BatchExportWorker | None = None
        self._last_ai_test_result: dict[str, object] | None = None
        self._last_selected_candidate_id: int | None = None
        self._panel_animations: list[QPropertyAnimation] = []
        self.gallery_page = 1
        self.gallery_page_size = 60
        # "library" = filmstrip driven by DB candidates; "folder" = driven by filesystem
        self._filmstrip_mode: str = "library"

        # ── Views ────────────────────────────────────────────────────────────
        self.preview_view = PreviewView()
        self.gallery_view = GalleryView()
        self.inspector_view = InspectorView()
        self.quality_view = QualityView()
        self.catalog_view = CatalogView()
        self.tags_view = TagsView()
        self.collections_view = CollectionsView()
        self.database_view = DatabaseView()
        self.dashboard_view = DashboardView()
        self.settings_view = SettingsView()
        self.calendar_view = CalendarView(db_manager)

        # ── Root layout ───────────────────────────────────────────────────────
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_top_bar())

        # ── Main 3-column splitter ────────────────────────────────────────────
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left: folder tree
        self.folder_tree = FolderTreeWidget()
        self.folder_tree.setMinimumWidth(160)
        self.main_splitter.addWidget(self.folder_tree)

        # Center: preview stack + filmstrip
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self.center_stack = QStackedWidget()
        self.center_stack.addWidget(self.preview_view)   # 0 — large single image
        self.center_stack.addWidget(self.gallery_view)   # 1 — grid / list browse
        self.center_stack.setCurrentIndex(0)
        center_layout.addWidget(self.center_stack, 1)

        self.filmstrip = self._build_filmstrip()
        center_layout.addWidget(self.filmstrip)
        self.main_splitter.addWidget(center)

        # Right: collapsible panels
        self.right_panel_scroll = self._build_right_panel()
        self.right_panel_tabs = QTabWidget()
        self.right_panel_tabs.addTab(self.right_panel_scroll, "Panels")
        self.right_panel_tabs.addTab(self.calendar_view, "Calendar")
        self.main_splitter.addWidget(self.right_panel_tabs)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([220, 1080, 420])
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)

        root_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(root)

        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

        self._wire_events()
        self._load_stylesheet()
        self._apply_settings_to_ui()
        self._refresh_gallery()
        self._refresh_database_stats()
        self._refresh_dashboard_and_quality()
        self._refresh_tags()
        self._refresh_collections()
        self._refresh_filter_options()

    # ── Layout builders ───────────────────────────────────────────────────────

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 6, 12, 6)

        self.title_label = QLabel("Universal Stock DAM")

        self.toggle_left_btn = QPushButton("Hide Folders")
        self.toggle_right_btn = QPushButton("Hide Panels")
        self.toggle_filmstrip_btn = QPushButton("Hide Filmstrip")

        self.browse_mode_btn = QPushButton("Browse")
        self.browse_mode_btn.setCheckable(True)
        self.browse_mode_btn.setToolTip("Switch between large preview and grid/list browse")

        self.ai_indicator = QLabel("⏳ AI Running…")
        self.ai_indicator.setObjectName("AIIndicator")
        self.ai_indicator.setVisible(False)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search filename, keywords, tags…")

        self.gallery_perf_label = QLabel("Render - ms")
        self.gallery_perf_label.setObjectName("GalleryPerfHud")
        self.gallery_perf_label.setProperty("perfLevel", "neutral")

        self.gallery_cache_label = QLabel("Cache -")
        self.gallery_cache_label.setObjectName("GalleryCacheHud")
        self.gallery_cache_label.setProperty("cacheLevel", "neutral")

        self.quick_stats = QLabel("0 images")

        layout.addWidget(self.title_label)
        layout.addWidget(self.toggle_left_btn)
        layout.addWidget(self.toggle_filmstrip_btn)
        layout.addWidget(self.browse_mode_btn)
        layout.addStretch(1)
        layout.addWidget(self.ai_indicator)
        layout.addWidget(self.search_box, 2)
        layout.addWidget(self.gallery_perf_label)
        layout.addWidget(self.gallery_cache_label)
        layout.addWidget(self.quick_stats)
        layout.addWidget(self.toggle_right_btn)
        return bar

    def _build_filmstrip(self) -> QFrame:
        filmstrip = QFrame()
        filmstrip.setObjectName("Filmstrip")

        layout = QVBoxLayout(filmstrip)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(4)

        header = QHBoxLayout()
        header.addWidget(QLabel("Filmstrip"))
        header.addStretch(1)
        self.filmstrip_hint = QLabel("Click a frame to preview — scroll horizontally to browse")
        header.addWidget(self.filmstrip_hint)
        layout.addLayout(header)

        self.filmstrip_list = QListWidget()
        self.filmstrip_list.setObjectName("FilmstripList")
        self.filmstrip_list.setViewMode(QListWidget.IconMode)
        self.filmstrip_list.setFlow(QListWidget.LeftToRight)
        self.filmstrip_list.setMovement(QListWidget.Static)
        self.filmstrip_list.setWrapping(False)
        self.filmstrip_list.setResizeMode(QListWidget.Adjust)
        self.filmstrip_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.filmstrip_list.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.filmstrip_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.filmstrip_list.setIconSize(QPixmap(96, 64).size())
        self.filmstrip_list.setFixedHeight(138)
        layout.addWidget(self.filmstrip_list)

        return filmstrip

    def _build_right_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        # AsNeeded is a safety net: with the panel widths below, fields should
        # normally fit, but if a section's content ever needs more room than
        # is available, a scrollbar appears instead of clipping past the edge.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setMinimumWidth(300)
        scroll.setMaximumWidth(560)
        scroll.setObjectName("RightPanelScroll")

        content = QWidget()
        content.setObjectName("RightPanelContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        def _section(title: str, widget: QWidget, collapsed: bool = False) -> CollapsibleSection:
            sec = CollapsibleSection(title, collapsed=collapsed)
            sec.add_widget(widget)
            layout.addWidget(sec)
            return sec

        self._inspector_section = _section("Inspector", self.inspector_view)
        self._collections_section = _section("Collections", self.collections_view, collapsed=True)
        self._settings_section = _section("Settings", self.settings_view, collapsed=True)
        self._database_section = _section("Database", self.database_view, collapsed=True)
        self._filters_section = _section("Filters", self.gallery_view.filters, collapsed=True)

        layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    # ── Event wiring ──────────────────────────────────────────────────────────

    def _wire_events(self) -> None:
        self.search_box.textChanged.connect(self._apply_search)
        self.toggle_left_btn.clicked.connect(self._toggle_left_panel)
        self.toggle_right_btn.clicked.connect(self._toggle_right_panel)
        self.toggle_filmstrip_btn.clicked.connect(self._toggle_filmstrip)
        self.browse_mode_btn.toggled.connect(self._on_browse_mode_toggled)

        self.folder_tree.folder_selected.connect(self._on_folder_selected)
        self.folder_tree.add_to_library_requested.connect(self._on_folder_add_to_library)

        self.catalog_view.start_scan.clicked.connect(self._start_catalog_scan)

        self.gallery_view.refresh_btn.clicked.connect(lambda: self._refresh_gallery(page=1))
        self.gallery_view.sort_combo.currentIndexChanged.connect(lambda _=0: self._refresh_gallery(page=1))
        self.gallery_view.filters.filters_changed.connect(lambda _=None: self._refresh_gallery(page=1))
        self.gallery_view.page_requested.connect(self._on_gallery_page_requested)
        self.gallery_view.candidate_selected.connect(self._on_gallery_candidate_selected)
        self.gallery_view.performance_updated.connect(self._on_gallery_performance_updated)
        self.gallery_view.ai_selected_btn.clicked.connect(self._ai_tag_selected_gallery)

        self.filmstrip_list.itemClicked.connect(self._on_filmstrip_item_activated)
        self.filmstrip_list.itemDoubleClicked.connect(self._on_filmstrip_item_activated)

        self.database_view.backup_btn.clicked.connect(self._on_create_backup)
        self.database_view.restore_btn.clicked.connect(self._on_restore_backup)
        self.database_view.reset_btn.clicked.connect(self._on_reset_database)
        self.database_view.clean_missing_btn.clicked.connect(self._on_clean_missing)
        self.database_view.vacuum_btn.clicked.connect(self._on_vacuum)
        self.database_view.enforce_cache_btn.clicked.connect(self._on_enforce_cache)
        self.database_view.find_duplicates_btn.clicked.connect(self._on_find_duplicates)

        self.dashboard_view.quick_button.clicked.connect(self._analyze_unanalyzed)
        self.dashboard_view.ai_quick_button.clicked.connect(self._ai_tag_unanalyzed)
        self.quality_view.analyze_btn.clicked.connect(self._analyze_selected_image)
        self.quality_view.analyze_unanalyzed.clicked.connect(self._analyze_unanalyzed)
        self.quality_view.reanalyze_all.clicked.connect(self._reanalyze_all)
        self.quality_view.ai_tag_unanalyzed.clicked.connect(self._ai_tag_unanalyzed)

        self.gallery_view.rename_selected_btn.clicked.connect(self._on_batch_rename_selected)
        self.gallery_view.move_selected_btn.clicked.connect(self._on_batch_move_selected)

        self.collections_view.create_btn.clicked.connect(self._on_create_collection)
        self.collections_view.save_btn.clicked.connect(self._on_save_collection)
        self.collections_view.save_search_btn.clicked.connect(self._on_save_search_collection)
        self.collections_view.open_btn.clicked.connect(self._on_open_collection)
        self.collections_view.edit_btn.clicked.connect(self._on_edit_collection)
        self.collections_view.delete_btn.clicked.connect(self._on_delete_collection)
        self.collections_view.assign_btn.clicked.connect(self._on_assign_selected_to_collection)
        self.collections_view.collections.currentItemChanged.connect(self._on_collection_selected)

        self.inspector_view.favorite_btn.clicked.connect(self._on_inspector_toggle_favorite)
        self.inspector_view.add_collection_btn.clicked.connect(self._on_inspector_add_to_collection)
        self.inspector_view.export_btn.clicked.connect(self._on_inspector_export)
        self.inspector_view.delete_btn.clicked.connect(self._on_inspector_delete)
        self.inspector_view.analyze_btn.clicked.connect(self._analyze_selected_image)
        self.inspector_view.ai_generate_requested.connect(self._generate_ai_metadata_selected_image)
        self.inspector_view.save_data_btn.clicked.connect(self._on_inspector_save_data)
        self.calendar_view.asset_open_requested.connect(self._on_calendar_asset_open)
        self.right_panel_tabs.currentChanged.connect(lambda _index: self.calendar_view.refresh())

        self.settings_view.save_btn.clicked.connect(self._save_settings)
        self.settings_view.reload_btn.clicked.connect(self._reload_settings)
        self.settings_view.refresh_models_requested.connect(self._on_refresh_ai_models)
        self.settings_view.test_provider_requested.connect(self._on_test_ai_provider)
        self.settings_view.save_test_profile_requested.connect(self._on_save_ai_test_profile)
        self.settings_view.clear_thumbnail_cache_requested.connect(self._on_clear_thumbnail_cache)
        self.settings_view.trim_thumbnail_cache_requested.connect(self._on_trim_thumbnail_cache)
        self.settings_view.reset_thumbnail_cache_stats_requested.connect(self._on_reset_thumbnail_cache_stats)
        self.settings_view.open_models_folder_btn.clicked.connect(self._on_open_models_folder)

        QShortcut("Ctrl+L", self, activated=self._toggle_left_panel)
        QShortcut("Ctrl+R", self, activated=self._toggle_right_panel)
        QShortcut("Ctrl+F", self, activated=self._toggle_filmstrip)
        QShortcut("Ctrl+B", self, activated=lambda: self.browse_mode_btn.toggle())

    # ── Panel toggles ─────────────────────────────────────────────────────────

    def _toggle_left_panel(self) -> None:
        sizes = self.main_splitter.sizes()
        if sizes[0] > 0:
            self.settings.ui_left_panel_collapsed = True
            self.main_splitter.setSizes([0, sizes[0] + sizes[1], sizes[2]])
        else:
            self.settings.ui_left_panel_collapsed = False
            self.main_splitter.setSizes([220, max(sizes[1] - 220, 300), sizes[2]])
        self.toggle_left_btn.setText(
            "Show Folders" if self.settings.ui_left_panel_collapsed else "Hide Folders"
        )
        save_settings(self.settings)

    def _toggle_right_panel(self) -> None:
        sizes = self.main_splitter.sizes()
        if sizes[2] > 0:
            self.settings.ui_right_panel_collapsed = True
            self.main_splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
        else:
            self.settings.ui_right_panel_collapsed = False
            self.main_splitter.setSizes([sizes[0], max(sizes[1] - 360, 300), 360])
        self.toggle_right_btn.setText(
            "Show Panels" if self.settings.ui_right_panel_collapsed else "Hide Panels"
        )
        save_settings(self.settings)

    def _toggle_filmstrip(self) -> None:
        self.settings.ui_filmstrip_collapsed = not self.settings.ui_filmstrip_collapsed
        self._animate_filmstrip(collapse=self.settings.ui_filmstrip_collapsed)
        self.toggle_filmstrip_btn.setText(
            "Show Filmstrip" if self.settings.ui_filmstrip_collapsed else "Hide Filmstrip"
        )
        save_settings(self.settings)

    def _animate_filmstrip(self, *, collapse: bool) -> None:
        target = 0 if collapse else 138
        if not collapse:
            self.filmstrip.setVisible(True)
        anim = QPropertyAnimation(self.filmstrip_list, b"maximumHeight", self)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.InOutCubic)
        anim.setStartValue(max(0, self.filmstrip_list.height()))
        anim.setEndValue(target)

        def _finish() -> None:
            if collapse:
                self.filmstrip.setVisible(False)
            self.filmstrip_list.setMaximumHeight(16777215)
            if anim in self._panel_animations:
                self._panel_animations.remove(anim)

        anim.finished.connect(_finish)
        self._panel_animations.append(anim)
        anim.start()

    def _on_browse_mode_toggled(self, checked: bool) -> None:
        self.center_stack.setCurrentIndex(1 if checked else 0)
        self.browse_mode_btn.setText("Preview" if checked else "Browse")

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self.main_splitter.sizes()
        if len(sizes) >= 3:
            self.settings.ui_splitter_sizes = [int(s) for s in sizes[:3]]
            save_settings(self.settings)

    # ── Folder tree ───────────────────────────────────────────────────────────

    def _on_folder_selected(self, path: str) -> None:
        self._filmstrip_mode = "folder"
        self._populate_filmstrip_from_folder(path)
        self.statusBar().showMessage(f"Browsing: {path}")

    def _populate_filmstrip_from_folder(self, folder_path: str) -> None:
        folder = Path(folder_path)
        if not folder.is_dir():
            return

        image_files = sorted(
            (f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in _ALL_IMAGE_EXTENSIONS),
            key=lambda f: f.name.lower(),
        )

        self.filmstrip_list.blockSignals(True)
        self.filmstrip_list.clear()

        for img_file in image_files:
            item = QListWidgetItem(img_file.name)
            item.setData(Qt.UserRole, str(img_file))
            thumb = self.gallery_view.load_scaled_thumbnail(str(img_file), 96, 64)
            if not thumb.isNull():
                item.setIcon(QIcon(thumb))
            self.filmstrip_list.addItem(item)

        self.filmstrip_list.blockSignals(False)
        self.quick_stats.setText(f"{len(image_files)} files")

        if self.filmstrip_list.count() > 0:
            self.filmstrip_list.setCurrentRow(0)
            first = self.filmstrip_list.item(0)
            if first:
                self.preview_view.set_image(str(first.data(Qt.UserRole)))
                self.center_stack.setCurrentIndex(0)
                if self.browse_mode_btn.isChecked():
                    self.browse_mode_btn.setChecked(False)

    def _on_folder_add_to_library(self, path: str) -> None:
        if self._scanner_worker is not None and self._scanner_worker.isRunning():
            self.statusBar().showMessage("Scan already running")
            return
        self._scanner_worker = CatalogScannerWorker(
            database_manager=self.db_manager,
            folder_path=path,
            recursive=True,
            generate_thumbnails=True,
            thumbnail_root=self.settings.thumbnail_cache_dir,
            parent=self,
        )
        self._scanner_worker.progress_updated.connect(self._on_scan_progress)
        self._scanner_worker.scan_complete.connect(self._on_scan_complete)
        self._scanner_worker.start()
        self.statusBar().showMessage(f"Scanning: {path}")

    # ── Settings ──────────────────────────────────────────────────────────────

    def _apply_settings_to_ui(self) -> None:
        self.settings_view.set_settings(self.settings)
        current_stock_site = self.inspector_view.stock_site.currentText()
        self.inspector_view.set_stock_sites(self.settings.stock_sites, current=current_stock_site)
        self.gallery_view.set_thumbnail_cache_enabled(self.settings.thumbnail_cache_enabled)
        self.gallery_view.set_thumbnail_cache_max_items(self.settings.thumbnail_cache_max_items)
        self.gallery_view.set_thumbnail_cache_auto_maintenance(
            enabled=self.settings.thumbnail_cache_auto_maintenance,
            threshold_pct=self.settings.thumbnail_cache_auto_trim_threshold_pct,
            keep_ratio=self.settings.thumbnail_cache_auto_keep_ratio,
        )
        self._on_refresh_ai_models()
        self._refresh_filter_options()

        splitter_sizes = [v for v in self.settings.ui_splitter_sizes if isinstance(v, int) and v >= 0]
        if len(splitter_sizes) >= 3 and sum(splitter_sizes) > 0:
            self.main_splitter.setSizes(splitter_sizes[:3])

        self.filmstrip.setVisible(not self.settings.ui_filmstrip_collapsed)
        self.toggle_left_btn.setText(
            "Show Folders" if self.settings.ui_left_panel_collapsed else "Hide Folders"
        )
        self.toggle_right_btn.setText(
            "Show Panels" if self.settings.ui_right_panel_collapsed else "Hide Panels"
        )
        self.toggle_filmstrip_btn.setText(
            "Show Filmstrip" if self.settings.ui_filmstrip_collapsed else "Hide Filmstrip"
        )

    def _save_settings(self) -> None:
        incoming = self.settings_view.read_settings()
        incoming.ai_test_profiles = list(self.settings.ai_test_profiles)
        incoming.ai_last_test_profile = self.settings.ai_last_test_profile
        incoming.ui_left_panel_collapsed = self.settings.ui_left_panel_collapsed
        incoming.ui_filmstrip_collapsed = self.settings.ui_filmstrip_collapsed
        incoming.ui_right_panel_collapsed = self.settings.ui_right_panel_collapsed
        incoming.ui_splitter_sizes = list(self.settings.ui_splitter_sizes)
        self.settings = incoming
        current_stock_site = self.inspector_view.stock_site.currentText()
        self.inspector_view.set_stock_sites(self.settings.stock_sites, current=current_stock_site)
        self.gallery_view.set_thumbnail_cache_enabled(self.settings.thumbnail_cache_enabled)
        self.gallery_view.set_thumbnail_cache_max_items(self.settings.thumbnail_cache_max_items)
        self.gallery_view.set_thumbnail_cache_auto_maintenance(
            enabled=self.settings.thumbnail_cache_auto_maintenance,
            threshold_pct=self.settings.thumbnail_cache_auto_trim_threshold_pct,
            keep_ratio=self.settings.thumbnail_cache_auto_keep_ratio,
        )
        path = save_settings(self.settings)
        self.statusBar().showMessage(f"Settings saved: {path}")

    def _reload_settings(self) -> None:
        self.settings = load_settings()
        self._apply_settings_to_ui()
        self.statusBar().showMessage("Settings reloaded")

    # ── Gallery / library ─────────────────────────────────────────────────────

    def _apply_search(self, _text: str) -> None:
        self._refresh_gallery(page=1)

    def _start_catalog_scan(self) -> None:
        selected = self.catalog_view.selected_path()
        path = Path(selected)
        if not path.exists():
            self.statusBar().showMessage("Select a valid folder in the Library section")
            return
        if path.is_file():
            path = path.parent
        if self._scanner_worker is not None and self._scanner_worker.isRunning():
            self.statusBar().showMessage("Catalog scan already running")
            return
        self.catalog_view.log.append(f"Scanning: {path}")
        self._scanner_worker = CatalogScannerWorker(
            database_manager=self.db_manager,
            folder_path=str(path),
            recursive=self.catalog_view.recursive.isChecked(),
            generate_thumbnails=True,
            thumbnail_root=self.settings.thumbnail_cache_dir,
            parent=self,
        )
        self._scanner_worker.progress_updated.connect(self._on_scan_progress)
        self._scanner_worker.scan_complete.connect(self._on_scan_complete)
        self._scanner_worker.start()

    def _on_scan_progress(self, index: int, total: int, message: str) -> None:
        percent = 0 if total <= 0 else int(index * 100 / total)
        self.catalog_view.progress.setValue(percent)
        self.catalog_view.log.append(message)
        self.statusBar().showMessage(message)

    def _on_scan_complete(self, summary: dict) -> None:
        if "error" in summary:
            self.catalog_view.log.append(summary["error"])
            self.statusBar().showMessage(summary["error"])
            return
        self.catalog_view.log.append(
            f"Scan complete: added={summary.get('added', 0)}, failed={summary.get('failed', 0)}"
        )
        self.statusBar().showMessage("Scan complete")
        self._filmstrip_mode = "library"
        self._refresh_gallery(page=1)
        self._refresh_database_stats()
        self._refresh_dashboard_and_quality()
        self._refresh_tags()
        self._refresh_collections()

    def _current_candidate_selection_id(self) -> int | None:
        if self.inspector_view.current_candidate_id is not None:
            return self.inspector_view.current_candidate_id
        if self._last_selected_candidate_id is not None:
            return self._last_selected_candidate_id
        return None

    def _restore_selected_candidate(self, candidate_id: int | None) -> None:
        if candidate_id is None:
            return
        self._last_selected_candidate_id = candidate_id
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        self._on_gallery_candidate_selected(candidate_id)

    def _refresh_gallery(self, page: int | None = None) -> None:
        if page is not None:
            self.gallery_page = max(1, page)

        filters = self._collect_gallery_filters()
        rows, total = self.db_manager.query_candidates(
            page=self.gallery_page,
            page_size=self.gallery_page_size,
            min_quality=filters["min_quality"],
            max_quality=filters["max_quality"],
            formats=filters["formats"],
            sort=filters["sort"],
            search=self.search_box.text().strip(),
            tag_query=str(filters.get("tag_query", "")),
            collection_id=filters.get("collection_id"),
            favorite_only=bool(filters.get("favorite_only", False)),
            recommended_only=bool(filters.get("recommended_only", False)),
            camera_query=str(filters.get("camera_query", "")),
            lens_query=str(filters.get("lens_query", "")),
        )

        payload = []
        for candidate in rows:
            quality_score = candidate.quality.overall_score if candidate.quality else None
            payload.append({
                "id": candidate.id,
                "filename": candidate.filename,
                "ext": candidate.ext,
                "path": candidate.path,
                "overall_score": quality_score,
                "is_favorite": candidate.is_favorite,
                "recommended": candidate.recommended,
                "tags": [tag.name for tag in candidate.tags],
            })

        self.gallery_view.populate_candidates(
            candidates=payload,
            total_items=total,
            page=self.gallery_page,
            page_size=self.gallery_page_size,
        )
        self.quick_stats.setText(f"{total} images")

        if self._filmstrip_mode == "library":
            self._populate_filmstrip(payload)
            selected_id = self._current_candidate_selection_id()
            if selected_id is None and payload:
                selected_id = int(payload[0]["id"])
            if selected_id is not None:
                self._on_gallery_candidate_selected(selected_id)

    def _on_gallery_performance_updated(self, payload: dict) -> None:
        render_ms = float(payload.get("render_ms", 0.0))
        cache_enabled = bool(payload.get("cache_enabled", False))
        perf_level = "good" if render_ms < 35 else ("warn" if render_ms <= 80 else "critical")
        self.gallery_perf_label.setProperty("perfLevel", perf_level)
        self.gallery_perf_label.style().unpolish(self.gallery_perf_label)
        self.gallery_perf_label.style().polish(self.gallery_perf_label)

        if not cache_enabled:
            self.gallery_perf_label.setText(f"Render {render_ms:.1f} ms | Cache off")
            self.gallery_cache_label.setText("Cache off")
            return

        page_hit_rate = float(payload.get("cache_hit_rate_page", 0.0))
        cache_items = int(payload.get("cache_items", 0))
        cache_max = int(payload.get("cache_max_items", 0))
        self.gallery_perf_label.setText(f"Render {render_ms:.1f} ms")

        cache_level = "good" if page_hit_rate >= 70 else ("warn" if page_hit_rate >= 40 else "critical")
        self.gallery_cache_label.setText(f"Cache {page_hit_rate:.0f}% ({cache_items}/{cache_max})")
        self.gallery_cache_label.setProperty("cacheLevel", cache_level)
        self.gallery_cache_label.style().unpolish(self.gallery_cache_label)
        self.gallery_cache_label.style().polish(self.gallery_cache_label)

        self.settings_view.set_cache_status(
            f"Enabled | items={cache_items}/{cache_max} | "
            f"page={page_hit_rate:.0f}% | total={float(payload.get('cache_hit_rate_total', 0)):.0f}%"
        )

    def _populate_filmstrip(self, candidates: list[dict[str, object]]) -> None:
        self.filmstrip_list.blockSignals(True)
        self.filmstrip_list.clear()

        for candidate in candidates:
            candidate_id = int(candidate["id"])
            name = str(candidate.get("filename", "Untitled"))
            ext = str(candidate.get("ext", "")).upper()
            item = QListWidgetItem(f"{name}\n[{ext}]")
            item.setData(Qt.UserRole, candidate_id)
            path_text = str(candidate.get("path", ""))
            thumb = self.gallery_view.load_scaled_thumbnail(path_text, 96, 64)
            if not thumb.isNull():
                item.setIcon(QIcon(thumb))
            self.filmstrip_list.addItem(item)

        if self._last_selected_candidate_id is not None:
            self._select_filmstrip_item(self._last_selected_candidate_id)
        elif self.filmstrip_list.count() > 0:
            self.filmstrip_list.setCurrentRow(0)

        self.filmstrip_list.blockSignals(False)

    def _select_filmstrip_item(self, candidate_id: int) -> None:
        for index in range(self.filmstrip_list.count()):
            item = self.filmstrip_list.item(index)
            current_id = item.data(Qt.UserRole)
            if isinstance(current_id, int) and current_id == candidate_id:
                self.filmstrip_list.setCurrentItem(item)
                self.filmstrip_list.scrollToItem(item, QAbstractItemView.PositionAtCenter)
                return

    def _on_filmstrip_item_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if self._filmstrip_mode == "folder":
            path = str(data)
            self.preview_view.set_image(path)
            if self.center_stack.currentIndex() != 0:
                self.center_stack.setCurrentIndex(0)
                self.browse_mode_btn.setChecked(False)
            self.statusBar().showMessage(Path(path).name)
        elif isinstance(data, int):
            self._on_gallery_candidate_selected(data)

    def _on_gallery_candidate_selected(self, candidate_id: int) -> None:
        self._last_selected_candidate_id = candidate_id
        self.calendar_view.set_current_candidate(candidate_id)
        self._filmstrip_mode = "library"
        self.gallery_view.set_active_candidate(candidate_id)
        self.gallery_view.select_candidate_item(candidate_id)
        self._select_filmstrip_item(candidate_id)

        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            self.statusBar().showMessage(f"Candidate not found: {candidate_id}")
            return

        self.preview_view.set_image(candidate.path)
        if self.center_stack.currentIndex() != 0:
            self.center_stack.setCurrentIndex(0)
            self.browse_mode_btn.setChecked(False)

        metrics: dict[str, object] = {}
        overall_score = None
        if candidate.quality is not None:
            overall_score = candidate.quality.overall_score
            metrics = {
                "overall_score": candidate.quality.overall_score,
                "sharpness": candidate.quality.sharpness,
                "contrast": candidate.quality.contrast,
                "exposure": candidate.quality.exposure,
                "noise_level": candidate.quality.noise_level,
                "dynamic_range": candidate.quality.dynamic_range,
                "edge_density": candidate.quality.edge_density,
                "color_cast_deviation": candidate.quality.color_cast_deviation,
            }

        title = ""
        description = ""
        keywords: list[str] = []
        stock_site = ""
        stock_notes = ""
        stock_location = ""
        stock_usage_notes = ""
        exif_payload: dict = {}
        if candidate.vision is not None:
            title = candidate.vision.title
            description = candidate.vision.description
            keywords = candidate.vision.keywords
            stock_site = getattr(candidate.vision, "stock_site", "") or ""
            stock_notes = getattr(candidate.vision, "stock_notes", "") or ""
            stock_location = getattr(candidate.vision, "stock_location", "") or ""
            stock_usage_notes = getattr(candidate.vision, "stock_usage_notes", "") or ""
            exif_payload = candidate.vision.exif_data or {}

        self.inspector_view.set_candidate({
            "candidate_id": candidate.id,
            "filename": candidate.filename,
            "path": candidate.path,
            "overall_score": overall_score,
            "metrics": metrics,
            "title": title,
            "description": description,
            "keywords": keywords,
            "stock_site": stock_site,
            "stock_notes": stock_notes,
            "stock_location": stock_location,
            "stock_usage_notes": stock_usage_notes,
            "exif": {
                "camera_make": exif_payload.get("camera_make") or "Unavailable",
                "camera_model": exif_payload.get("camera_model") or "Unavailable",
                "lens": exif_payload.get("lens") or "Unavailable",
                "iso": exif_payload.get("iso") or "Unavailable",
                "aperture": exif_payload.get("aperture") or "Unavailable",
                "focal_length": exif_payload.get("focal_length") or "Unavailable",
                "shutter_speed": exif_payload.get("shutter_speed") or "Unavailable",
            },
        })

        # Populate per-image quality panel
        self.quality_view.set_quality(candidate.path, overall_score, metrics)

    def _on_calendar_asset_open(self, candidate_id: int) -> None:
        self.right_panel_tabs.setCurrentWidget(self.right_panel_scroll)
        self._on_gallery_candidate_selected(candidate_id)

    def _on_gallery_page_requested(self, page: int) -> None:
        self._refresh_gallery(page=page)

    def _selected_collection_item(self) -> QListWidgetItem | None:
        return self.collections_view.collections.currentItem()

    def _refresh_database_stats(self) -> None:
        stats = self.db_manager.get_database_stats()
        self.database_view.set_stats(stats)

    def _refresh_dashboard_and_quality(self) -> None:
        stats = self.db_manager.get_database_stats()
        bins = self.db_manager.get_quality_histogram(bin_count=10)
        buckets = self.db_manager.get_quality_buckets(limit_per_bucket=200)
        self.dashboard_view.set_metrics(
            total_images=int(stats.get("images", 0)),
            avg_quality=float(stats.get("avg_quality", 0.0)),
            analyzed_pct=float(stats.get("analyzed_pct", 0.0)),
            storage_mb=float(stats.get("db_size_mb", 0.0)),
        )
        self.dashboard_view.set_histogram_bins(bins)
        self.quality_view.set_histogram_bins(bins)
        self.quality_view.set_categories(buckets)

    # ── Thumbnail cache ───────────────────────────────────────────────────────

    def _on_clear_thumbnail_cache(self) -> None:
        self.gallery_view.clear_thumbnail_cache()
        self.statusBar().showMessage("In-memory thumbnail cache cleared")
        self._refresh_gallery(page=self.gallery_page)

    def _on_trim_thumbnail_cache(self) -> None:
        removed = self.gallery_view.trim_thumbnail_cache(keep_ratio=self.settings.thumbnail_cache_auto_keep_ratio)
        self.statusBar().showMessage(f"Thumbnail cache trimmed: {removed} items removed")
        self._refresh_gallery(page=self.gallery_page)

    def _on_reset_thumbnail_cache_stats(self) -> None:
        self.gallery_view.reset_thumbnail_cache_metrics()
        self.statusBar().showMessage("Cache stats reset")
        self._refresh_gallery(page=self.gallery_page)

    # ── Filters ───────────────────────────────────────────────────────────────

    def _refresh_filter_options(self) -> None:
        try:
            self.gallery_view.filters.set_collection_options(self.db_manager.list_collection_summaries())
        except Exception:
            pass

    def _collect_gallery_filters(self) -> dict[str, object]:
        f = self.gallery_view.filters
        formats: list[str] = []
        if f.jpg_cb.isChecked():
            formats.extend(["jpg", "jpeg"])
        if f.png_cb.isChecked():
            formats.append("png")
        if f.raw_cb.isChecked():
            formats.extend(["raf", "dng", "arw", "cr2", "cr3", "nef", "orf", "rw2", "pef", "raw"])

        sort_label = self.gallery_view.sort_combo.currentText()
        sort = {"Oldest": "oldest", "Quality High-Low": "quality_desc", "Quality Low-High": "quality_asc"}.get(
            sort_label, "newest"
        )
        return {
            "min_quality": int(f.min_quality.value()),
            "max_quality": int(f.max_quality.value()),
            "formats": formats,
            "sort": sort,
            "favorite_only": f.favorite_only.isChecked(),
            "recommended_only": f.recommended_only.isChecked(),
            "tag_query": f.tag_query.text().strip(),
            "collection_id": f.collection_combo.currentData(),
            "camera_query": f.camera_query.text().strip(),
            "lens_query": f.lens_query.text().strip(),
        }

    def _current_gallery_search_spec(self) -> dict[str, object]:
        spec = self._collect_gallery_filters()
        spec["search"] = self.search_box.text().strip()
        return spec

    def _apply_gallery_search_spec(self, spec: dict[str, object]) -> None:
        self.search_box.setText(str(spec.get("search", "")))
        f = self.gallery_view.filters
        f.min_quality.setValue(int(spec.get("min_quality", 0) or 0))
        f.max_quality.setValue(int(spec.get("max_quality", 100) or 100))
        formats = [str(x).lower() for x in spec.get("formats", []) if str(x).strip()]
        f.jpg_cb.setChecked(any(x in {"jpg", "jpeg"} for x in formats))
        f.raw_cb.setChecked(any(x in {"raf", "dng", "arw", "cr2", "cr3", "nef", "orf", "rw2", "pef", "raw"} for x in formats))
        f.png_cb.setChecked("png" in formats)
        f.favorite_only.setChecked(bool(spec.get("favorite_only", False)))
        f.recommended_only.setChecked(bool(spec.get("recommended_only", False)))
        f.tag_query.setText(str(spec.get("tag_query", "")))
        f.camera_query.setText(str(spec.get("camera_query", "")))
        f.lens_query.setText(str(spec.get("lens_query", "")))
        cid = spec.get("collection_id")
        if cid is not None and f.collection_combo.findData(cid) >= 0:
            f.collection_combo.setCurrentIndex(f.collection_combo.findData(cid))
        sort = str(spec.get("sort", "newest"))
        self.gallery_view.sort_combo.setCurrentText(
            {"oldest": "Oldest", "quality_desc": "Quality High-Low", "quality_asc": "Quality Low-High"}.get(sort, "Newest")
        )
        self._refresh_gallery(page=1)

    # ── AI models / provider ──────────────────────────────────────────────────

    def _discover_local_gguf_models(self, current_hint: str = "") -> list[str]:
        from universal_stock_dam.core.paths import models_dir, resource_path
        from universal_stock_dam.core.ai_provider import LlamaCppProvider

        roots = [
            str(Path(__file__).resolve().parents[1] / "models"),
            str(resource_path("resources")),
            str(models_dir()),
        ]
        if current_hint.strip():
            roots.append(current_hint.strip())
        return LlamaCppProvider.list_local_gguf_models(*roots)

    def _on_refresh_ai_models(self) -> None:
        snapshot = self.settings_view.read_settings()
        gguf_models = self._discover_local_gguf_models(snapshot.llamacpp_model_path)
        self.settings_view.set_model_options(gguf_models)
        self.statusBar().showMessage(f"Local GGUF models found: {len(gguf_models)}")

    def _on_open_models_folder(self) -> None:
        folder = models_dir(create=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.statusBar().showMessage(f"Models folder: {folder}")

    def _on_test_ai_provider(self) -> None:
        snapshot = self.settings_view.read_settings()
        timer_start = perf_counter()
        try:
            provider = self._build_ai_provider(settings=snapshot)
            health = provider.validate()
            lines = [f"Provider: {snapshot.ai_provider}", f"Health: {health}"]
            sample_path = ""
            if self.inspector_view.current_candidate_id is not None:
                candidate = self.db_manager.get_candidate_by_id(self.inspector_view.current_candidate_id)
                if candidate is not None and Path(candidate.path).exists():
                    sample_path = candidate.path
            if sample_path:
                result = provider.analyze_image(sample_path, prompt="Return strict JSON only with keys: title, keywords.")
                lines += [f"Sample: {sample_path}", f"Title: {result.title}", f"Keywords: {', '.join(result.keywords[:10])}"]
            else:
                lines.append("Sample image: none selected in Inspector.")
            elapsed_ms = round((perf_counter() - timer_start) * 1000, 1)
            lines.append(f"Latency: {elapsed_ms} ms")
            self.settings_view.set_ai_test_result(True, "\n".join(lines))
            self.statusBar().showMessage("AI provider test passed")
            tested_model = snapshot.ai_core_model if snapshot.ai_provider == "aicore" else snapshot.llamacpp_model_path
            self._last_ai_test_result = {
                "provider": snapshot.ai_provider,
                "model": tested_model,
                "latency_ms": elapsed_ms,
                "tested_at": datetime.now().isoformat(timespec="seconds"),
                "result": "passed",
            }
        except Exception as exc:
            elapsed_ms = round((perf_counter() - timer_start) * 1000, 1)
            self.settings_view.set_ai_test_result(False, f"Test failed after {elapsed_ms} ms\n{type(exc).__name__}: {exc}")
            self.statusBar().showMessage("AI provider test failed")
            self._last_ai_test_result = None

    def _on_save_ai_test_profile(self) -> None:
        if self._last_ai_test_result is None:
            self.statusBar().showMessage("Run a successful AI provider test first")
            return
        profile = dict(self._last_ai_test_result)
        profile_name = f"{profile.get('provider')} | {profile.get('model')} | {profile.get('tested_at')}"
        profile["name"] = profile_name
        existing = [p for p in self.settings.ai_test_profiles if str(p.get("name", "")) != profile_name]
        existing.append(profile)
        self.settings.ai_test_profiles = existing
        self.settings.ai_last_test_profile = profile_name
        save_settings(self.settings)
        self.statusBar().showMessage("AI test profile saved")

    def _build_ai_provider(self, settings=None):
        from universal_stock_dam.core.ai_provider import AICoreProvider, LlamaCppProvider

        effective = settings or self.settings
        if effective.ai_provider == "aicore":
            return AICoreProvider(
                base_url=effective.ai_core_base_url,
                model=effective.ai_core_model,
            )
        return LlamaCppProvider(
            binary_path=effective.llamacpp_binary_path.strip(),
            model_path=effective.llamacpp_model_path.strip(),
            mmproj_path=effective.llamacpp_mmproj_path.strip(),
            host=effective.llamacpp_host.strip() or "127.0.0.1",
            port=effective.llamacpp_port,
            context_size=effective.llamacpp_context_size,
            gpu_layers=effective.llamacpp_gpu_layers,
        )

    def _current_ai_prompt(self) -> str | None:
        preset = (self.settings.ai_prompt_preset or "stock").strip().lower()
        if preset == "custom" and self.settings.ai_prompt_custom.strip():
            return self.settings.ai_prompt_custom.strip()
        return (
            "Analyze this image for stock photography metadata. Return strict JSON with keys: "
            "title, description, keywords. Provide up to 50 highly relevant keywords, ordered from most "
            "important to least important. No extra text."
        )

    # ── Quality workers ───────────────────────────────────────────────────────

    def _analyze_selected_image(self) -> None:
        candidate_id = self._current_candidate_selection_id()
        if candidate_id is None:
            self.statusBar().showMessage("No image selected")
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        # Quality + EXIF only on selected image
        self._start_quality_worker([candidate.path], f"Analyzing: {candidate.filename}")

    def _generate_ai_metadata_selected_image(self) -> None:
        candidate_id = self._current_candidate_selection_id()
        if candidate_id is None:
            self.statusBar().showMessage("No image selected")
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        self.inspector_view.set_feedback("Generating AI metadata...", success=None)
        self.statusBar().showMessage("Generating AI metadata...")
        self._start_ai_worker([candidate.path], f"AI generating: {candidate.filename}")

    def _analyze_unanalyzed(self) -> None:
        paths = self.db_manager.list_candidate_paths_for_quality(mode="unanalyzed", limit=1000)
        if not paths:
            self.statusBar().showMessage("No unanalyzed images found")
            return
        self._start_quality_worker(paths, "Analyzing unanalyzed images")

    def _reanalyze_all(self) -> None:
        paths = self.db_manager.list_candidate_paths_for_quality(mode="all", limit=1000)
        if not paths:
            self.statusBar().showMessage("No images found for re-analysis")
            return
        self._start_quality_worker(paths, "Re-analyzing all images")

    def _start_quality_worker(self, paths: list[str], label: str, chain_ai: bool = False) -> None:
        if self._quality_worker is not None and self._quality_worker.isRunning():
            self.statusBar().showMessage("Quality analysis already running")
            return
        self.dashboard_view.add_activity(f"{label} ({len(paths)} files)")
        self._quality_worker = QualityBatchWorker(database_manager=self.db_manager, image_paths=paths, parent=self)
        self._quality_worker.progress_updated.connect(self._on_quality_progress)
        if chain_ai:
            self._quality_worker.finished_summary.connect(lambda summary: self._on_quality_finished_chain_ai(summary, paths))
        else:
            self._quality_worker.finished_summary.connect(self._on_quality_finished)
        self._quality_worker.start()

    def _on_quality_progress(self, index: int, total: int, message: str) -> None:
        self.statusBar().showMessage(f"[{index}/{total}] {message}")

    def _on_quality_finished(self, summary: dict) -> None:
        msg = f"Quality complete: total={summary.get('total', 0)}, success={summary.get('success', 0)}, failed={summary.get('failed', 0)}"
        self.statusBar().showMessage(msg)
        self.dashboard_view.add_activity(msg)
        preserved_candidate_id = self._current_candidate_selection_id()
        self._refresh_gallery(page=self.gallery_page)
        self._refresh_database_stats()
        self._refresh_dashboard_and_quality()
        self._restore_selected_candidate(preserved_candidate_id)

    def _on_quality_finished_chain_ai(self, summary: dict, paths: list[str]) -> None:
        msg = f"Quality complete: total={summary.get('total', 0)}, success={summary.get('success', 0)}, failed={summary.get('failed', 0)}"
        self.statusBar().showMessage(msg)
        self.dashboard_view.add_activity(msg)
        # Preserve the selected image before refresh
        preserved_candidate_id = self._current_candidate_selection_id()
        self._refresh_gallery(page=self.gallery_page)
        self._refresh_database_stats()
        self._refresh_dashboard_and_quality()
        self._restore_selected_candidate(preserved_candidate_id)
        # Now chain into AI tagging
        self._start_ai_worker(paths, "AI analyzing selected image")

    # ── AI workers ────────────────────────────────────────────────────────────

    def _selected_gallery_candidate_ids(self) -> list[int]:
        return [item.data(Qt.UserRole) for item in self.gallery_view.list.selectedItems() if isinstance(item.data(Qt.UserRole), int)]

    def _ai_tag_selected_gallery(self) -> None:
        selected_ids = self._selected_gallery_candidate_ids()
        if not selected_ids:
            self.statusBar().showMessage("Select one or more gallery items to AI tag")
            return
        paths = self.db_manager.list_candidate_paths_by_ids(selected_ids)
        self._start_ai_worker(paths, "AI tagging selected gallery items")

    def _ai_tag_unanalyzed(self) -> None:
        paths = self.db_manager.list_candidate_paths_for_quality(mode="unanalyzed", limit=500)
        if not paths:
            self.statusBar().showMessage("No unanalyzed images for AI tagging")
            return
        self._start_ai_worker(paths, "AI tagging unanalyzed images")

    def _ai_tag_selected_or_all(self) -> None:
        selected_ids = self._selected_gallery_candidate_ids()
        if selected_ids:
            paths = self.db_manager.list_candidate_paths_by_ids(selected_ids)
            self._start_ai_worker(paths, "AI batch tagging selected")
            return
        paths = self.db_manager.list_candidate_paths_for_quality(mode="all", limit=300)
        if not paths:
            self.statusBar().showMessage("No images available for AI batch tagging")
            return
        self._start_ai_worker(paths, "AI batch tagging library sample")

    def _start_ai_worker(self, paths: list[str], label: str) -> None:
        if self._ai_worker is not None and self._ai_worker.isRunning():
            self.statusBar().showMessage("AI tagging already running")
            return
        if not paths:
            self.statusBar().showMessage("No images available for AI tagging")
            return
        try:
            provider = self._build_ai_provider()
        except Exception as exc:
            msg = f"AI provider setup failed: {exc}"
            self.statusBar().showMessage(msg)
            hint = "Check the AI-Core API URL and model in Settings." if self.settings.ai_provider == "aicore" else "Check the Llama.cpp Server Binary and Model paths in Settings."
            QMessageBox.warning(self, "AI Provider Error", f"{msg}\n\n{hint}")
            return
        self.dashboard_view.add_activity(f"{label} ({len(paths)} files)")
        self.ai_indicator.setVisible(True)
        self.ai_indicator.setText("⏳ AI Generating…")
        self._ai_worker = AITaggingWorker(
            database_manager=self.db_manager, provider=provider, image_paths=paths,
            prompt=self._current_ai_prompt(), parent=self,
        )
        self._ai_worker.progress_updated.connect(self._on_ai_progress)
        self._ai_worker.analysis_ready.connect(self._on_ai_analysis_ready)
        self._ai_worker.analysis_failed.connect(self._on_ai_analysis_failed)
        self._ai_worker.finished_summary.connect(self._on_ai_finished)
        self._ai_worker.start()

    def _on_ai_progress(self, index: int, total: int, message: str) -> None:
        self.ai_indicator.setVisible(True)
        self.ai_indicator.setText(f"⏳ AI [{index}/{total}]")
        self.statusBar().showMessage(f"AI [{index}/{total}] {message}")

    def _on_ai_analysis_ready(self, payload: dict) -> None:
        candidate_id = payload.get("candidate_id")
        if not isinstance(candidate_id, int):
            return
        if candidate_id != self._last_selected_candidate_id:
            return
        analysis = payload.get("analysis")
        if not isinstance(analysis, dict):
            return
        title = str(analysis.get("title") or "")
        description = str(analysis.get("description") or analysis.get("caption") or "")
        self.inspector_view.title_edit.setPlainText(title)
        self.inspector_view.description_edit.setPlainText(description)
        keywords = analysis.get("keywords", [])
        cleaned: list[str] = []
        if isinstance(keywords, list):
            cleaned = [str(k).strip() for k in keywords if str(k).strip()]
            self.inspector_view.keywords_edit.setPlainText(", ".join(cleaned[:50]))
        try:
            self.db_manager.upsert_vision_analysis(
                candidate_id,
                {
                    "title": title,
                    "description": description,
                    "keywords": cleaned[:50],
                },
            )
        except Exception as exc:
            self.inspector_view.set_feedback(f"AI save failed: {exc}", success=False)
            self.statusBar().showMessage(f"AI save failed: {exc}")
            return
        if cleaned:
            self.inspector_view.set_feedback("AI metadata generated.", success=True)
        else:
            self.inspector_view.set_feedback("AI generated no keywords for this image.", success=False)
            self.statusBar().showMessage("AI generated no keywords for this image")
        self.inspector_view.set_ai_saved(True)

    def _on_ai_analysis_failed(self, payload: dict) -> None:
        path = str(payload.get("path") or "")
        error = str(payload.get("error") or "Unknown AI error")
        candidate_id = self._last_selected_candidate_id
        if candidate_id is None:
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None or candidate.path != path:
            return
        self.inspector_view.set_feedback(f"AI generation failed: {error}", success=False)
        self.statusBar().showMessage(f"AI generation failed: {error}")

    def _on_ai_finished(self, summary: dict) -> None:
        self.ai_indicator.setVisible(False)
        msg = f"AI complete: total={summary.get('total', 0)}, success={summary.get('success', 0)}, failed={summary.get('failed', 0)}"
        self.statusBar().showMessage(msg)
        self.dashboard_view.add_activity(msg)
        # Preserve the selected image before refresh
        preserved_candidate_id = self._last_selected_candidate_id
        self._refresh_gallery(page=self.gallery_page)
        self._refresh_database_stats()
        self._refresh_dashboard_and_quality()
        # Restore selection and load results
        if preserved_candidate_id is not None:
            self._last_selected_candidate_id = preserved_candidate_id
            self._on_gallery_candidate_selected(preserved_candidate_id)

    # ── Tags ──────────────────────────────────────────────────────────────────

    def _refresh_tags(self) -> None:
        self.tags_view.tags_list.clear()
        summaries = self.db_manager.list_tag_summaries()
        self.tags_view.set_summary(len(summaries))
        for row in summaries:
            item = QListWidgetItem(f"{row['name']} ({row['color']}) - used {int(row['usage_count'])}")
            item.setData(Qt.UserRole, int(row["id"]))
            item.setData(Qt.UserRole + 1, str(row["name"]))
            item.setData(Qt.UserRole + 2, str(row["color"]))
            item.setData(Qt.UserRole + 3, int(row["usage_count"]))
            self.tags_view.tags_list.addItem(item)

    def _on_add_tag(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Tag", "Tag name")
        if not ok:
            return
        normalized = " ".join(name.split()).strip()
        if not normalized:
            return
        self.db_manager.add_or_get_tag(normalized)
        self._refresh_tags()
        self._refresh_database_stats()
        self.dashboard_view.add_activity(f"Tag added: {normalized}")

    def _on_rename_tag(self) -> None:
        item = self.tags_view.tags_list.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a tag to rename")
            return
        tag_id = int(item.data(Qt.UserRole))
        current_name = str(item.data(Qt.UserRole + 1))
        name, ok = QInputDialog.getText(self, "Rename Tag", "New tag name", text=current_name)
        if not ok:
            return
        normalized = " ".join(name.split()).strip()
        if not normalized:
            return
        try:
            self.db_manager.update_tag(tag_id, name=normalized)
            self._refresh_tags()
            self.dashboard_view.add_activity(f"Tag renamed: {current_name} → {normalized}")
        except Exception as exc:
            self.statusBar().showMessage(f"Rename failed: {exc}")

    def _on_save_tag(self) -> None:
        item = self.tags_view.tags_list.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a tag to edit")
            return
        tag_id = int(item.data(Qt.UserRole))
        name = self.tags_view.name_edit.text().strip()
        color_text = self.tags_view.color_edit.text().strip() or str(item.data(Qt.UserRole + 2))
        if not name:
            self.statusBar().showMessage("Tag name cannot be empty")
            return
        color = QColor(color_text)
        if not color.isValid():
            self.statusBar().showMessage("Tag color must be a valid color value")
            return
        try:
            self.db_manager.update_tag(tag_id, name=name, color=color.name())
            self._refresh_tags()
            self._select_tag_item(tag_id)
            self.statusBar().showMessage("Tag updated")
        except Exception as exc:
            self.statusBar().showMessage(f"Tag update failed: {exc}")

    def _on_set_tag_color(self) -> None:
        item = self.tags_view.tags_list.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a tag to recolor")
            return
        tag_id = int(item.data(Qt.UserRole))
        current_color = str(item.data(Qt.UserRole + 2))
        color = QColorDialog.getColor(parent=self)
        if not color.isValid():
            return
        try:
            self.db_manager.update_tag(tag_id, color=color.name())
            self._refresh_tags()
            self.dashboard_view.add_activity(f"Tag color updated: {current_color} → {color.name()}")
        except Exception as exc:
            self.statusBar().showMessage(f"Set color failed: {exc}")

    def _on_delete_tag(self) -> None:
        item = self.tags_view.tags_list.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a tag to delete")
            return
        tag_id = int(item.data(Qt.UserRole))
        tag_name = str(item.data(Qt.UserRole + 1))
        if QMessageBox.question(self, "Delete Tag", f"Delete tag '{tag_name}'?") != QMessageBox.Yes:
            return
        self.db_manager.delete_tag(tag_id)
        self._refresh_tags()
        self._refresh_database_stats()
        self.dashboard_view.add_activity(f"Tag deleted: {tag_name}")

    def _select_tag_item(self, tag_id: int) -> None:
        for i in range(self.tags_view.tags_list.count()):
            item = self.tags_view.tags_list.item(i)
            if int(item.data(Qt.UserRole)) == tag_id:
                self.tags_view.tags_list.setCurrentItem(item)
                return

    def _on_tag_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.tags_view.set_detail("Select a tag to view details")
            self.tags_view.name_edit.clear()
            self.tags_view.color_edit.clear()
            return
        self.tags_view.name_edit.setText(str(current.data(Qt.UserRole + 1)))
        self.tags_view.color_edit.setText(str(current.data(Qt.UserRole + 2)))
        self.tags_view.set_detail(
            f"Name: {current.data(Qt.UserRole + 1)} | Color: {current.data(Qt.UserRole + 2)} | Usage: {int(current.data(Qt.UserRole + 3) or 0)}"
        )

    # ── Collections ───────────────────────────────────────────────────────────

    def _refresh_collections(self) -> None:
        self.collections_view.collections.clear()
        summaries = self.db_manager.list_collection_summaries()
        self.collections_view.set_summary(len(summaries))
        for row in summaries:
            label_prefix = "[Smart] " if row.get("is_smart") else ""
            item = QListWidgetItem(f"{label_prefix}{row['name']} ({int(row['image_count'])} images)")
            item.setData(Qt.UserRole, int(row["id"]))
            item.setData(Qt.UserRole + 1, str(row["description"]))
            item.setData(Qt.UserRole + 2, int(row["image_count"]))
            item.setData(Qt.UserRole + 3, str(row["name"]))
            item.setData(Qt.UserRole + 4, bool(row.get("is_smart")))
            item.setData(Qt.UserRole + 5, row.get("search_spec", {}))
            self.collections_view.collections.addItem(item)
        self._refresh_filter_options()

    def _on_create_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "Create Collection", "Collection name")
        if not ok:
            return
        normalized = " ".join(name.split()).strip()
        if not normalized:
            return
        description = self.collections_view.description.toPlainText().strip()
        self.db_manager.add_or_get_collection(normalized, description=description)
        self._refresh_collections()
        self._refresh_database_stats()
        self.dashboard_view.add_activity(f"Collection created: {normalized}")

    def _on_save_search_collection(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Search", "Smart collection name")
        if not ok:
            return
        normalized = " ".join(name.split()).strip()
        if not normalized:
            return
        spec = self._current_gallery_search_spec()
        try:
            self.db_manager.create_or_update_smart_collection(
                normalized, spec, description=f"Saved search: {spec.get('search', '')}".strip()
            )
            self._refresh_collections()
            self._refresh_database_stats()
            self.dashboard_view.add_activity(f"Smart collection saved: {normalized}")
        except Exception as exc:
            self.statusBar().showMessage(f"Save search failed: {exc}")

    def _on_open_collection(self) -> None:
        item = self._selected_collection_item()
        if item is None:
            self.statusBar().showMessage("Select a collection to open")
            return
        collection_id = int(item.data(Qt.UserRole))
        collection = self.db_manager.get_collection(collection_id)
        if collection is None:
            self.statusBar().showMessage("Collection not found")
            return
        if collection.is_smart:
            self._apply_gallery_search_spec(collection.search_spec or {})
            self.statusBar().showMessage(f"Opened smart collection: {collection.name}")
            return
        self.gallery_view.filters.collection_combo.setCurrentIndex(
            self.gallery_view.filters.collection_combo.findData(collection_id)
        )
        self._refresh_gallery(page=1)
        self.statusBar().showMessage(f"Opened collection: {collection.name}")

    def _on_edit_collection(self) -> None:
        item = self.collections_view.collections.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a collection to edit")
            return
        collection_id = int(item.data(Qt.UserRole))
        current_short_name = str(item.data(Qt.UserRole + 3) or item.text())
        current_description = str(item.data(Qt.UserRole + 1))
        new_name, ok = QInputDialog.getText(self, "Edit Collection", "Collection name", text=current_short_name)
        if not ok:
            return
        normalized = " ".join(new_name.split()).strip()
        if not normalized:
            return
        desc, ok_desc = QInputDialog.getMultiLineText(self, "Edit Description", "Description", current_description)
        if not ok_desc:
            return
        try:
            self.db_manager.update_collection(collection_id, name=normalized, description=desc)
            self._refresh_collections()
            self._select_collection_item(collection_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Collection update failed: {exc}")

    def _on_delete_collection(self) -> None:
        item = self.collections_view.collections.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a collection to delete")
            return
        collection_id = int(item.data(Qt.UserRole))
        if QMessageBox.question(self, "Delete Collection", f"Delete collection '{item.text()}'?") != QMessageBox.Yes:
            return
        self.db_manager.delete_collection(collection_id)
        self._refresh_collections()
        self._refresh_database_stats()

    def _on_assign_selected_to_collection(self) -> None:
        coll_item = self._selected_collection_item()
        if coll_item is None:
            self.statusBar().showMessage("Select a collection first")
            return
        selected_ids = self._selected_gallery_candidate_ids()
        if not selected_ids:
            self.statusBar().showMessage("Select gallery items to assign")
            return
        assigned = self.db_manager.assign_candidates_to_collection(int(coll_item.data(Qt.UserRole)), selected_ids)
        self.statusBar().showMessage(f"Assigned {assigned} images")
        self._refresh_collections()

    def _on_collection_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.collections_view.set_detail("Select a collection to view details")
            self.collections_view.name_edit.clear()
            self.collections_view.description.clear()
            return
        self.collections_view.name_edit.setText(str(current.data(Qt.UserRole + 3) or current.text()))
        self.collections_view.description.setPlainText(str(current.data(Qt.UserRole + 1) or ""))
        is_smart = bool(current.data(Qt.UserRole + 4))
        self.collections_view.set_detail(
            f"Images: {current.data(Qt.UserRole + 2)} | {'Smart' if is_smart else 'Manual'}"
        )
        self._refresh_filter_options()

    def _on_save_collection(self) -> None:
        item = self.collections_view.collections.currentItem()
        if item is None:
            self.statusBar().showMessage("Select a collection to edit")
            return
        collection_id = int(item.data(Qt.UserRole))
        name = self.collections_view.name_edit.text().strip()
        description = self.collections_view.description.toPlainText().strip()
        if not name:
            self.statusBar().showMessage("Collection name cannot be empty")
            return
        try:
            self.db_manager.update_collection(collection_id, name=name, description=description)
            self._refresh_collections()
            self._select_collection_item(collection_id)
            self.statusBar().showMessage("Collection updated")
        except Exception as exc:
            self.statusBar().showMessage(f"Collection update failed: {exc}")

    def _select_collection_item(self, collection_id: int) -> None:
        for i in range(self.collections_view.collections.count()):
            item = self.collections_view.collections.item(i)
            if int(item.data(Qt.UserRole)) == collection_id:
                self.collections_view.collections.setCurrentItem(item)
                return

    # ── Inspector actions ─────────────────────────────────────────────────────

    def _on_inspector_save_metadata(self) -> None:
        self._on_inspector_save_data()

    def _on_inspector_toggle_favorite(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        try:
            updated = self.db_manager.set_candidate_favorite(candidate_id, not candidate.is_favorite)
            self.statusBar().showMessage(f"Favorite {'enabled' if updated.is_favorite else 'disabled'}")
            self._on_gallery_candidate_selected(candidate_id)
            self._refresh_gallery(page=self.gallery_page)
        except Exception as exc:
            self.statusBar().showMessage(f"Favorite toggle failed: {exc}")

    def _on_inspector_add_to_collection(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            return
        current_coll = self._selected_collection_item()
        collection_id = int(current_coll.data(Qt.UserRole)) if current_coll is not None else None
        if collection_id is None:
            name, ok = QInputDialog.getText(self, "Add to Collection", "Collection name")
            if not ok:
                return
            normalized = " ".join(name.split()).strip()
            if not normalized:
                return
            collection = self.db_manager.add_or_get_collection(normalized)
            collection_id = int(collection.id)
        try:
            assigned = self.db_manager.assign_candidates_to_collection(collection_id, [candidate_id])
            self.statusBar().showMessage(f"Added to collection ({assigned})")
            self._refresh_collections()
        except Exception as exc:
            self.statusBar().showMessage(f"Add to collection failed: {exc}")

    def _on_inspector_export(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        from universal_stock_dam.ui.views.export_dialog import ExportDialog

        dialog = ExportDialog(
            default_dir=self.settings.export_default_dir,
            default_format=self.settings.export_default_format,
            default_quality=self.settings.export_jpeg_quality,
            default_lut_path=self.settings.export_default_lut_path,
            default_filename_template=self.settings.export_filename_template,
            export_presets=self.settings.export_presets,
            default_preset_name=self.settings.export_default_preset_name,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        opts = dialog.values()
        output_dir = str(opts["output_dir"])
        if not output_dir:
            return

        self.settings.export_presets = list(opts.get("export_presets", []))
        self.settings.export_default_preset_name = str(opts.get("default_preset_name", ""))
        self.settings.export_default_dir = output_dir
        self.settings.export_default_format = str(opts["output_format"])
        self.settings.export_jpeg_quality = int(opts["jpeg_quality"])
        self.settings.export_default_lut_path = str(opts["lut_path"])
        self.settings.export_filename_template = str(opts["filename_template"])
        self.settings_view.set_settings(self.settings)
        save_settings(self.settings)

        if self._export_worker is not None and self._export_worker.isRunning():
            self.statusBar().showMessage("Export already running")
            return
        self._export_worker = BatchExportWorker(
            input_paths=[candidate.path],
            output_dir=output_dir,
            output_format=self.settings.export_default_format,
            jpeg_quality=self.settings.export_jpeg_quality,
            lut_path=self.settings.export_default_lut_path or None,
            filename_template=self.settings.export_filename_template,
            metadata_writer=self._build_metadata_writer(),
            metadata_payload_provider=self._export_metadata_payload,
            parent=self,
        )
        self._export_worker.progress_updated.connect(self._on_export_progress)
        self._export_worker.export_finished.connect(self._on_export_finished)
        self._export_worker.start()

    def _build_metadata_writer(self):
        try:
            from universal_stock_dam.core.exif_engine import ExifEngine
        except Exception:
            return None
        return ExifEngine(self.settings.exiftool_path if self.settings.exiftool_path.strip() else None)

    def _export_metadata_payload(self, source_path: str) -> dict[str, object]:
        candidate = self.db_manager.get_candidate_by_id(self.inspector_view.current_candidate_id or 0)
        if candidate is None:
            return {}
        return {
            "title": candidate.vision.title if candidate.vision else candidate.filename,
            "keywords": candidate.vision.keywords if candidate.vision else [],
            "source_path": source_path,
        }

    def _on_export_progress(self, index: int, total: int, message: str) -> None:
        self.statusBar().showMessage(f"Export [{index}/{total}] {message}")

    def _on_export_finished(self, summary: dict) -> None:
        self.dashboard_view.add_activity(
            f"Export complete: success={summary.get('success_count', 0)} failed={summary.get('failed_count', 0)}"
        )
        self.statusBar().showMessage("Export complete")

    def _on_inspector_delete(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        if QMessageBox.question(self, "Delete", f"Delete {candidate.filename}?") != QMessageBox.Yes:
            return
        try:
            deleted_name = self.db_manager.delete_candidate(candidate_id)
            self.statusBar().showMessage(f"Deleted: {deleted_name}")
            self._last_selected_candidate_id = None
            self._refresh_gallery(page=1)
            self._refresh_database_stats()
            self._refresh_dashboard_and_quality()
            self._refresh_tags()
            self._refresh_collections()
        except Exception as exc:
            self.statusBar().showMessage(f"Delete failed: {exc}")

    def _on_inspector_apply_tags(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            return
        keywords = [c.strip() for c in self.inspector_view.keywords_edit.toPlainText().split(",") if c.strip()]
        if not keywords:
            self.statusBar().showMessage("No keywords to tag")
            return
        try:
            for keyword in keywords:
                self.db_manager.add_tag_to_candidate(candidate_id, keyword)
            self.statusBar().showMessage("Tags applied")
            self._refresh_tags()
        except Exception as exc:
            self.statusBar().showMessage(f"Tag application failed: {exc}")

    def _on_inspector_save_data(self) -> None:
        candidate_id = self.inspector_view.current_candidate_id
        if candidate_id is None:
            self.statusBar().showMessage("No image selected")
            return
        candidate = self.db_manager.get_candidate_by_id(candidate_id)
        if candidate is None:
            return
        try:
            title = self.inspector_view.title_edit.toPlainText().strip()
            description = self.inspector_view.description_edit.toPlainText().strip()
            keywords = [k.strip() for k in self.inspector_view.keywords_edit.toPlainText().split(",") if k.strip()]
            stock_site = self.inspector_view.stock_site.currentText().strip()
            stock_notes = self.inspector_view.stock_notes_edit.toPlainText().strip()
            stock_location = self.inspector_view.stock_location_edit.text().strip()
            stock_usage_notes = self.inspector_view.stock_usage_edit.toPlainText().strip()
            payload = {
                "title": title,
                "description": description,
                "keywords": keywords[:50],
                "stock_site": stock_site,
                "stock_notes": stock_notes,
                "stock_location": stock_location,
                "stock_usage_notes": stock_usage_notes,
            }
            self.db_manager.upsert_vision_analysis(candidate_id, payload)
            self.statusBar().showMessage("Data saved")
            self.inspector_view.set_feedback("Saved.", success=True)
            self._refresh_gallery(page=self.gallery_page)
            self._refresh_database_stats()
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to save data: {exc}")
            self.inspector_view.set_feedback(f"Save failed: {exc}", success=False)

    # ── Database ──────────────────────────────────────────────────────────────

    def _on_create_backup(self) -> None:
        try:
            backup_path = self.db_manager.backup_database()
            self.database_view.log.append(f"Backup created: {backup_path}")
            self.statusBar().showMessage(f"Backup: {backup_path}")
            self._refresh_database_stats()
        except Exception as exc:
            self.database_view.log.append(f"Backup failed: {exc}")

    def _on_restore_backup(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(self, "Select Backup", str(data_path("backups")), "SQLite DB (*.db)")
        if not selected:
            return
        try:
            self.db_manager.restore_database(selected)
            self.database_view.log.append(f"Restored: {selected}")
            self.statusBar().showMessage("Backup restored")
            self._filmstrip_mode = "library"
            self._refresh_gallery(page=1)
            self._refresh_database_stats()
            self._refresh_dashboard_and_quality()
            self._refresh_tags()
            self._refresh_collections()
            self._refresh_filter_options()
        except Exception as exc:
            self.database_view.log.append(f"Restore failed: {exc}")

    def _on_reset_database(self) -> None:
        if QMessageBox.question(
            self,
            "Reset Database",
            "This will create a backup and clear all library metadata. Continue?",
        ) != QMessageBox.Yes:
            return
        try:
            backup_path = self.db_manager.reset_database()
            self.database_view.log.append(f"Database reset complete. Backup: {backup_path}")
            self.statusBar().showMessage(f"Database reset complete: {backup_path}")
            self._last_selected_candidate_id = None
            self.inspector_view.set_candidate(
                {
                    "candidate_id": None,
                    "filename": "No image selected",
                    "path": "",
                    "overall_score": None,
                    "metrics": {},
                    "title": "",
                    "description": "",
                    "keywords": [],
                    "stock_site": "",
                    "stock_notes": "",
                    "stock_location": "",
                    "stock_usage_notes": "",
                    "exif": {},
                }
            )
            self._refresh_gallery(page=1)
            self._refresh_database_stats()
            self._refresh_dashboard_and_quality()
            self._refresh_tags()
            self._refresh_collections()
            self._refresh_filter_options()
        except Exception as exc:
            self.database_view.log.append(f"Reset failed: {exc}")
            self.statusBar().showMessage(f"Reset failed: {exc}")

    def _on_clean_missing(self) -> None:
        try:
            deleted = self.db_manager.remove_missing_candidates()
            self.database_view.log.append(f"Removed missing: {deleted}")
            self.statusBar().showMessage(f"Removed {deleted} missing")
            self._refresh_gallery(page=1)
            self._refresh_database_stats()
            self._refresh_dashboard_and_quality()
        except Exception as exc:
            self.database_view.log.append(f"Cleanup failed: {exc}")

    def _on_vacuum(self) -> None:
        try:
            self.db_manager.vacuum_database()
            self.database_view.log.append("Vacuum completed")
            self.statusBar().showMessage("Vacuum completed")
            self._refresh_database_stats()
        except Exception as exc:
            self.database_view.log.append(f"Vacuum failed: {exc}")

    def _on_enforce_cache(self) -> None:
        try:
            result = self.db_manager.enforce_thumbnail_cache_lru(
                thumbnail_root=self.settings.thumbnail_cache_dir,
                max_cache_bytes=self.settings.thumbnail_cache_max_bytes,
            )
            self.database_view.log.append(
                "Cache prune: removed={removed_files}, freed={freed_bytes} bytes".format(**result)
            )
            self.statusBar().showMessage("Thumbnail cache enforcement complete")
        except Exception as exc:
            self.database_view.log.append(f"Cache enforcement failed: {exc}")

    def _on_find_duplicates(self) -> None:
        try:
            groups = self.db_manager.detect_duplicate_groups(limit=1000, max_distance=5)
        except Exception as exc:
            self.database_view.log.append(f"Duplicate scan failed: {exc}")
            return
        self.database_view.log.append(f"Duplicate scan: {len(groups)} groups")
        for i, group in enumerate(groups, 1):
            self.database_view.log.append(f"Group {i} ({group.get('group_size')} items)")
            for member in group.get("members", []):
                q = member.get("quality")
                self.database_view.log.append(
                    f"  {member.get('filename')} | quality={'-' if q is None else f'{float(q):.1f}'} | {member.get('path')}"
                )
        self.statusBar().showMessage(f"Duplicate scan: {len(groups)} groups")

    # ── Batch operations ──────────────────────────────────────────────────────

    def _on_batch_rename_selected(self) -> None:
        selected_ids = self._selected_gallery_candidate_ids()
        if not selected_ids:
            self.statusBar().showMessage("Select gallery items to rename")
            return
        template, ok = QInputDialog.getText(self, "Batch Rename", "Filename template", text="{stem}_{index:02d}")
        if not ok:
            return
        first = self.db_manager.get_candidate_by_id(selected_ids[0])
        target_dir = str(Path(first.path).parent) if first is not None else ""
        if QMessageBox.question(self, "Confirm", f"Rename {len(selected_ids)} files using '{template}'?") != QMessageBox.Yes:
            return
        try:
            result = self.db_manager.batch_relocate_candidates(selected_ids, target_dir=target_dir, filename_template=template, move_files=True)
            self.statusBar().showMessage(f"Batch rename: {result.get('total', 0)} processed")
            self._refresh_gallery(page=self.gallery_page)
        except Exception as exc:
            self.statusBar().showMessage(f"Batch rename failed: {exc}")

    def _on_batch_move_selected(self) -> None:
        selected_ids = self._selected_gallery_candidate_ids()
        if not selected_ids:
            self.statusBar().showMessage("Select gallery items to move")
            return
        target_dir = QFileDialog.getExistingDirectory(self, "Select Target Folder", str(Path(self.settings.export_default_dir).expanduser()))
        if not target_dir:
            return
        template, ok = QInputDialog.getText(self, "Batch Move", "Filename template", text="{stem}")
        if not ok:
            return
        if QMessageBox.question(self, "Confirm", f"Move {len(selected_ids)} files to '{target_dir}'?") != QMessageBox.Yes:
            return
        try:
            result = self.db_manager.batch_relocate_candidates(selected_ids, target_dir=target_dir, filename_template=template, move_files=True)
            self.statusBar().showMessage(f"Batch move: {result.get('total', 0)} processed")
            self._refresh_gallery(page=self.gallery_page)
        except Exception as exc:
            self.statusBar().showMessage(f"Batch move failed: {exc}")

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def _load_stylesheet(self) -> None:
        qss_path = Path(__file__).resolve().parent / "style.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
