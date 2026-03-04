"""LangChain Gemini adapter for V1 orchestration and memo generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
import re

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from .client import LlmClient, LlmRequest

_MODEL_ALIASES: dict[str, str] = {
    "gemini-3": "gemini-3-pro-preview",
    "gemini-3-pro": "gemini-3-pro-preview",
    "gemini-3-flash": "gemini-3-flash-preview",
}
_MIN_LC_GOOGLE_GENAI_VERSION = (4, 0, 0)


@dataclass
class LangChainGeminiClient(LlmClient):
    """Gemini-backed LLM client using LangChain chat interfaces."""

    api_key: str
    model: str
    temperature: float = 0.1
    include_thoughts: bool = True
    _chat_model: ChatGoogleGenerativeAI | None = field(default=None, init=False, repr=False)
    _validated_dependency_version: bool = field(default=False, init=False, repr=False)

    def generate_text(self, request: LlmRequest) -> str:
        chat = self.get_chat_model(model_override=request.model)
        response = chat.invoke([HumanMessage(content=request.prompt)])
        return _message_to_text(response.content)

    def get_chat_model(self, *, model_override: str | None = None) -> ChatGoogleGenerativeAI:
        self._ensure_supported_dependency_version()
        selected_model = _normalize_model_name(model_override or self.model)
        if model_override:
            return ChatGoogleGenerativeAI(
                model=selected_model,
                api_key=self.api_key,
                temperature=self.temperature,
                include_thoughts=self.include_thoughts,
            )
        if self._chat_model is None:
            self._chat_model = ChatGoogleGenerativeAI(
                model=selected_model,
                api_key=self.api_key,
                temperature=self.temperature,
                include_thoughts=self.include_thoughts,
            )
        return self._chat_model

    def _ensure_supported_dependency_version(self) -> None:
        if self._validated_dependency_version:
            return
        try:
            installed = metadata.version("langchain-google-genai")
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "Missing dependency: langchain-google-genai is not installed."
            ) from exc

        if _parse_semver(installed) < _MIN_LC_GOOGLE_GENAI_VERSION:
            raise RuntimeError(
                "Unsupported langchain-google-genai version "
                f"{installed}. Required >= 4.0.0 for Gemini thought-signature "
                "tool-calling compatibility."
            )
        self._validated_dependency_version = True


def _message_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    chunks.append(str(text))
        return "\n".join(chunk for chunk in chunks if chunk)
    return str(content)


def _normalize_model_name(model_name: str) -> str:
    normalized = model_name.strip()
    if not normalized:
        return "gemini-3-pro-preview"
    return _MODEL_ALIASES.get(normalized, normalized)


def _parse_semver(value: str) -> tuple[int, int, int]:
    parts = [int(token) for token in re.findall(r"\d+", value)]
    major = parts[0] if len(parts) > 0 else 0
    minor = parts[1] if len(parts) > 1 else 0
    patch = parts[2] if len(parts) > 2 else 0
    return (major, minor, patch)
