from __future__ import annotations

from pathlib import Path

from PIL import Image

from universal_stock_dam.core.exif_engine import ExifEngine
from universal_stock_dam.db.manager import DatabaseManager


def _make_image(path: Path, color: tuple[int, int, int], *, flipped: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (32, 32), color=color)
    if flipped:
        for x in range(16, 32):
            for y in range(16, 32):
                image.putpixel((x, y), (255, 255, 255))
    else:
        for x in range(0, 16):
            for y in range(0, 16):
                image.putpixel((x, y), (255, 255, 255))
    image.save(path)


def test_detect_duplicate_groups(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))

    first = tmp_path / "one.png"
    second = tmp_path / "two.png"
    third = tmp_path / "three.png"
    _make_image(first, (10, 20, 30))
    _make_image(second, (10, 20, 30))
    _make_image(third, (200, 40, 80), flipped=True)

    manager.add_or_update_candidate(str(first), first.name, first.suffix.lstrip("."))
    manager.add_or_update_candidate(str(second), second.name, second.suffix.lstrip("."))
    manager.add_or_update_candidate(str(third), third.name, third.suffix.lstrip("."))

    groups = manager.detect_duplicate_groups(limit=10, max_distance=0)

    assert groups
    assert any(len(group["members"]) == 2 for group in groups)


def test_batch_relocate_candidates(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))

    source = tmp_path / "source.jpg"
    _make_image(source, (40, 90, 140))
    candidate = manager.add_or_update_candidate(str(source), source.name, source.suffix.lstrip("."))

    target_dir = tmp_path / "moved"
    result = manager.batch_relocate_candidates(
        [candidate.id],
        target_dir=str(target_dir),
        filename_template="{stem}_renamed",
        move_files=True,
    )

    moved_path = target_dir / "source_renamed.jpg"
    updated = manager.get_candidate_by_id(candidate.id)

    assert result["total"] == 1
    assert moved_path.exists()
    assert updated is not None
    assert Path(updated.path) == moved_path
    assert updated.filename == "source_renamed.jpg"


def test_smart_collection_counts_from_saved_search(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))

    jpg_one = tmp_path / "one.jpg"
    jpg_two = tmp_path / "two.jpg"
    png_one = tmp_path / "three.png"
    _make_image(jpg_one, (1, 2, 3))
    _make_image(jpg_two, (4, 5, 6))
    _make_image(png_one, (7, 8, 9))

    manager.add_or_update_candidate(str(jpg_one), jpg_one.name, jpg_one.suffix.lstrip("."))
    manager.add_or_update_candidate(str(jpg_two), jpg_two.name, jpg_two.suffix.lstrip("."))
    manager.add_or_update_candidate(str(png_one), png_one.name, png_one.suffix.lstrip("."))

    manager.create_or_update_smart_collection(
        "JPEG only",
        {
            "search": "",
            "min_quality": 0,
            "max_quality": 100,
            "formats": ["jpg", "jpeg"],
            "sort": "newest",
        },
        description="Only JPEG files",
    )

    summaries = manager.list_collection_summaries()
    smart_summary = next(item for item in summaries if item["name"] == "JPEG only")

    assert smart_summary["is_smart"] is True
    assert smart_summary["image_count"] == 2


def test_query_candidates_filters_by_tags_and_collection(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))

    target = tmp_path / "target.jpg"
    other = tmp_path / "other.jpg"
    _make_image(target, (100, 120, 140))
    _make_image(other, (30, 60, 90))

    target_candidate = manager.add_or_update_candidate(str(target), target.name, target.suffix.lstrip("."))
    other_candidate = manager.add_or_update_candidate(str(other), other.name, other.suffix.lstrip("."))

    manager.add_tag_to_candidate(target_candidate.id, "Portrait")
    collection = manager.add_or_get_collection("Selected Work")
    manager.assign_candidates_to_collection(collection.id, [target_candidate.id])

    rows, total = manager.query_candidates(
        page=1,
        page_size=10,
        tag_query="Portrait",
        collection_id=collection.id,
        favorite_only=False,
        recommended_only=False,
        search="",
    )

    assert total == 1
    assert len(rows) == 1
    assert rows[0].id == target_candidate.id
    assert other_candidate.id != rows[0].id


def test_xmp_sidecar_round_trip(tmp_path: Path) -> None:
    engine = ExifEngine()

    target = tmp_path / "export.jpg"
    _make_image(target, (50, 80, 120))

    sidecar = engine.write_xmp_sidecar(target, "Test Title", ["one", "two"], str(tmp_path / "source.raf"))
    assert sidecar.exists()

    metadata = engine.extract_metadata(str(target))

    assert metadata["title"] == "Test Title"
    assert metadata["keywords"] == ["one", "two"]