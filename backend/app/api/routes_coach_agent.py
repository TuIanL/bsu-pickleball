"""教学助教 Agent 接口。

* ``POST /api/coach/chat`` —— SSE 事件流（与前端 CoachStreamEvent 同构）
* ``GET  /api/coach/health`` —— 模型配置状态，供前端决定是否可切 live

安全：不记录、不回显密钥；事件里只出现模型产出与工具结果。
"""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.coach_agent import get_coach_agent_settings, stream_coach_chat

router = APIRouter(prefix="/api/coach", tags=["coach-agent"])


class CoachEvidenceModel(BaseModel):
    id: str
    metric: str = ""
    value: str = ""
    detail: str = ""
    quality: str = "medium"
    windowLabel: str | None = None


class CoachContextModel(BaseModel):
    taskLabel: str = ""
    playerLabel: str = ""
    source: str = "demo"
    dataQuality: str = ""
    evidence: list[CoachEvidenceModel] = Field(default_factory=list)
    hasInsights: bool = False


class CoachPlanStepModel(BaseModel):
    id: str = ""
    title: str = ""
    minutes: int = 0
    note: str = ""
    drillId: str = ""
    evidenceIds: list[str] = Field(default_factory=list)


class CoachPlanModel(BaseModel):
    version: int = 0
    goal: str = ""
    totalMinutes: int = 0
    steps: list[CoachPlanStepModel] = Field(default_factory=list)


class CoachHistoryItem(BaseModel):
    role: str = "user"
    text: str = ""


class CoachChatRequest(BaseModel):
    message: str
    context: CoachContextModel = Field(default_factory=CoachContextModel)
    plan: CoachPlanModel | None = None
    history: list[CoachHistoryItem] = Field(default_factory=list)


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _event_stream(payload: CoachChatRequest) -> AsyncGenerator[str, None]:
    try:
        async for event in stream_coach_chat(payload.model_dump()):
            yield _sse(event)
    except Exception as error:  # 兜底：任何异常都转成一条可读事件，不裸抛给浏览器
        yield _sse({"type": "error", "message": f"教学助教内部错误：{error.__class__.__name__}"})
    yield "data: [DONE]\n\n"


@router.post("/chat")
async def coach_chat(payload: CoachChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx 等反向代理下禁用缓冲，保证逐字出字
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
def coach_health() -> dict[str, Any]:
    settings = get_coach_agent_settings()
    return {
        "configured": settings.configured,
        "model": settings.model,
        "base_url": settings.base_url,
    }
