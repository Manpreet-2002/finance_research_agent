"""Unit tests for symbol search API routes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.tools.symbol_search.client import SymbolSearchMatch
from backend.app.core.settings import Settings, load_settings


def _build_test_settings(tmp_path: Path) -> Settings:
    base = load_settings()
    return replace(
        base,
        execution_db_path=str(tmp_path / "executions.db"),
        execution_worker_enabled=False,
        api_cors_origins="",
    )


class FakeSymbolSearchService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int = 10) -> list[SymbolSearchMatch]:
        self.calls.append((query, limit))
        return [
            SymbolSearchMatch(
                ticker="AAPL",
                company_name="Apple Inc.",
                source="test",
            ),
            SymbolSearchMatch(
                ticker="APLE",
                company_name="Apple Hospitality REIT, Inc.",
                source="test",
            ),
        ][:limit]


def test_symbol_search_route_returns_formatted_results(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    fake_service = FakeSymbolSearchService()
    app = create_app(
        settings=settings,
        start_worker=False,
        repo_root=tmp_path,
        symbol_search_service=fake_service,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/symbol-search", params={"q": "apple"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "apple"
    assert payload["total"] == 2
    assert payload["items"][0]["label"] == "AAPL - Apple Inc."
    assert fake_service.calls == [("apple", 10)]


def test_symbol_search_route_respects_limit_query_param(tmp_path: Path) -> None:
    settings = _build_test_settings(tmp_path)
    fake_service = FakeSymbolSearchService()
    app = create_app(
        settings=settings,
        start_worker=False,
        repo_root=tmp_path,
        symbol_search_service=fake_service,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/symbol-search", params={"q": "apple", "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1
    assert fake_service.calls == [("apple", 1)]
