from __future__ import annotations

import atexit
import json
import socket
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

import requests

from universal_stock_dam.core.raw_loader import extract_preview_rgb, is_raw_format


@dataclass(slots=True)
class AIAnalysisResult:
    title: str
    title_short: str
    title_poetic: str
    title_descriptive: str
    description: str
    caption: str
    keywords: list[str]
    mood: str
    scene_type: str
    objects_detected: list[str]
    color_palette: list[str]


class AIVisionProvider(ABC):
    @abstractmethod
    def analyze_image(self, image_path: str, prompt: str | None = None) -> AIAnalysisResult:
        raise NotImplementedError

    @abstractmethod
    def validate(self) -> dict[str, object]:
        raise NotImplementedError


# Tracks llama.cpp server subprocesses this app has launched so repeated
# provider instances reuse a running server instead of spawning duplicates,
# and so we can cleanly terminate them when the app exits.
_SERVER_LOCK = threading.Lock()
_SERVER_PROCESSES: dict[tuple, subprocess.Popen] = {}


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@atexit.register
def _shutdown_llamacpp_servers() -> None:
    with _SERVER_LOCK:
        for proc in _SERVER_PROCESSES.values():
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
        _SERVER_PROCESSES.clear()


class LlamaCppProvider(AIVisionProvider):
    """Runs a bundled llama.cpp server binary locally and talks to its
    OpenAI-compatible HTTP API. No external service (like Ollama) is required;
    the server process is launched on demand from the configured binary/model
    paths, which default to the files shipped in the app's resources folder.
    """

    def __init__(
        self,
        binary_path: str,
        model_path: str,
        mmproj_path: str = "",
        host: str = "127.0.0.1",
        port: int = 8642,
        context_size: int = 4096,
        gpu_layers: int = 0,
        startup_timeout: float = 120.0,
    ) -> None:
        self.binary_path = Path(binary_path).expanduser() if binary_path else Path()
        self.model_path = Path(model_path).expanduser() if model_path else Path()
        self.mmproj_path = Path(mmproj_path).expanduser() if mmproj_path.strip() else None
        self.host = host.strip() or "127.0.0.1"
        self.port = int(port)
        self.context_size = int(context_size)
        self.gpu_layers = int(gpu_layers)
        self.startup_timeout = startup_timeout
        self.base_url = f"http://{self.host}:{self.port}"

    @property
    def vision_capable(self) -> bool:
        return self.mmproj_path is not None

    def analyze_image(self, image_path: str, prompt: str | None = None) -> AIAnalysisResult:
        self._ensure_server()
        prompt_text = prompt or self._default_prompt()

        if self.vision_capable:
            image_b64 = self._image_to_base64(image_path)
            content: object = [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ]
        else:
            filename = Path(image_path).name
            content = (
                f"{prompt_text}\n\nNote: no vision projector (mmproj) is configured, so the image "
                f"itself is unavailable. Give your best-effort answer using only this filename: "
                f"'{filename}'."
            )

        payload = {
            "model": self.model_path.stem or "local-model",
            "messages": [{"role": "user", "content": content}],
            "temperature": 0.4,
            "max_tokens": 800,
        }
        response = requests.post(f"{self.base_url}/v1/chat/completions", json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()
        text = str(data["choices"][0]["message"]["content"]).strip()
        return _coerce_result(_extract_json(text))

    def validate(self) -> dict[str, object]:
        info: dict[str, object] = {
            "provider": "llamacpp",
            "binary_path": str(self.binary_path),
            "model_path": str(self.model_path),
            "mmproj_path": str(self.mmproj_path) if self.mmproj_path else "",
            "base_url": self.base_url,
            "vision_capable": self.vision_capable,
        }
        if not self.binary_path.exists():
            info["server_running"] = False
            info["error"] = f"llama.cpp server binary not found: {self.binary_path}"
            return info
        if not self.model_path.exists():
            info["server_running"] = False
            info["error"] = f"GGUF model not found: {self.model_path}"
            return info
        try:
            self._ensure_server()
            info["server_running"] = True
        except Exception as exc:
            info["server_running"] = False
            info["error"] = str(exc)
        return info

    @staticmethod
    def list_local_gguf_models(*roots: str) -> list[str]:
        seen: set[str] = set()
        found: list[str] = []
        for root_str in roots:
            if not root_str:
                continue
            root = Path(root_str).expanduser()
            if root.is_file() and root.suffix.lower() == ".gguf":
                resolved = str(root.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(resolved)
                continue
            if not root.is_dir():
                continue
            for p in root.rglob("*.gguf"):
                resolved = str(p.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(resolved)
        return sorted(found)

    def _server_key(self) -> tuple:
        return (
            str(self.binary_path),
            str(self.model_path),
            str(self.mmproj_path),
            self.host,
            self.port,
            self.context_size,
            self.gpu_layers,
        )

    def _check_health(self) -> bool:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def _ensure_server(self) -> None:
        if not self.binary_path.exists():
            raise FileNotFoundError(f"llama.cpp server binary not found: {self.binary_path}")
        if not self.model_path.exists():
            raise FileNotFoundError(f"GGUF model not found: {self.model_path}")

        if self._check_health():
            return

        key = self._server_key()
        with _SERVER_LOCK:
            proc = _SERVER_PROCESSES.get(key)
            if proc is None or proc.poll() is not None:
                if not _is_port_open(self.host, self.port):
                    proc = self._spawn_server()
                    _SERVER_PROCESSES[key] = proc

        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self._check_health():
                return
            time.sleep(0.5)
        raise TimeoutError(
            f"Timed out waiting for llama.cpp server at {self.base_url} to become ready"
        )

    def _spawn_server(self) -> subprocess.Popen:
        args = [
            str(self.binary_path),
            "-m", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "-c", str(self.context_size),
            "-ngl", str(self.gpu_layers),
        ]
        if self.mmproj_path is not None:
            args += ["--mmproj", str(self.mmproj_path)]

        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(
            args,
            cwd=str(self.binary_path.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )

    @staticmethod
    def _image_to_base64(image_path: str) -> str:
        import base64
        import io
        from PIL import Image

        path = Path(image_path).expanduser().resolve()
        buf = io.BytesIO()
        if is_raw_format(path):
            rgb = extract_preview_rgb(path, half_size=True)
            img = Image.fromarray(rgb, mode="RGB")
            img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            img.save(buf, format="JPEG", quality=85)
        else:
            with Image.open(path) as img:
                img = img.convert("RGB")
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    @staticmethod
    def _default_prompt() -> str:
        return (
            "You are a professional stock photography metadata specialist. "
            "Analyze this image and respond ONLY with a valid JSON object — no markdown, no explanation. "
            "Use these exact keys: title, description, keywords. Provide up to 50 keywords, ordered by relevance. "
            "Example: {\"title\": \"Orange Cat on Ottoman\", \"description\": \"...\", \"keywords\": [\"cat\", \"orange\", \"pet\"]}"
        )


class AICoreProvider(AIVisionProvider):
    """Uses the AI-Core OpenAI-compatible API without managing its runtime."""

    _DEFAULT_VISION_MODEL = "minicpm-v-4.6"
    _VISION_MODEL_IDS = {"minicpm-v-4.6", "gemma-4-e2b-it"}
    _NON_VISION_MODEL_IDS = {"auto", "qwen3.5-9b", "qwen3.6-35b-a3b"}

    def __init__(self, base_url: str = "http://127.0.0.1:8080", model: str = "auto") -> None:
        self.base_url = base_url.strip().rstrip("/")
        configured_model = model.strip() or "auto"
        self.model = (
            self._DEFAULT_VISION_MODEL
            if configured_model in self._NON_VISION_MODEL_IDS
            else configured_model
        )
        self._fallback_model = (
            "gemma-4-e2b-it"
            if self.model == self._DEFAULT_VISION_MODEL
            else ""
        )

    def _api_url(self) -> str:
        return self.base_url if self.base_url.endswith("/v1") else f"{self.base_url}/v1"

    def analyze_image(self, image_path: str, prompt: str | None = None) -> AIAnalysisResult:
        image_b64 = LlamaCppProvider._image_to_base64(image_path)
        prompt_text = prompt or LlamaCppProvider._default_prompt()
        content_blocks = [
            {"type": "text", "text": prompt_text},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]
        models = [self.model]
        if self._fallback_model:
            models.append(self._fallback_model)

        last_error: BaseException | None = None
        for model in models:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": content_blocks}],
                "temperature": 0.4,
                "max_tokens": 1000,
            }
            try:
                response = requests.post(
                    f"{self._api_url()}/chat/completions", json=payload, timeout=600
                )
                response.raise_for_status()
                response_content = response.json()["choices"][0]["message"]["content"]
                if isinstance(response_content, list):
                    response_content = "\n".join(
                        str(part.get("text", "")) for part in response_content if isinstance(part, dict)
                    )
                return _coerce_result(_extract_json(str(response_content)))
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError("AI-Core image analysis failed")

    def validate(self) -> dict[str, object]:
        health_url = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
        response = requests.get(f"{health_url}/health", timeout=10)
        response.raise_for_status()
        return {
            "provider": "aicore",
            "base_url": self.base_url,
            "model": self.model,
            "health": response.json(),
        }



def _extract_json(text: str) -> dict:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if candidate.lower().startswith("json"):
            candidate = candidate[4:].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start >= 0 and end > start:
            return json.loads(candidate[start : end + 1])
        raise


def _coerce_result(data: dict) -> AIAnalysisResult:
    def _text(value: object) -> str:
        text = str(value)
        for marker in ("<|im_end|>", "<|eot_id|>", "<|end_of_turn|>"):
            text = text.replace(marker, "")
        return text.strip()

    def _list(key: str) -> list[str]:
        value = data.get(key, [])
        if isinstance(value, list):
            return [text for item in value if (text := _text(item))]
        if isinstance(value, str):
            return [text for item in value.split(",") if (text := _text(item))]
        return []

    return AIAnalysisResult(
        title=_text(data.get("title", "")),
        title_short=_text(data.get("title_short", "")),
        title_poetic=_text(data.get("title_poetic", "")),
        title_descriptive=_text(data.get("title_descriptive", "")),
        description=_text(data.get("description", "")),
        caption=_text(data.get("caption", "")),
        keywords=_list("keywords")[:50],
        mood=_text(data.get("mood", "")),
        scene_type=_text(data.get("scene_type", "")),
        objects_detected=_list("objects_detected"),
        color_palette=_list("color_palette"),
    )
