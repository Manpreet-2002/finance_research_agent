#!/usr/bin/env python3
"""Standalone Gemini smoke test using a minimal LangGraph workflow.

This script does not use the finance agent runtime. It creates a one-node
LangGraph that calls Gemini directly through LangChain, then validates the
response against an expected value.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Literal, TypedDict

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph


class SmokeState(TypedDict):
    prompt: str
    response: str


def _load_env_file(path: str) -> None:
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _message_to_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(part for part in parts if part)
    return str(content)


def _build_graph(
    *,
    api_key: str,
    model_name: str,
    temperature: float,
) -> StateGraph:
    chat_model = ChatGoogleGenerativeAI(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
    )

    def invoke_model(state: SmokeState) -> SmokeState:
        response = chat_model.invoke([HumanMessage(content=state["prompt"])])
        return {
            "prompt": state["prompt"],
            "response": _message_to_text(response.content).strip(),
        }

    graph = StateGraph(SmokeState)
    graph.add_node("invoke_model", invoke_model)
    graph.add_edge(START, "invoke_model")
    graph.add_edge("invoke_model", END)
    return graph.compile()


def _is_match(
    *,
    expected: str,
    response: str,
    match_mode: Literal["exact", "contains"],
) -> bool:
    if match_mode == "contains":
        return expected in response
    return response == expected


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone Gemini LangGraph smoke test")
    parser.add_argument("--env-file", default=".env", help="Optional env file to load")
    parser.add_argument(
        "--model",
        default="gemini-3-flash-preview",
        help="Gemini model name",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Model temperature",
    )
    parser.add_argument(
        "--expected",
        default="FINANCE_AGENT_OK",
        help="Expected response token",
    )
    parser.add_argument(
        "--prompt",
        default=(
            "Reply with EXACTLY the text FINANCE_AGENT_OK and nothing else. "
            "Do not add punctuation, explanation, or markdown."
        ),
        help="Prompt to send to the model",
    )
    parser.add_argument(
        "--match-mode",
        choices=("exact", "contains"),
        default="exact",
        help="How to validate the response against --expected",
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)

    api_key = str(os.getenv("GOOGLE_API_KEY", "")).strip()
    if not api_key:
        print("FAIL: GOOGLE_API_KEY is missing.")
        return 1

    graph = _build_graph(
        api_key=api_key,
        model_name=args.model,
        temperature=args.temperature,
    )

    try:
        result = graph.invoke({"prompt": args.prompt, "response": ""})
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    response = str(result.get("response", "")).strip()
    ok = _is_match(
        expected=args.expected,
        response=response,
        match_mode=args.match_mode,
    )

    print("PASS" if ok else "FAIL")
    print(f"Model: {args.model}")
    print(f"Match mode: {args.match_mode}")
    print(f"Expected: {args.expected}")
    print(f"Response: {response}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
