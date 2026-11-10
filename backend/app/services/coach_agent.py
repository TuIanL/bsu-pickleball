"""教学助教 Agent —— 模型调用与工具循环。

职责边界：
* 只负责「模型 ⇄ 工具」的有限循环（默认最多 4 轮），不做业务判断；
* 证据、练习、计划校验全部交给 ``coach_agent_tools``；
* 对外暴露的事件流与前端 ``CoachStreamEvent`` 完全一致，前端不需要
  知道背后是不是大模型。

密钥只从环境变量 / ``backend/.env`` 读取，绝不写进代码或前端产物。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncGenerator

import httpx

from app.services.coach_agent_tools import (
    TOOL_SPECS,
    CoachToolContext,
    CoachToolRunner,
    load_teaching_drills,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"
MAX_TOOL_ROUNDS = 4
REQUEST_TIMEOUT_SECONDS = 90.0

TOOL_TITLES = {
    "get_analysis_evidence": "读取分析证据",
    "find_teaching_drills": "检索教学练习",
    "save_training_plan": "保存训练计划",
}


def _load_env_file(path: Path) -> None:
    """极简 .env 解析：只支持 KEY=VALUE 与 # 注释，不覆盖已存在的环境变量。"""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(_ENV_FILE)


@dataclass
class CoachAgentSettings:
    api_key: str
    base_url: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.api_key)


