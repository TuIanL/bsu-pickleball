from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.coach_cloud as cloud

ORIGIN = "https://example.onrender.com"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PICKLEBALL_COACH_AGENT_API_KEY", "test-server-only-secret")

    async def fake_stream(payload):
        yield {"type": "tool_start", "call": {"id": "c1", "name": "get_analysis_evidence"}}
        yield {"type": "text_delta", "delta": "模型已读取本次证据"}

    monkeypatch.setattr(cloud, "stream_coach_chat", fake_stream)
    return TestClient(cloud.create_app([ORIGIN]))


def test_live_event_stream_and_allowed_origin(client: TestClient) -> None:
    response = client.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "解释移动数据"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["access-control-allow-origin"] == ORIGIN
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]
    assert [event["type"] for event in events] == ["tool_start", "text_delta"]
    assert response.text.endswith("data: [DONE]\n\n")


def test_origin_and_input_limits(client: TestClient) -> None:
    for origin in (None, "https://unrelated.example"):
        headers = {"Origin": origin} if origin else {}
        assert client.post("/api/coach/chat", headers=headers, json={"message": "你好"}).status_code == 403
    assert client.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "x" * 2001}).status_code == 422
    assert client.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": " "}).status_code == 422
    assert client.post("/api/coach/chat", headers={"Origin": ORIGIN}, content=b"x" * 32769).status_code == 413


def test_rate_limit_and_concurrency(client: TestClient) -> None:
    budget = cloud.TurnBudget(hourly_per_client=1, daily_total=3)
    limited = TestClient(cloud.create_app([ORIGIN], budget))
    assert limited.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "你好"}).status_code == 200
    assert limited.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "你好"}).status_code == 429
    assert budget.active == 0
    budget = cloud.TurnBudget()
    budget.active = cloud.MAX_CONCURRENT_TURNS
    busy = TestClient(cloud.create_app([ORIGIN], budget))
    assert busy.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "你好"}).status_code == 429


def test_health_never_returns_secrets_or_enables_local_apis(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["configured"] is True
    assert "test-server-only-secret" not in response.text
    for path in ("/docs", "/openapi.json", "/api/videos", "/api/analysis/jobs", "/api/capture-takes/active"):
        assert client.get(path).status_code == 404
    monkeypatch.delenv("PICKLEBALL_COACH_AGENT_API_KEY")
    assert client.get("/healthz").status_code == 503
    assert client.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "你好"}).status_code == 503


def test_failed_or_unconfigured_service_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken_stream(payload):
        raise RuntimeError("private-provider-detail")
        yield

    monkeypatch.setattr(cloud, "stream_coach_chat", broken_stream)
    response = client.post("/api/coach/chat", headers={"Origin": ORIGIN}, json={"message": "你好"})
    assert '"type": "error"' in response.text
    assert "private-provider-detail" not in response.text
    unconfigured = TestClient(cloud.create_app([]))
    assert unconfigured.get("/healthz").status_code == 503
