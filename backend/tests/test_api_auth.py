from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.api.routes_analysis as routes
from app.core.api_auth import validate_api_auth_configuration
from app.main import app


def test_startup_requires_token_unless_explicitly_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PICKLEBALL_API_TOKEN", raising=False)
    monkeypatch.setenv("PICKLEBALL_AUTH_DISABLED", "false")
    with pytest.raises(RuntimeError, match="PICKLEBALL_API_TOKEN"):
        validate_api_auth_configuration()

    monkeypatch.setenv("PICKLEBALL_AUTH_DISABLED", "true")
    validate_api_auth_configuration()


def test_api_routes_require_bearer_token_and_support_explicit_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "get_mock_job", lambda _job_id: None)
    monkeypatch.setenv("PICKLEBALL_AUTH_DISABLED", "false")
    monkeypatch.setenv("PICKLEBALL_API_TOKEN", "test-secret-token")

    client = TestClient(app)
    path = "/api/analysis/jobs/job-does-not-exist"
    assert client.get(path).status_code == 401
    assert client.get("/calibration/automatic").status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer test-secret-token"}).status_code == 404

    monkeypatch.setenv("PICKLEBALL_AUTH_DISABLED", "true")
    assert client.get(path).status_code == 401
    monkeypatch.delenv("PICKLEBALL_API_TOKEN")
    assert client.get(path).status_code == 404


def test_openapi_documentation_routes_are_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PICKLEBALL_LOCAL_DOCS", raising=False)
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/redoc").status_code == 404


def test_documentation_requires_explicit_local_mode_and_loopback_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PICKLEBALL_LOCAL_DOCS", "true")
    local = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 12345))
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert local.get(path).status_code == 200
        assert local.get(path, headers={"Host": "example.com"}).status_code == 404
    assert "/api/analysis/jobs" in local.get("/openapi.json").json()["paths"]
    remote = TestClient(app, base_url="http://127.0.0.1:8000", client=("192.0.2.10", 12345))
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert remote.get(path, headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 404
    monkeypatch.setenv("PICKLEBALL_LOCAL_DOCS", "false")
    assert local.get("/openapi.json").status_code == 404
