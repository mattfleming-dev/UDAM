from __future__ import annotations

import numpy as np

from universal_stock_dam.core.quality_engine import QualityEngine


def test_quality_metrics_ranges() -> None:
    engine = QualityEngine()

    # Synthetic gradient with moderate structure/noise.
    h, w = 320, 480
    x = np.linspace(0, 255, w, dtype=np.uint8)
    gradient = np.tile(x, (h, 1))
    bgr = np.dstack([gradient, gradient, gradient])

    metrics = engine.analyze_bgr(bgr).to_dict()

    numeric_keys = [
        "overall_score",
        "sharpness",
        "contrast",
        "exposure",
        "noise_level",
        "dynamic_range",
        "edge_density",
        "color_cast_deviation",
        "shadow_clipping",
        "highlight_clipping",
    ]
    for key in numeric_keys:
        value = float(metrics[key])
        assert 0.0 <= value <= 100.0
