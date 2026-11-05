from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from universal_stock_dam.core.exif_engine import ExifEngine
from universal_stock_dam.core.raw_loader import extract_thumbnail, is_supported_format
from universal_stock_dam.db.manager import DatabaseManager

_exif_engine = ExifEngine()


class CatalogScannerWorker(QThread):
    progress_updated = Signal(int, int, str)
    file_discovered = Signal(dict)
    scan_complete = Signal(dict)

    def __init__(
        self,
        database_manager: DatabaseManager,
        folder_path: str,
        recursive: bool = True,
        generate_thumbnails: bool = True,
        thumbnail_root: str = "universal_stock_dam/thumbnails",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.database_manager = database_manager
        self.folder_path = str(Path(folder_path).expanduser().resolve())
        self.recursive = recursive
        self.generate_thumbnails = generate_thumbnails
        self.thumbnail_root = thumbnail_root

    def run(self) -> None:
        root = Path(self.folder_path)
        if not root.exists() or not root.is_dir():
            self.scan_complete.emit({"error": f"Folder not found: {root}"})
            return

        files = self._gather_files(root)
        total = len(files)
        added = 0
        failed = 0

        for index, path in enumerate(files, start=1):
            try:
                stat = path.stat()
                candidate = self.database_manager.add_or_update_candidate(
                    path=str(path),
                    filename=path.name,
                    ext=path.suffix,
                    size_bytes=stat.st_size,
                )

                # Extract EXIF and store in vision_analysis (best-effort)
                try:
                    exif_meta = _exif_engine.extract_metadata(str(path))
                    self.database_manager.upsert_vision_analysis(candidate.id, {"exif_data": exif_meta})
                    if exif_meta.get("width") and exif_meta.get("height"):
                        self.database_manager.add_or_update_candidate(
                            path=str(path),
                            filename=path.name,
                            ext=path.suffix,
                            width=int(exif_meta["width"]),
                            height=int(exif_meta["height"]),
                        )
                except Exception:
                    pass

                thumb = None
                if self.generate_thumbnails:
                    thumb = extract_thumbnail(path=path, size_name="medium", output_dir=self.thumbnail_root)

                added += 1
                payload = {
                    "candidate_id": candidate.id,
                    "path": candidate.path,
                    "filename": candidate.filename,
                    "thumbnail": thumb.output_path if thumb else "",
                }
                self.file_discovered.emit(payload)
                self.progress_updated.emit(index, total, f"Indexed {path.name}")
            except Exception as exc:
                failed += 1
                self.progress_updated.emit(index, total, f"Failed {path.name}: {exc}")

        self.database_manager.add_or_update_watched_folder(path=str(root), is_active=True)
        self.scan_complete.emit({"total": total, "added": added, "failed": failed})

    def _gather_files(self, root: Path) -> list[Path]:
        if self.recursive:
            candidates = [p for p in root.rglob("*") if p.is_file()]
        else:
            candidates = [p for p in root.glob("*") if p.is_file()]

        return [p for p in candidates if is_supported_format(p)]
