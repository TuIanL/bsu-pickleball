"""Public teaching demo API. Does not import or expose the local analysis API.

Run one worker: uvicorn app.coach_cloud:app --host 0.0.0.0 --port $PORT
Model credentials are configured only in Render's server environment.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import deque
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import Field
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.routes_coach_agent import CoachChatRequest, CoachHistoryItem
from app.services.coach_agent import get_coach_agent_settings, stream_coach_chat

MAX_BODY_BYTES = 32_768
MAX_CONCURRENT_TURNS = 2
TURN_TIMEOUT_SECONDS = 150


class CloudHistoryItem(CoachHistoryItem):
    role: Literal["user", "assistant"] = "user"
    text: str = Field(default="", max_length=4_000)


class CloudChatRequest(CoachChatRequest):
    message: str = Field(min_length=1, max_length=2_000)
    history: list[CloudHistoryItem] = Field(default_factory=list, max_length=6)


class BodyLimitMiddleware:
    """Bound request bodies, including requests without Content-Length."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return
        messages: deque[Message] = deque()
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > MAX_BODY_BYTES:
                await JSONResponse({"detail": "提问与上下文过长，请缩短后重试。"}, 413)(scope, receive, send)
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            return messages.popleft() if messages else await receive()

        await self.app(scope, replay, send)


class TurnBudget:
    """Single-instance limits for the public competition demo."""

    def __init__(self, hourly_per_client: int = 30, daily_total: int = 300) -> None:
        self.hourly_per_client = hourly_per_client
        self.daily_total = daily_total
        self.turns: deque[tuple[float, str]] = deque()
        self.active = 0

    def admit(self, client: str) -> None:
        now = time.monotonic()
        while self.turns and self.turns[0][0] <= now - 86_400:
            self.turns.popleft()
        client_turns = sum(ip == client and at > now - 3_600 for at, ip in self.turns)
        if len(self.turns) >= self.daily_total or client_turns >= self.hourly_per_client:
            raise HTTPException(429, "教学助教本时段体验次数已用完，请稍后再试。", headers={"Retry-After": "3600"})
        if self.active >= MAX_CONCURRENT_TURNS:
            raise HTTPException(429, "教学助教正在回答其他问题，请稍后再试。", headers={"Retry-After": "15"})
        self.turns.append((now, client))


def create_app(allowed_origins: list[str] | None = None, budget: TurnBudget | None = None) -> FastAPI:
    origins = allowed_origins if allowed_origins is not None else [
        origin.strip().rstrip("/")
        for origin in os.getenv("COACH_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    turn_budget = budget if budget is not None else TurnBudget()

    @app.get("/healthz")
    @app.get("/api/coach/health")
    def health() -> JSONResponse:
        settings = get_coach_agent_settings()
        ready = settings.configured and bool(origins)
        return JSONResponse(
            {"configured": ready, "model": settings.model, "mode": "live"},
            status_code=200 if ready else 503,
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/coach/chat")
    async def chat(payload: CloudChatRequest, request: Request) -> StreamingResponse:
        if request.headers.get("origin", "") not in origins:
            raise HTTPException(403, "请从瞬境网页使用教学助教。")
        if not get_coach_agent_settings().configured:
            raise HTTPException(503, "教学助教尚未完成服务端配置。")
        if not payload.message.strip():
            raise HTTPException(422, "请输入问题。")
        if len(payload.context.evidence) > 32 or (payload.plan and len(payload.plan.steps) > 8):
            raise HTTPException(422, "证据或计划步骤过多，请缩短后重试。")
        turn_budget.admit(request.client.host if request.client else "unknown")

        async def events():
            # No await between the check and increment: one worker admits atomically.
            if turn_budget.active >= MAX_CONCURRENT_TURNS:
                yield encode({"type": "error", "message": "教学助教繁忙，请稍后重试。"})
                yield "data: [DONE]\n\n"
                return
            turn_budget.active += 1
            try:
                async with asyncio.timeout(TURN_TIMEOUT_SECONDS):
                    async for event in stream_coach_chat(payload.model_dump()):
                        yield encode(event)
            except TimeoutError:
                yield encode({"type": "error", "message": "本轮模型响应超时，请重试。"})
            except Exception:
                yield encode({"type": "error", "message": "教学助教暂时不可用，请稍后重试。"})
            finally:
                turn_budget.active -= 1
            yield "data: [DONE]\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        })

    return app


def encode(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


app = create_app()
