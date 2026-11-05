from __future__ import annotations

from pathlib import Path

import numpy as np

from universal_stock_dam.core.lut import apply_lut_to_rgb, load_lut


def test_parse_and_apply_3d_cube_identity(tmp_path: Path) -> None:
    cube_path = tmp_path / "identity.cube"
    size = 2

    lines = [
        "TITLE \"Identity\"",
        "LUT_3D_SIZE 2",
    ]

    for b in (0.0, 1.0):
        for g in (0.0, 1.0):
            for r in (0.0, 1.0):
                lines.append(f"{r:.6f} {g:.6f} {b:.6f}")

    cube_path.write_text("\n".join(lines), encoding="utf-8")

    lut = load_lut(str(cube_path))
    assert lut.shape == (size, size, size, 3)

    image = np.array([[[0, 127, 255], [64, 128, 192]]], dtype=np.uint8)
    mapped = apply_lut_to_rgb(image, lut)

    assert mapped.shape == image.shape
    # Identity LUT should preserve values with only small interpolation rounding differences.
    assert np.max(np.abs(mapped.astype(np.int16) - image.astype(np.int16))) <= 1
