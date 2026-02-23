"""Sharing behavior tests for GoogleSheetsEngine."""

from __future__ import annotations

from typing import Any

from backend.app.core.settings import Settings
from backend.app.sheets.google_engine import GoogleSheetsEngine


class _FakeExecute:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def execute(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakePermissionsApi:
    def __init__(
        self,
        *,
        listed_permissions: list[dict[str, Any]],
        created_payload: dict[str, Any] | None = None,
        updated_payload: dict[str, Any] | None = None,
    ) -> None:
        self._listed_permissions = listed_permissions
        self._created_payload = created_payload or {
            "id": "perm_created",
            "role": "reader",
            "allowFileDiscovery": False,
        }
        self._updated_payload = updated_payload or {
            "id": "perm_updated",
            "role": "reader",
            "allowFileDiscovery": False,
        }
        self.list_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> _FakeExecute:
        self.list_calls.append(kwargs)
        return _FakeExecute({"permissions": list(self._listed_permissions)})

    def create(self, **kwargs: Any) -> _FakeExecute:
        self.create_calls.append(kwargs)
        return _FakeExecute(self._created_payload)

    def update(self, **kwargs: Any) -> _FakeExecute:
        self.update_calls.append(kwargs)
        return _FakeExecute(self._updated_payload)


class _FakeDriveService:
    def __init__(self, permissions_api: _FakePermissionsApi) -> None:
        self._permissions_api = permissions_api

    def permissions(self) -> _FakePermissionsApi:
        return self._permissions_api


def _build_engine(permissions_api: _FakePermissionsApi) -> GoogleSheetsEngine:
    engine = GoogleSheetsEngine(settings=Settings())
    engine._drive = _FakeDriveService(permissions_api)
    return engine


def test_set_anyone_with_link_reader_creates_permission_when_missing() -> None:
    permissions_api = _FakePermissionsApi(
        listed_permissions=[{"id": "owner_1", "type": "user", "role": "owner"}]
    )
    engine = _build_engine(permissions_api)

    result = engine.set_anyone_with_link_reader("sheet_123")

    assert result["status"] == "created"
    assert result["permission_id"] == "perm_created"
    assert len(permissions_api.list_calls) == 1
    assert len(permissions_api.create_calls) == 1
    assert permissions_api.create_calls[0]["body"] == {
        "type": "anyone",
        "role": "reader",
        "allowFileDiscovery": False,
    }
    assert permissions_api.create_calls[0]["supportsAllDrives"] is True
    assert permissions_api.update_calls == []


def test_set_anyone_with_link_reader_updates_existing_anyone_permission() -> None:
    permissions_api = _FakePermissionsApi(
        listed_permissions=[
            {
                "id": "perm_anyone",
                "type": "anyone",
                "role": "writer",
                "allowFileDiscovery": True,
            }
        ],
        updated_payload={
            "id": "perm_anyone",
            "role": "reader",
            "allowFileDiscovery": False,
        },
    )
    engine = _build_engine(permissions_api)

    result = engine.set_anyone_with_link_reader("sheet_123")

    assert result["status"] == "updated"
    assert result["permission_id"] == "perm_anyone"
    assert len(permissions_api.update_calls) == 1
    assert permissions_api.update_calls[0]["permissionId"] == "perm_anyone"
    assert permissions_api.update_calls[0]["body"] == {
        "role": "reader",
        "allowFileDiscovery": False,
    }
    assert permissions_api.create_calls == []


def test_set_anyone_with_link_reader_is_noop_when_already_configured() -> None:
    permissions_api = _FakePermissionsApi(
        listed_permissions=[
            {
                "id": "perm_anyone",
                "type": "anyone",
                "role": "reader",
                "allowFileDiscovery": False,
            }
        ]
    )
    engine = _build_engine(permissions_api)

    result = engine.set_anyone_with_link_reader("sheet_123")

    assert result["status"] == "unchanged"
    assert result["permission_id"] == "perm_anyone"
    assert permissions_api.create_calls == []
    assert permissions_api.update_calls == []
