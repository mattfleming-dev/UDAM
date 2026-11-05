from __future__ import annotations

from pathlib import Path

from PIL import Image

from universal_stock_dam.core.exif_engine import ExifEngine


def test_pil_exif_tags_are_named_and_exposed(tmp_path: Path) -> None:
    source = tmp_path / "sample.jpg"

    image = Image.new("RGB", (100, 100), color=(10, 20, 30))
    exif = Image.Exif()
    exif[271] = "SONY"
    exif[272] = "ZV-1"
    image.save(source, format="JPEG", exif=exif)

    payload = ExifEngine().extract_metadata(str(source))

    assert payload["camera_make"] == "SONY"
    assert payload["camera_model"] == "ZV-1"
    assert payload["exif"]["Make"] == "SONY"
    assert payload["exif"]["Model"] == "ZV-1"
