from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from universal_stock_dam.core.paths import data_path, models_dir, resource_path


def _cpu_backend_binary_path() -> Path:
    return resource_path("resources", "llama-b11024-bin-win-cpu-x64", "llama-server.exe")


def _cuda_backend_binary_path() -> Path:
    return resource_path("resources", "llama-b11024-bin-win-cuda-13.4-x64", "llama-server.exe")


def _default_llamacpp_binary_path() -> str:
    path = _cpu_backend_binary_path()
    return str(path) if path.exists() else ""


def _first_user_gguf(*, mmproj: bool) -> str:
    """Fall back to a user-provided .gguf in the writable models folder
    (used when the app was installed without bundled model weights).
    Files with "mmproj" in their name are treated as vision projectors;
    everything else is treated as a chat/completion model.
    """
    root = models_dir()
    if not root.is_dir():
        return ""
    candidates = sorted(root.rglob("*.gguf"))
    for candidate in candidates:
        is_mmproj = "mmproj" in candidate.stem.lower()
        if is_mmproj == mmproj:
            return str(candidate)
    return ""


def _default_llamacpp_model_path() -> str:
    path = resource_path("resources", "gemma-4-E2B-it-Q4_K_M.gguf")
    if path.exists():
        return str(path)
    return _first_user_gguf(mmproj=False)


def _default_llamacpp_mmproj_path() -> str:
    path = resource_path("resources", "mmproj-gemma-4-E2B-it-F16.gguf")
    if path.exists():
        return str(path)
    return _first_user_gguf(mmproj=True)


def available_llamacpp_backends() -> dict[str, str]:
    """Returns a mapping of backend id -> llama-server.exe path for every
    bundled llama.cpp build found in the resources folder (e.g. "cpu", "cuda").
    """
    backends: dict[str, str] = {}
    cpu_path = _cpu_backend_binary_path()
    if cpu_path.exists():
        backends["cpu"] = str(cpu_path)
    cuda_path = _cuda_backend_binary_path()
    if cuda_path.exists():
        backends["cuda"] = str(cuda_path)
    return backends


@dataclass(slots=True)
class DamSettings:
    schema_version: int = 1

    ai_provider: str = "llamacpp"
    ai_core_base_url: str = "http://127.0.0.1:8080"
    ai_core_model: str = "auto"
    llamacpp_backend: str = "cpu"
    llamacpp_binary_path: str = field(default_factory=_default_llamacpp_binary_path)
    llamacpp_model_path: str = field(default_factory=_default_llamacpp_model_path)
    llamacpp_mmproj_path: str = field(default_factory=_default_llamacpp_mmproj_path)
    llamacpp_host: str = "127.0.0.1"
    llamacpp_port: int = 8642
    llamacpp_context_size: int = 4096
    llamacpp_gpu_layers: int = 0
    ai_prompt_preset: str = "stock"
    ai_prompt_custom: str = ""
    ai_test_profiles: list[dict[str, object]] = field(default_factory=list)
    ai_last_test_profile: str = ""

    exiftool_path: str = ""

    thumbnail_cache_dir: str = field(default_factory=lambda: str(data_path("thumbnails")))
    thumbnail_cache_max_gb: float = 5.0
    thumbnail_cache_max_items: int = 1200
    thumbnail_cache_enabled: bool = True
    thumbnail_cache_auto_maintenance: bool = True
    thumbnail_cache_auto_trim_threshold_pct: float = 90.0
    thumbnail_cache_auto_keep_ratio: float = 0.5

    export_default_dir: str = field(default_factory=lambda: str(data_path("exports")))
    export_default_format: str = "jpg"
    export_jpeg_quality: int = 92
    export_default_lut_path: str = ""
    export_filename_template: str = "{stem}"
    export_presets: list[dict[str, object]] = field(default_factory=list)
    export_default_preset_name: str = ""
    stock_sites: list[str] = field(default_factory=lambda: ["Unsplash", "Adobe Stock"])

    ui_default_workspace: str = "develop"
    ui_left_panel_collapsed: bool = False
    ui_filmstrip_collapsed: bool = False
    ui_right_panel_collapsed: bool = False
    ui_splitter_sizes: list[int] = field(default_factory=lambda: [250, 900, 420])

    @property
    def thumbnail_cache_max_bytes(self) -> int:
        return int(max(self.thumbnail_cache_max_gb, 0.0) * 1024 * 1024 * 1024)


def load_settings(path: str | None = None) -> DamSettings:
    if path is None:
        path = str(data_path("settings.yaml"))
    settings_path = Path(path).expanduser().resolve()
    if not settings_path.exists():
        defaults = DamSettings()
        save_settings(defaults, str(settings_path))
        return defaults

    data = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    defaults = DamSettings()

    merged = asdict(defaults)
    merged.update({k: v for k, v in data.items() if k in merged})
    if merged.get("ai_provider") not in {"llamacpp", "aicore"}:
        merged["ai_provider"] = "llamacpp"
    return DamSettings(**merged)


def save_settings(settings: DamSettings, path: str | None = None) -> str:
    if path is None:
        path = str(data_path("settings.yaml"))
    settings_path = Path(path).expanduser().resolve()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    settings_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return str(settings_path)
