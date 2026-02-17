# ADR 0002: Use Gemini 3 model family for V1 LLM tasks

## Status
Accepted

## Context
The user selected Gemini 3 for planning, memo generation, and high-level rationale synthesis.

## Decision
Set V1 defaults to:
- `LLM_PROVIDER=google`
- `LLM_MODEL=gemini-3`

## Consequences
- Centralized model config through env settings.
- Provider adapter implementation should isolate request/response differences from orchestration logic.
