"""Unit tests for LangChain Gemini adapter helpers."""

from __future__ import annotations

import importlib.metadata as metadata

import pytest

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
