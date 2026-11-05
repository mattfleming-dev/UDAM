from __future__ import annotations

from pathlib import Path

import cv2
from PySide6.QtCore import QThread, Signal

from universal_stock_dam.core.exif_engine import ExifEngine
from universal_stock_dam.core.quality_engine import QualityEngine
from universal_stock_dam.core.raw_loader import extract_preview_rgb
from universal_stock_dam.db.manager import DatabaseManager

_exif_engine = ExifEngine()


class QualityBatchWorker(QThread):
    progress_updated = Signal(int, int, str)
    quality_ready = Signal(dict)
    finished_summary = Signal(dict)

    def __init__(
        self,
        database_manager: DatabaseManager,
        image_paths: list[str],
        quality_engine: QualityEngine | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.database_manager = database_manager
        self.image_paths = [str(Path(p).expanduser().resolve()) for p in image_paths]
        self.quality_engine = quality_engine or QualityEngine()

    def run(self) -> None:
        total = len(self.image_paths)
        success = 0
        failed = 0

        for index, path in enumerate(self.image_paths, start=1):
            try:
                preview_rgb = extract_preview_rgb(path, half_size=True)
                bgr = cv2.cvtColor(preview_rgb, cv2.COLOR_RGB2BGR)
                metrics = self.quality_engine.analyze_bgr(bgr).to_dict()

                candidate = self.database_manager.add_or_update_candidate(
                    path=path,
                    filename=Path(path).name,
                    ext=Path(path).suffix,
                    width=int(preview_rgb.shape[1]),
                    height=int(preview_rgb.shape[0]),
                )
                self.database_manager.upsert_quality(candidate.id, metrics)

                # Refresh EXIF metadata from the current file for the selected candidate.
                try:
                    exif_meta = _exif_engine.extract_metadata(path)
                    self.database_manager.upsert_vision_analysis(candidate.id, {"exif_data": exif_meta})
                except Exception:
                    pass

                success += 1
                payload = {"path": path, "candidate_id": candidate.id, "quality": metrics}
                self.quality_ready.emit(payload)
                self.progress_updated.emit(index, total, f"Quality analyzed: {Path(path).name}")
            except Exception as exc:
                failed += 1
                self.progress_updated.emit(index, total, f"Quality failed: {Path(path).name}: {exc}")

        self.finished_summary.emit({"total": total, "success": success, "failed": failed})