def get_coach_agent_settings() -> CoachAgentSettings:
    return CoachAgentSettings(
        api_key=os.getenv("PICKLEBALL_COACH_AGENT_API_KEY", "").strip(),
        base_url=(os.getenv("PICKLEBALL_COACH_AGENT_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
        model=os.getenv("PICKLEBALL_COACH_AGENT_MODEL") or DEFAULT_MODEL,
    )


SYSTEM_PROMPT = """你是「瞬境」匹克球教学助教，服务对象是带队教练和体育教师。

工作方式：
1. 凡涉及数值、趋势、判断的结论，先调用 get_analysis_evidence 取证据，再作答。
2. 需要安排练习时，先调用 find_teaching_drills 检索练习库，再用 save_training_plan 保存计划。
3. 只能引用工具返回过的指标与证据编号；工具没给的维度（如击球类型、甜区命中率、战术评价）要直接说明「当前分析不产出」，不得估算或编造。
4. 用户改时长或人数时，保留原训练目标与证据引用，只调整组织方式和步骤，并在回答里说明改了什么、代价是什么。

回答要求：
- 中文，先给结论，再给依据，最后给下一步建议。
- 220 字以内（约 4–6 句），不要罗列工具名，不要说「根据工具返回」这类过程话术。
- 可以用 **加粗** 强调小标题，但不要用 markdown 标题层级。
- 引用证据时写成 [E1] 这种形式，和工具返回的 id 保持一致。
"""


def _system_prompt_for(context: dict[str, Any]) -> str:
    evidence = context.get("evidence") or []
    lines = [
        SYSTEM_PROMPT,
        "",
        "【本次会话上下文】",
        f"任务：{context.get('taskLabel') or '未知'}",
        f"球员：{context.get('playerLabel') or '未指定'}",
        f"数据来源：{'真实分析任务' if context.get('source') == 'job' else '演示样例数据'}",
        f"数据质量：{context.get('dataQuality') or '未知'}",
    ]
    if evidence:
        lines.append("可引用证据（只能用这些编号）：")
        for item in evidence:
            lines.append(
                f"- [{item.get('id')}] {item.get('metric')} = {item.get('value')}"
                f"（{item.get('detail') or ''}；质量 {item.get('quality') or '未知'}）"
            )
    else:
        lines.append("可引用证据：无。任何数值结论都必须说明数据不足。")
    return "\n".join(lines)


def _tool_call_event(call_id: str, name: str, arguments: str) -> dict[str, Any]:
    return {
        "type": "tool_start",
        "call": {
            "id": call_id,
            "name": name,
            "title": TOOL_TITLES.get(name, name),
            "argument": _short_argument(name, arguments),
            "result": "",
            "status": "running",
        },
    }


def _short_argument(name: str, raw_arguments: str) -> str:
    """把工具入参压成一行中文摘要，用于前端展示。"""
    try:
        args = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return raw_arguments[:60]
    if not isinstance(args, dict):
        return raw_arguments[:60]

    if name == "get_analysis_evidence":
        metrics = args.get("metrics") or []
        return f"指标={('、'.join(map(str, metrics)) if metrics else '全部')}"
    if name == "find_teaching_drills":
        parts = []
        if args.get("focus"):
            parts.append(f"问题={args['focus']}")
        if args.get("level"):
            parts.append(f"水平={args['level']}")
        if args.get("group_size"):
            parts.append(f"人数={args['group_size']}")
        if args.get("minutes_available"):
            parts.append(f"时长={args['minutes_available']}min")
        return " · ".join(parts) or "未指定条件"
    if name == "save_training_plan":
        steps = args.get("steps") or []
        return f"steps={len(steps)} · total={args.get('total_minutes')}min"
    return json.dumps(args, ensure_ascii=False)[:60]


async def stream_coach_chat(payload: dict[str, Any], signal: Any = None) -> AsyncGenerator[dict[str, Any], None]:
    """把一次对话变成事件流；调用方负责包成 SSE。"""
    settings = get_coach_agent_settings()
    if not settings.configured:
        yield {"type": "error", "message": "教学助教未配置模型密钥：请设置 PICKLEBALL_COACH_AGENT_API_KEY"}
        return

    context = payload.get("context") or {}
    history = payload.get("history") or []
    plan = payload.get("plan") or None
    message = str(payload.get("message") or "").strip()

    tool_context = CoachToolContext(
        task_label=str(context.get("taskLabel") or ""),
        subject_label=str(context.get("playerLabel") or ""),
        source=str(context.get("source") or "demo"),
        data_quality=str(context.get("dataQuality") or ""),
        evidence=[item for item in (context.get("evidence") or []) if isinstance(item, dict)],
        plan_version=int((plan or {}).get("version") or 0),
        drills=load_teaching_drills(),
    )
    runner = CoachToolRunner(tool_context)

    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt_for(context)}]
    for item in history[-6:]:
        role = "user" if item.get("role") == "user" else "assistant"
        text = str(item.get("text") or "").strip()
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": message})

    body_base = {
        "model": settings.model,
        "tools": TOOL_SPECS,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 1200,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for round_index in range(MAX_TOOL_ROUNDS):
            tool_calls: dict[int, dict[str, str]] = {}
            collected_text: list[str] = []
            finish_reason: str | None = None
            # 文本按 40ms / 18 字批量下发：前端仍逐字增长，但渲染次数下降一个量级
            text_buffer: list[str] = []
            buffered_chars = 0
            last_flush = time.monotonic()

            try:
                async with client.stream(
                    "POST",
                    f"{settings.base_url}/chat/completions",
                    headers=headers,
                    json={**body_base, "messages": messages},
                ) as response:
                    if response.status_code >= 400:
                        await response.aread()
                        hint = {
                            400: "请检查服务端模型配置",
                            401: "服务端模型凭证不可用",
                            402: "模型账户余额不足",
                            429: "模型请求频繁，请稍后重试",
                        }.get(response.status_code, "模型服务暂时不可用，请稍后重试")
                        yield {
                            "type": "error",
                            "message": f"模型接口返回 {response.status_code}：{hint}",
                        }
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if not data or data == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta") or {}

                        text_piece = delta.get("content")
                        if text_piece:
                            collected_text.append(text_piece)
                            text_buffer.append(text_piece)
                            buffered_chars += len(text_piece)
                            now = time.monotonic()
                            if buffered_chars >= 18 or now - last_flush >= 0.04:
                                yield {"type": "text_delta", "delta": "".join(text_buffer)}
                                text_buffer.clear()
                                buffered_chars = 0
                                last_flush = now

                        for call in delta.get("tool_calls") or []:
                            index = int(call.get("index") or 0)
                            slot = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                            if call.get("id"):
                                slot["id"] = call["id"]
                            function = call.get("function") or {}
                            if function.get("name"):
                                slot["name"] = function["name"]
                            if function.get("arguments"):
                                slot["arguments"] += function["arguments"]

                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
            except httpx.HTTPError as error:
                yield {"type": "error", "message": f"模型请求失败：{error.__class__.__name__}，请稍后重试"}
                return

            if text_buffer:
                yield {"type": "text_delta", "delta": "".join(text_buffer)}
                text_buffer.clear()
                buffered_chars = 0

            ordered = [tool_calls[index] for index in sorted(tool_calls)]
            if not ordered:
                # 没有工具调用 → 本轮就是最终回答
                return

            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(collected_text) or None,
                    "tool_calls": [
                        {
                            "id": call["id"] or f"call_{round_index}_{position}",
                            "type": "function",
                            "function": {"name": call["name"], "arguments": call["arguments"] or "{}"},
                        }
                        for position, call in enumerate(ordered)
                    ],
                }
            )

            for position, call in enumerate(ordered):
                call_id = call["id"] or f"call_{round_index}_{position}"
                name = call["name"]
                raw_arguments = call["arguments"] or "{}"
                yield _tool_call_event(call_id, name, raw_arguments)

                try:
                    arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
                    if not isinstance(arguments, dict):
                        arguments = {}
                except json.JSONDecodeError:
                    arguments = {}

                result = runner.run(name, arguments)
                yield {
                    "type": "tool_done",
                    "id": call_id,
                    "result": result.summary,
                    "status": "done" if result.ok else "failed",
                }
                if result.plan is not None:
                    yield {"type": "plan", "plan": result.plan}
                if name == "get_analysis_evidence" and result.ok and tool_context.evidence:
                    yield {
                        "type": "evidence",
                        "items": [
                            {
                                "id": item.get("id"),
                                "metric": item.get("metric"),
                                "value": item.get("value"),
                                "detail": item.get("detail") or "",
                                "quality": item.get("quality") or "medium",
                                "windowLabel": item.get("windowLabel"),
                            }
                            for item in tool_context.evidence
                        ],
                    }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(
                            {"ok": result.ok, **result.payload},
                            ensure_ascii=False,
                        ),
                    }
                )

        # 达到轮数上限仍在调工具
        yield {"type": "error", "message": "工具调用轮数达到上限，已停止；请把问题缩小到单个目标再试。"}
