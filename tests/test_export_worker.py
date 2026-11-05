from __future__ import annotations

from pathlib import Path

from PIL import Image

from universal_stock_dam.workers.export_worker import BatchExportWorker


def test_export_worker_applies_filename_template(tmp_path: Path) -> None:
    source = tmp_path / "source image.jpg"
    image = Image.new("RGB", (16, 16), color=(120, 80, 40))
    image.save(source)

    output_dir = tmp_path / "exports"
    worker = BatchExportWorker(
        input_paths=[str(source)],
        output_dir=str(output_dir),
        output_format="png",
        filename_template="{stem}_{index:02d}",
    )

    worker.run()

    exported = output_dir / "source image_01.png"
    assert exported.exists()