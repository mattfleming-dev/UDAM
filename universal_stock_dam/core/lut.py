from __future__ import annotations

from pathlib import Path

import numpy as np


def load_lut(lut_path: str) -> np.ndarray:
    path = Path(lut_path).expanduser().resolve()
    suffix = path.suffix.lower()
    if suffix == ".npy":
        lut = np.load(path)
        if lut.ndim != 2 or lut.shape[1] != 3:
            raise ValueError("1D NPY LUT must have shape [N, 3]")
        return lut.astype(np.float32)
    if suffix == ".cube":
        return _parse_cube(path)
    raise ValueError(f"Unsupported LUT extension: {suffix}")


def apply_lut_to_rgb(rgb: np.ndarray, lut: np.ndarray) -> np.ndarray:
    if rgb.dtype != np.uint8:
        raise ValueError("Expected uint8 RGB image")

    if lut.ndim == 2:
        return _apply_1d_lut(rgb, lut)
    if lut.ndim == 4:
        return _apply_3d_lut_tetrahedral(rgb, lut)

    raise ValueError("Unsupported LUT dimensions")


def _apply_1d_lut(rgb: np.ndarray, lut_1d: np.ndarray) -> np.ndarray:
    levels = lut_1d.shape[0]
    if levels < 2:
        raise ValueError("1D LUT must contain at least 2 entries")

    samples = rgb.astype(np.float32) / 255.0
    idx = samples * (levels - 1)
    idx0 = np.floor(idx).astype(np.int32)
    idx1 = np.clip(idx0 + 1, 0, levels - 1)
    frac = idx - idx0

    out = np.empty_like(samples, dtype=np.float32)
    for channel in range(3):
        c0 = lut_1d[idx0[:, :, channel], channel]
        c1 = lut_1d[idx1[:, :, channel], channel]
        out[:, :, channel] = c0 + (c1 - c0) * frac[:, :, channel]

    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)


def _apply_3d_lut_tetrahedral(rgb: np.ndarray, lut_3d: np.ndarray) -> np.ndarray:
    size = lut_3d.shape[0]
    if lut_3d.shape != (size, size, size, 3):
        raise ValueError("3D LUT must have shape [N, N, N, 3]")

    values = rgb.reshape(-1, 3).astype(np.float32) / 255.0
    scaled = values * (size - 1)
    i0 = np.floor(scaled).astype(np.int32)
    f = scaled - i0
    i1 = np.clip(i0 + 1, 0, size - 1)

    rx, ry, rz = f[:, 0], f[:, 1], f[:, 2]
    x0, y0, z0 = i0[:, 0], i0[:, 1], i0[:, 2]
    x1, y1, z1 = i1[:, 0], i1[:, 1], i1[:, 2]

    c000 = lut_3d[x0, y0, z0]
    c100 = lut_3d[x1, y0, z0]
    c010 = lut_3d[x0, y1, z0]
    c001 = lut_3d[x0, y0, z1]
    c110 = lut_3d[x1, y1, z0]
    c101 = lut_3d[x1, y0, z1]
    c011 = lut_3d[x0, y1, z1]
    c111 = lut_3d[x1, y1, z1]

    out = np.zeros((values.shape[0], 3), dtype=np.float32)

    mask0 = (rx >= ry) & (ry >= rz)
    mask1 = (rx >= rz) & (rz > ry)
    mask2 = (rz > rx) & (rx >= ry)
    mask3 = (ry > rx) & (rx >= rz)
    mask4 = (ry >= rz) & (rz > rx)
    mask5 = (rz > ry) & (ry > rx)

    out[mask0] = (
        c000[mask0]
        + rx[mask0, None] * (c100[mask0] - c000[mask0])
        + ry[mask0, None] * (c110[mask0] - c100[mask0])
        + rz[mask0, None] * (c111[mask0] - c110[mask0])
    )
    out[mask1] = (
        c000[mask1]
        + rx[mask1, None] * (c100[mask1] - c000[mask1])
        + rz[mask1, None] * (c101[mask1] - c100[mask1])
        + ry[mask1, None] * (c111[mask1] - c101[mask1])
    )
    out[mask2] = (
        c000[mask2]
        + rz[mask2, None] * (c001[mask2] - c000[mask2])
        + rx[mask2, None] * (c101[mask2] - c001[mask2])
        + ry[mask2, None] * (c111[mask2] - c101[mask2])
    )
    out[mask3] = (
        c000[mask3]
        + ry[mask3, None] * (c010[mask3] - c000[mask3])
        + rx[mask3, None] * (c110[mask3] - c010[mask3])
        + rz[mask3, None] * (c111[mask3] - c110[mask3])
    )
    out[mask4] = (
        c000[mask4]
        + ry[mask4, None] * (c010[mask4] - c000[mask4])
        + rz[mask4, None] * (c011[mask4] - c010[mask4])
        + rx[mask4, None] * (c111[mask4] - c011[mask4])
    )
    out[mask5] = (
        c000[mask5]
        + rz[mask5, None] * (c001[mask5] - c000[mask5])
        + ry[mask5, None] * (c011[mask5] - c001[mask5])
        + rx[mask5, None] * (c111[mask5] - c011[mask5])
    )

    return np.clip(np.round(out.reshape(rgb.shape) * 255.0), 0, 255).astype(np.uint8)


def _parse_cube(path: Path) -> np.ndarray:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()

    domain_min = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    domain_max = np.array([1.0, 1.0, 1.0], dtype=np.float32)

    lut_1d_size = None
    lut_3d_size = None
    values: list[list[float]] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        parts = stripped.split()
        key = parts[0].upper()

        if key == "TITLE":
            continue
        if key == "DOMAIN_MIN" and len(parts) == 4:
            domain_min = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=np.float32)
            continue
        if key == "DOMAIN_MAX" and len(parts) == 4:
            domain_max = np.array([float(parts[1]), float(parts[2]), float(parts[3])], dtype=np.float32)
            continue
        if key == "LUT_1D_SIZE" and len(parts) == 2:
            lut_1d_size = int(parts[1])
            continue
        if key == "LUT_3D_SIZE" and len(parts) == 2:
            lut_3d_size = int(parts[1])
            continue

        if len(parts) >= 3:
            try:
                values.append([float(parts[0]), float(parts[1]), float(parts[2])])
            except ValueError:
                continue

    if lut_1d_size is not None and lut_3d_size is not None:
        raise ValueError("CUBE file cannot contain both LUT_1D_SIZE and LUT_3D_SIZE")

    arr = np.array(values, dtype=np.float32)
    if arr.size == 0:
        raise ValueError("No LUT sample values found in CUBE file")

    scale = np.clip(domain_max - domain_min, 1e-8, None)
    arr = (arr - domain_min[None, :]) / scale[None, :]
    arr = np.clip(arr, 0.0, 1.0)

    if lut_1d_size is not None:
        if arr.shape[0] != lut_1d_size:
            raise ValueError("CUBE LUT_1D_SIZE does not match value count")
        return arr

    if lut_3d_size is not None:
        expected = lut_3d_size ** 3
        if arr.shape[0] != expected:
            raise ValueError("CUBE LUT_3D_SIZE does not match value count")
        # CUBE files are typically ordered with red changing fastest, then green, then blue.
        # Reshape to [b, g, r, c] then transpose to [r, g, b, c] for RGB lookup indexing.
        lut_bgr_axes = arr.reshape((lut_3d_size, lut_3d_size, lut_3d_size, 3))
        return np.transpose(lut_bgr_axes, (2, 1, 0, 3))

    raise ValueError("CUBE file missing LUT_1D_SIZE or LUT_3D_SIZE")
