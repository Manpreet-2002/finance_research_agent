"""Unit tests for LangChain Gemini adapter helpers."""

from __future__ import annotations

import importlib.metadata as metadata

import pytest

import backend.app.llm.langchain_gemini as gemini_module
from backend.app.llm.langchain_gemini import (
    LangChainGeminiClient,
    _normalize_model_name,
    _parse_semver,
)


def test_normalize_model_aliases() -> None:
    assert _normalize_model_name("gemini-3") == "gemini-3-pro-preview"
    assert _normalize_model_name("gemini-3-pro") == "gemini-3-pro-preview"
    assert _normalize_model_name("gemini-3-flash") == "gemini-3-flash-preview"


def test_parse_semver_handles_suffixes() -> None:
    assert _parse_semver("4.0.0") == (4, 0, 0)
    assert _parse_semver("4.1.2rc1") == (4, 1, 2)
    assert _parse_semver("v5") == (5, 0, 0)


def test_dependency_guard_rejects_old_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metadata, "version", lambda _name: "2.1.12")
    client = LangChainGeminiClient(api_key="x", model="gemini-3")
    with pytest.raises(RuntimeError, match="Required >= 4.0.0"):
        client._ensure_supported_dependency_version()


def test_get_chat_model_override_does_not_replace_cached_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata, "version", lambda _name: "4.1.0")

    created_models: list[str] = []

    class _FakeChatModel:
        def __init__(self, *, model: str, **_: object) -> None:
            created_models.append(model)
            self.model = model

    monkeypatch.setattr(gemini_module, "ChatGoogleGenerativeAI", _FakeChatModel)

    client = LangChainGeminiClient(api_key="x", model="gemini-3-flash-preview")

    default_model = client.get_chat_model()
    override_model = client.get_chat_model(model_override="gemini-2.5-pro")
    default_model_again = client.get_chat_model()

    assert created_models == [
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
    ]
    assert default_model is default_model_again
    assert override_model is not default_model
