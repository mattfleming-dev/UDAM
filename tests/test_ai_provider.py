from __future__ import annotations

from universal_stock_dam.core.ai_provider import AICoreProvider, LlamaCppProvider, _coerce_result, _extract_json


def test_ai_result_coercion() -> None:
    result = _coerce_result(
        {
            "title": "Sunlit Mountain Lake",
            "title_short": "Mountain Lake",
            "title_poetic": "A Quiet Alpine Mirror",
            "title_descriptive": "Calm mountain lake under warm sunlight",
            "description": "Scenic outdoor landscape",
            "caption": "Mountain lake at sunrise",
            "keywords": ["mountain", "lake", "sunrise"],
            "mood": "serene",
            "scene_type": "landscape",
            "objects_detected": ["mountain", "water"],
            "color_palette": ["blue", "green", "gold"],
        }
    )

    assert result.title == "Sunlit Mountain Lake"
    assert "mountain" in result.keywords
    assert result.scene_type == "landscape"


def test_chat_template_markers_do_not_enter_metadata() -> None:
    response = (
        '{"title": "Mountain Lake <|im_end|> <|im_end|>", '
        '"description": "Calm water<|im_end|>", '
        '"keywords": ["lake<|im_end|>", "<|im_end|>", "water"], '
        '"objects_detected": ["water<|im_end|>"]}'
        "<|im_end|>"
    )

    result = _coerce_result(_extract_json(response))

    assert result.title == "Mountain Lake"
    assert result.description == "Calm water"
    assert result.keywords == ["lake", "water"]
    assert result.objects_detected == ["water"]


def test_aicore_provider_posts_openai_compatible_vision_request(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"title":"Test lake","keywords":["lake"]}'}}]}

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> Response:
        captured.update(url=url, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr("universal_stock_dam.core.ai_provider.requests.post", fake_post)
    monkeypatch.setattr(LlamaCppProvider, "_image_to_base64", staticmethod(lambda _path: "encoded-image"))

    result = AICoreProvider("http://127.0.0.1:8080/v1", "auto").analyze_image("sample.jpg", "Describe it")

    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    request = captured["payload"]
    assert isinstance(request, dict)
    assert request["model"] == "minicpm-v-4.6"
    assert request["messages"][0]["content"][0]["text"] == "Describe it"
    assert request["messages"][0]["content"][1]["image_url"]["url"].endswith("encoded-image")
    assert result.title == "Test lake"


def test_aicore_vision_replaces_heavy_model_with_vision_model(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"title":"Test image","keywords":["vision"]}'}}]}

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> Response:
        captured.append(json)
        return Response()

    monkeypatch.setattr("universal_stock_dam.core.ai_provider.requests.post", fake_post)
    monkeypatch.setattr(LlamaCppProvider, "_image_to_base64", staticmethod(lambda _path: "encoded-image"))

    result = AICoreProvider("http://127.0.0.1:8080", "qwen3.6-35b-a3b").analyze_image("sample.jpg")

    assert len(captured) == 1
    assert captured[0]["model"] == "minicpm-v-4.6"
    assert result.title == "Test image"


def test_aicore_vision_falls_back_to_gemma_4(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"title":"Fallback image","keywords":["gemma"]}'}}]}

    class FailingResponse:
        def raise_for_status(self) -> None:
            raise RuntimeError("model unavailable")

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> Response | FailingResponse:
        captured.append(json)
        return FailingResponse() if len(captured) == 1 else Response()

    monkeypatch.setattr("universal_stock_dam.core.ai_provider.requests.post", fake_post)
    monkeypatch.setattr(LlamaCppProvider, "_image_to_base64", staticmethod(lambda _path: "encoded-image"))

    result = AICoreProvider("http://127.0.0.1:8080", "auto").analyze_image("sample.jpg")

    assert [request["model"] for request in captured] == ["minicpm-v-4.6", "gemma-4-e2b-it"]
    assert result.title == "Fallback image"


def test_aicore_vision_uses_registered_vision_model_not_heavy_model(monkeypatch) -> None:
    captured: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"title":"Test image","keywords":["vision"]}'}}]}

    def fake_post(url: str, *, json: dict[str, object], timeout: int) -> Response:
        captured.append(json)
        return Response()

    monkeypatch.setattr("universal_stock_dam.core.ai_provider.requests.post", fake_post)
    monkeypatch.setattr(LlamaCppProvider, "_image_to_base64", staticmethod(lambda _path: "encoded-image"))

    result = AICoreProvider("http://127.0.0.1:8080", "auto").analyze_image("sample.jpg")

    assert len(captured) == 1
    assert captured[0]["model"] == "minicpm-v-4.6"
    assert result.title == "Test image"
