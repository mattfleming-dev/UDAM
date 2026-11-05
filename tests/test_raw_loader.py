from __future__ import annotations

from pathlib import Path

from PIL import Image

from universal_stock_dam.core.raw_loader import extract_thumbnail, is_supported_format


def test_standard_image_thumbnail_generation(tmp_path: Path) -> None:
    source = tmp_path / "sample.jpg"
    Image.new("RGB", (1600, 1000), color=(120, 80, 40)).save(source, format="JPEG")

    result = extract_thumbnail(source, "medium", tmp_path / "thumbs")
    output = Path(result.output_path)

    assert output.exists()
    assert result.width <= 400
    assert result.height <= 400


def test_supported_format_detection() -> None:
    assert is_supported_format("photo.cr3")
    assert is_supported_format("photo.nef")
    assert is_supported_format("photo.jpg")
    assert not is_supported_format("photo.txt")
