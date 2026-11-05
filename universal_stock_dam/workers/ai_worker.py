from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal

from universal_stock_dam.db.manager import DatabaseManager

if TYPE_CHECKING:
    from universal_stock_dam.core.ai_provider import AIVisionProvider


class AITaggingWorker(QThread):
    progress_updated = Signal(int, int, str)
    analysis_ready = Signal(dict)
    analysis_failed = Signal(dict)
    finished_summary = Signal(dict)

    def __init__(
        self,
        database_manager: DatabaseManager,
        provider: AIVisionProvider,
        image_paths: list[str],
        prompt: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.database_manager = database_manager
        self.provider = provider
        self.image_paths = [str(Path(p).expanduser().resolve()) for p in image_paths]
        self.prompt = prompt

    def run(self) -> None:
        total = len(self.image_paths)
        success = 0
        failed = 0

        for index, path in enumerate(self.image_paths, start=1):
            try:
                result = self.provider.analyze_image(path, self.prompt)

                candidate = self.database_manager.add_or_update_candidate(
                    path=path,
                    filename=Path(path).name,
                    ext=Path(path).suffix,
                )

                payload = {
                    "title": result.title,
                    "title_short": result.title_short,
                    "title_poetic": result.title_poetic,
                    "title_descriptive": result.title_descriptive,
                    "description": result.description,
                    "caption": result.caption,
                    "keywords": result.keywords,
                    "mood": result.mood,
                    "scene_type": result.scene_type,
                    "objects_detected": result.objects_detected,
                    "color_palette": result.color_palette,
                }
                self.database_manager.upsert_vision_analysis(candidate.id, payload)

                for keyword in result.keywords:
                    self.database_manager.add_tag_to_candidate(candidate.id, keyword)

                success += 1
                self.analysis_ready.emit({"path": path, "candidate_id": candidate.id, "analysis": payload})
                self.progress_updated.emit(index, total, f"AI tagged: {Path(path).name}")
            except Exception as exc:
                failed += 1
                self.analysis_failed.emit({"path": path, "error": str(exc)})
                self.progress_updated.emit(index, total, f"AI failed: {Path(path).name}: {exc}")

        self.finished_summary.emit({"total": total, "success": success, "failed": failed})
