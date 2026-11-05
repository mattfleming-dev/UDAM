from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from universal_stock_dam.workers import quality_worker as quality_worker_module


class DummyQualityEngine:
    def analyze_bgr(self, _bgr):
        return SimpleNamespace(to_dict=lambda: {"overall_score": 76.0})


class DummyDatabaseManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object, object]] = []
        self.last_vision_payload: dict | None = None
        self._candidate_id = 7

    def add_or_update_candidate(self, **_kwargs):
        return SimpleNamespace(id=self._candidate_id)

    def upsert_quality(self, candidate_id, metrics):
        self.calls.append(("quality", candidate_id, metrics))

    def upsert_vision_analysis(self, candidate_id, payload):
        self.calls.append(("vision", candidate_id, payload))
        self.last_vision_payload = payload

    def get_candidate_by_id(self, candidate_id):
        return SimpleNamespace(id=candidate_id, vision=SimpleNamespace(exif_data={"old": "value"}))


def test_quality_worker_refreshes_exif_metadata(monkeypatch) -> None:
    database_manager = DummyDatabaseManager()
    worker = quality_worker_module.QualityBatchWorker(
        database_manager=database_manager,
        image_paths=["C:/temp/sample.jpg"],
        quality_engine=DummyQualityEngine(),
    )

    monkeypatch.setattr(quality_worker_module, "extract_preview_rgb", lambda *_args, **_kwargs: np.zeros((10, 10, 3), dtype=np.uint8))
    monkeypatch.setattr(quality_worker_module._exif_engine, "extract_metadata", lambda _path: {"camera_model": "ZV-1", "lens": "Sony"})

    worker.run()

    vision_calls = [call for call in database_manager.calls if call[0] == "vision"]
    assert len(vision_calls) == 1
    assert database_manager.last_vision_payload == {"exif_data": {"camera_model": "ZV-1", "lens": "Sony"}}
