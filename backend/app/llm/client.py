"""LLM client interface for memo generation and rationale summaries."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmRequest:
    prompt: str
    model: str


class LlmClient:
    """Minimal interface to hide provider-specific request details."""

    def generate_text(self, request: LlmRequest) -> str:
        raise NotImplementedError
