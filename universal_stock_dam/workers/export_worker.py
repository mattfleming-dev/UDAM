from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import QThread, Signal

from universal_stock_dam.core.raw_loader import extract_preview_rgb, is_raw_format
from universal_stock_dam.core.lut import apply_lut_to_rgb, load_lut


class BatchExportWorker(QThread):
    progress_updated = Signal(int, int, str)
    export_finished = Signal(dict)

    def __init__(
        self,
        input_paths: list[str],
        output_dir: str,
        output_format: str = "jpg",
        resize_max_width: int | None = None,
        resize_max_height: int | None = None,
        jpeg_quality: int = 92,
        lut_path: str | None = None,
        filename_template: str = "{stem}",
        metadata_writer=None,
        metadata_payload_provider=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.input_paths = [str(Path(p).expanduser().resolve()) for p in input_paths]
        self.output_dir = str(Path(output_dir).expanduser().resolve())
        self.output_format = output_format.lower().lstrip(".")
        self.resize_max_width = resize_max_width
        self.resize_max_height = resize_max_height
        self.jpeg_quality = int(max(1, min(jpeg_quality, 100)))
        self.lut_path = str(Path(lut_path).expanduser().resolve()) if lut_path else None
        self.filename_template = filename_template.strip() or "{stem}"
        self.metadata_writer = metadata_writer
        self.metadata_payload_provider = metadata_payload_provider

    def run(self) -> None:
        out_dir = Path(self.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        lut = None
        if self.lut_path:
            lut = load_lut(self.lut_path)

        total = len(self.input_paths)
        exported: list[str] = []
        failed: list[dict[str, str]] = []

        for index, source in enumerate(self.input_paths, start=1):
            source_path = Path(source)
            try:
                output_path = self._export_single(source_path, out_dir, lut, index, total)
                exported.append(str(output_path))
                self._write_optional_metadata(str(output_path), str(source_path))
                self.progress_updated.emit(index, total, f"Exported {source_path.name}")
            except Exception as exc:
                failed.append({"source": str(source_path), "error": str(exc)})
                self.progress_updated.emit(index, total, f"Failed {source_path.name}: {exc}")

        self.export_finished.emit(
            {
                "exported": exported,
                "failed": failed,
                "total": total,
                "success_count": len(exported),
                "failed_count": len(failed),
            }
        )

    def _export_single(self, source_path: Path, out_dir: Path, lut: np.ndarray | None, index: int, total: int) -> Path:
        if not source_path.exists():
            raise FileNotFoundError(f"File not found: {source_path}")

        if is_raw_format(source_path):
            rgb = extract_preview_rgb(source_path, half_size=False)
            image = Image.fromarray(rgb, mode="RGB")
        else:
            with Image.open(source_path) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")

        if self.resize_max_width and self.resize_max_height:
            image.thumbnail((self.resize_max_width, self.resize_max_height), Image.Resampling.LANCZOS)

        if lut is not None:
            rgb = np.array(image, dtype=np.uint8)
            rgb = apply_lut_to_rgb(rgb, lut)
            image = Image.fromarray(rgb, mode="RGB")

        stem = self._format_filename_stem(source_path, index, total)
        extension = self._output_extension(self.output_format)
        output_path = out_dir / f"{stem}.{extension}"

        save_kwargs = {}
        if self.output_format in {"jpg", "jpeg"}:
            save_kwargs["quality"] = self.jpeg_quality
            save_kwargs["optimize"] = True

        image.save(output_path, format=self.output_format.upper(), **save_kwargs)
        return output_path

    def _write_optional_metadata(self, output_path: str, source_path: str) -> None:
        if self.metadata_writer is None:
            return

        payload = {}
        if callable(self.metadata_payload_provider):
            payload = self.metadata_payload_provider(source_path) or {}

        title = str(payload.get("title", "")).strip()
        keywords = payload.get("keywords", [])

        if not title or not keywords:
            return

        self.metadata_writer.write_stock_metadata(
            target_jpeg_path=output_path,
            source_raf_path=source_path,
            title=title,
            keywords=keywords,
        )

    @staticmethod
    def _output_extension(output_format: str) -> str:
        if output_format == "jpeg":
            return "jpg"
        return output_format

    def _format_filename_stem(self, source_path: Path, index: int, total: int) -> str:
        payload = {
            "stem": source_path.stem,
            "filename": source_path.name,
            "index": index,
            "total": total,
            "ext": source_path.suffix.lstrip(".") or self._output_extension(self.output_format),
        }
        try:
            formatted = self.filename_template.format_map(payload)
        except Exception:
            formatted = source_path.stem

        sanitized = re.sub(r"[<>:\\/*?\"|]+", "_", str(formatted)).strip().strip(".")
        return sanitized or source_path.stem
