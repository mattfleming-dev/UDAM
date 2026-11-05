from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir() -> Path:
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if root:
        return Path(root) / "UniversalStockDAM"
    return Path.home() / ".universal_stock_dam"


def data_path(*parts: str, create: bool = False) -> Path:
    path = app_data_dir().joinpath(*parts)
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parents[1]


def models_dir(create: bool = False) -> Path:
    """User-writable directory for GGUF model files.

    The installer ships without model weights (they are large and
    separately licensed/downloaded), so this is where end users drop their
    own .gguf files after installing. Always writable, unlike the app's
    installation folder which may be under Program Files.
    """
    path = app_data_dir() / "models"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    bundled = bundle_root().joinpath(*parts)
    if bundled.exists():
        return bundled

    package_root = Path(__file__).resolve().parents[1]
    package_candidate = package_root.joinpath(*parts)
    if package_candidate.exists():
        return package_candidate

    return Path.cwd().joinpath(*parts)