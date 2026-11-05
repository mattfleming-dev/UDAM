from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import func, select

from universal_stock_dam.db.manager import DatabaseManager
from universal_stock_dam.db.models import CalendarEvent, Collection, ImageCandidate, Tag, VisionAnalysis


def test_lru_thumbnail_cache_eviction(tmp_path: Path) -> None:
    db_path = tmp_path / "assets.db"
    manager = DatabaseManager(str(db_path))

    cache_dir = tmp_path / "thumbs"
    cache_dir.mkdir(parents=True, exist_ok=True)

    first = cache_dir / "a.jpg"
    second = cache_dir / "b.jpg"
    third = cache_dir / "c.jpg"

    first.write_bytes(b"a" * 120)
    time.sleep(0.01)
    second.write_bytes(b"b" * 120)
    time.sleep(0.01)
    third.write_bytes(b"c" * 120)

    result = manager.enforce_thumbnail_cache_lru(str(cache_dir), max_cache_bytes=240)

    assert result["removed_files"] >= 1
    assert not first.exists()
    assert second.exists() or third.exists()


def test_reset_database_clears_all_rows_and_creates_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "assets.db"
    manager = DatabaseManager(str(db_path))

    candidate = manager.add_or_update_candidate("/tmp/sample.jpg", "sample.jpg", "jpg")
    manager.add_or_get_tag("alpha")
    manager.add_or_get_collection("beta")
    manager.upsert_vision_analysis(candidate.id, {"title": "Example", "keywords": ["alpha", "beta"]})

    backup_path = manager.reset_database(backup_dir=str(tmp_path / "backups"))

    assert Path(backup_path).exists()
    with manager.session_factory() as session:
        assert session.execute(select(func.count(ImageCandidate.id))).scalar_one() == 0
        assert session.execute(select(func.count(Tag.id))).scalar_one() == 0
        assert session.execute(select(func.count(Collection.id))).scalar_one() == 0
        assert session.execute(select(func.count(VisionAnalysis.id))).scalar_one() == 0


def test_calendar_event_links_to_asset_and_survives_asset_deletion(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))
    image_path = tmp_path / "scheduled.jpg"
    image_path.write_bytes(b"image")
    candidate = manager.add_or_update_candidate(str(image_path), image_path.name, "jpg")

    start = time.strptime("2030-05-10 09:00", "%Y-%m-%d %H:%M")
    from datetime import datetime, timedelta

    starts_at = datetime(*start[:6])
    event = manager.save_calendar_event(
        title="Submit to stock site",
        description="Prepare release",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        candidate_id=candidate.id,
    )

    listed = manager.list_calendar_events(starts_before=starts_at + timedelta(days=1), ends_after=starts_at)
    assert listed[0]["id"] == event["id"]


    assert listed[0]["candidate_filename"] == image_path.name

    updated = manager.save_calendar_event(
        event_id=int(event["id"]),
        title="Upload image",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
    )
    assert updated["title"] == "Upload image"
    assert updated["candidate_id"] is None

    linked_event = manager.save_calendar_event(
        title="Review asset",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        candidate_id=candidate.id,
    )
    manager.delete_candidate(candidate.id)
    unlinked = manager.get_calendar_event(int(linked_event["id"]))
    assert unlinked is not None
    assert unlinked["candidate_id"] is None

    manager.delete_calendar_event(int(event["id"]))
    assert manager.get_calendar_event(int(event["id"])) is None


def test_search_matches_vision_keywords(tmp_path: Path) -> None:
    manager = DatabaseManager(str(tmp_path / "assets.db"))
    candidate = manager.add_or_update_candidate(str(tmp_path / "photo.jpg"), "photo.jpg", "jpg")
    manager.upsert_vision_analysis(candidate.id, {"keywords": ["wildflower", "meadow"]})

    matches, total = manager.query_candidates(search="wildflower")

    assert total == 1
    assert [match.id for match in matches] == [candidate.id]
