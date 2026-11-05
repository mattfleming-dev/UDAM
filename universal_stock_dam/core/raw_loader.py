from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    import rawpy
except Exception:  # pragma: no cover - optional runtime dependency
    rawpy = None


THUMBNAIL_SIZES: dict[str, tuple[int, int]] = {
    "small": (200, 200),
    "medium": (400, 400),
    "large": (800, 800),
}

RAW_EXTENSIONS: set[str] = {
    ".3fr",
    ".arw",
    ".bay",
    ".cr2",
    ".cr3",
    ".crw",
    ".dcr",
    ".dng",
    ".erf",
    ".iiq",
    ".k25",
    ".kdc",
    ".mdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".ptx",
    ".raf",
    ".raw",
    ".rw2",
    ".rwl",
    ".sr2",
    ".srf",
    ".x3f",
}

STANDARD_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}


@dataclass(slots=True)
class ThumbnailResult:
    source_path: str
    output_path: str
    size_name: str
    width: int
    height: int


def is_supported_format(path: str | Path) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in RAW_EXTENSIONS or suffix in STANDARD_IMAGE_EXTENSIONS


def is_raw_format(path: str | Path) -> bool:
    return Path(path).suffix.lower() in RAW_EXTENSIONS


def _embedded_jpeg_rgb(raw) -> np.ndarray | None:
    """Extract embedded JPEG from RAW (fast, works for Canon/Nikon/Sony/Fuji/DNG)."""
    try:
        thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            img = Image.open(io.BytesIO(bytes(thumb.data)))
            img = ImageOps.exif_transpose(img).convert("RGB")
            return np.array(img, dtype=np.uint8)
        if thumb.format == rawpy.ThumbFormat.BITMAP:
            arr = np.array(thumb.data, dtype=np.uint8)
            if arr.ndim == 3 and arr.shape[2] >= 3:
                return arr[:, :, :3]
    except Exception:
        pass
    return None


def extract_preview_rgb(path: str | Path, half_size: bool = True) -> np.ndarray:
    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Image file not found: {src}")

    if is_raw_format(src):
        if rawpy is None:
            raise RuntimeError("rawpy is required for RAW preview extraction")

        with rawpy.imread(str(src)) as raw:
            # Embedded JPEG is fastest and most compatible across all camera brands
            embedded = _embedded_jpeg_rgb(raw)
            if embedded is not None:
                return embedded

            # Full demosaicing fallback for files without embedded preview
            try:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    no_auto_bright=False,
                    output_bps=8,
                    half_size=half_size,
                )
            except Exception:
                rgb = raw.postprocess(
                    use_auto_wb=True,
                    output_bps=8,
                    half_size=half_size,
                )
            return rgb

    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        return np.array(img, dtype=np.uint8)


def extract_thumbnail(path: str | Path, size_name: str, output_dir: str | Path) -> ThumbnailResult:
    if size_name not in THUMBNAIL_SIZES:
        raise ValueError(f"Unknown thumbnail size: {size_name}")

    src = Path(path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Image file not found: {src}")

    target_dir = Path(output_dir).expanduser().resolve() / size_name
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{src.stem}.jpg"

    thumb_size = THUMBNAIL_SIZES[size_name]

    if is_raw_format(src):
        rgb = extract_preview_rgb(src, half_size=True)
        image = Image.fromarray(rgb, mode="RGB")
    else:
        with Image.open(src) as img:
            image = ImageOps.exif_transpose(img).convert("RGB")

    image.thumbnail(thumb_size, Image.Resampling.LANCZOS)
    image.save(out_path, format="JPEG", quality=85, optimize=True)

    return ThumbnailResult(
        source_path=str(src),
        output_path=str(out_path),
        size_name=size_name,
        width=image.width,
        height=image.height,
    )
