"""教学助教 Agent —— 三个工具的定义与执行。

设计约束（与前端 coachAgentClient 的事件协议一一对应）：
1. ``get_analysis_evidence`` 只返回本轮请求携带的「可核对证据快照」，
   不额外查询数据库，也不补算指标——证据缺什么就返回缺什么。
2. ``find_teaching_drills`` 只做标签/关键词检索，首版不引入向量库。
3. ``save_training_plan`` 负责校验：计划必须绑定当前任务的证据编号，
   步骤总时长必须与声明时长一致，否则把错误回给模型重写。

工具执行结果同时服务两个读者：
* ``payload`` 回给模型继续推理；
* ``summary`` 给前端显示「这次调用到底取到了什么」。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DRILLS_PATH = Path(__file__).resolve().parents[1] / "resources" / "teaching_drills.json"

# 计划规模上限：超过这个数说明模型在堆砌，直接拒绝并要求收敛
_MAX_PLAN_STEPS = 8
_MIN_PLAN_MINUTES = 3
_MAX_PLAN_MINUTES = 90


def load_teaching_drills() -> list[dict[str, Any]]:
    """读取教学练习库（教师核对过的练习卡）。"""
    try:
        with _DRILLS_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return [item for item in data if isinstance(item, dict) and item.get("id")]


# --- OpenAI 兼容的工具声明 -------------------------------------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_analysis_evidence",
            "description": (
                "读取本次分析任务中该球员可核对的指标证据（移动距离、站位占比、回位间隔、进区率等）。"
                "凡是需要给出数字或趋势结论时，必须先调用本工具取证据；"
                "工具没返回的指标一律视为数据不足，不得推测。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选：只关注这些指标名，例如 ['回位启动间隔']。留空表示要全部。",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_teaching_drills",
            "description": (
                "按问题、水平、人数和可用时长检索教学练习库，返回练习卡（步骤、器材、复测指标）。"
                "生成训练计划前必须先检索，不要凭记忆编练习。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {"type": "string", "description": "要解决的问题，例如 '回位启动慢'"},
                    "level": {"type": "string", "description": "学生水平：初学 / 进阶"},
                    "group_size": {"type": "integer", "description": "同时训练的人数"},
                    "minutes_available": {"type": "integer", "description": "本次可用的总时长（分钟）"},
                },
                "required": ["focus"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_training_plan",
            "description": (
                "保存训练计划草稿，返回带版本号的计划。只能使用会话中已取得的证据编号，"
                "steps 的 minutes 之和必须等于 total_minutes。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "本次训练目标，一句话"},
                    "total_minutes": {"type": "integer", "description": "总时长（分钟）"},
                    "group_size": {"type": "integer", "description": "参与人数"},
                    "level": {"type": "string", "description": "水平：初学 / 进阶"},
                    "steps": {
                        "type": "array",
                        "description": "按顺序排列的练习步骤",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "minutes": {"type": "integer"},
                                "note": {"type": "string", "description": "为什么这样安排，一句话"},
                                "drill_id": {"type": "string", "description": "取自 find_teaching_drills 的练习 id"},
                                "evidence_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "这一步依据的证据编号",
                                },
                            },
                            "required": ["title", "minutes"],
                        },
                    },
                    "reassess": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "下次复测指标，带当前值与目标值",
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "整份计划引用的证据编号",
                    },
                },
                "required": ["goal", "total_minutes", "steps", "reassess"],
            },
        },
    },
]


@dataclass
class ToolResult:
    """单次工具调用的结果。"""

    ok: bool
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] | None = None


@dataclass
class CoachToolContext:
    """工具可访问的会话上下文（全部来自本次请求，不跨请求共享）。"""

    task_label: str
    subject_label: str
    source: str
    data_quality: str
    evidence: list[dict[str, Any]]
    plan_version: int = 0
    drills: list[dict[str, Any]] = field(default_factory=load_teaching_drills)

    @property
    def evidence_ids(self) -> set[str]:
        return {str(item.get("id")) for item in self.evidence if item.get("id")}


def _split_terms(text: str) -> list[str]:
    return [part for part in re.split(r"[、，,;；/\s]+", text or "") if part]


def _relevance_score(drill: dict[str, Any], focus: str) -> float:
    """关键词 + 字符重叠的相关度，够用于 8 条练习卡的首版检索。"""
    if not focus:
        return 0.0
    score = 0.0
    haystack = f"{drill.get('name', '')}{drill.get('focus', '')}"
    for term in _split_terms(focus):
        if term and term in haystack:
            score += 2.0
    score += len(set(focus) & set(haystack)) * 0.15
    return score


class CoachToolRunner:
    """按工具名分发执行，并在内部保证入参校验。"""

    def __init__(self, context: CoachToolContext) -> None:
        self.context = context
        self._saved_plan: dict[str, Any] | None = None

    # --- 分发 ---------------------------------------------------------
    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name == "get_analysis_evidence":
            return self._get_analysis_evidence(arguments)
        if name == "find_teaching_drills":
            return self._find_teaching_drills(arguments)
        if name == "save_training_plan":
            return self._save_training_plan(arguments)
        return ToolResult(ok=False, summary=f"未知工具 {name}", payload={"error": "unknown_tool"})

    # --- 工具 1：读证据 -----------------------------------------------
    def _get_analysis_evidence(self, arguments: dict[str, Any]) -> ToolResult:
        wanted = [str(item) for item in (arguments.get("metrics") or []) if str(item).strip()]
        evidence = self.context.evidence
        if wanted:
            filtered = [
                item
                for item in evidence
                if any(term in f"{item.get('metric', '')}{item.get('detail', '')}" for term in wanted)
            ]
            # 过滤后为空时不返回空数组，避免模型误判「完全没有数据」
            evidence = filtered or evidence

        if not evidence:
            return ToolResult(
                ok=True,
                summary="本次任务没有可核对的指标",
                payload={
                    "task": self.context.task_label,
                    "subject": self.context.subject_label,
                    "data_quality": self.context.data_quality,
                    "evidence": [],
                    "note": "本次任务未产出可引用指标。涉及具体数值的结论必须说明数据不足。",
                },
            )

        return ToolResult(
            ok=True,
            summary=f"返回 {len(evidence)} 条可用证据（{self.context.data_quality}）",
            payload={
                "task": self.context.task_label,
                "subject": self.context.subject_label,
                "data_source": self.context.source,
                "data_quality": self.context.data_quality,
                "evidence": [
                    {
                        "id": item.get("id"),
                        "metric": item.get("metric"),
                        "value": item.get("value"),
                        "detail": item.get("detail"),
                        "quality": item.get("quality"),
                        "window": item.get("windowLabel"),
                    }
                    for item in evidence
                ],
                "note": "只可引用以上证据；未列出的维度请明确说明不具备，不要估算。",
            },
        )

    # --- 工具 2：检索练习 ---------------------------------------------
    def _find_teaching_drills(self, arguments: dict[str, Any]) -> ToolResult:
        focus = str(arguments.get("focus") or "").strip()
        level = str(arguments.get("level") or "").strip()
        try:
            group_size = int(arguments.get("group_size") or 0)
        except (TypeError, ValueError):
            group_size = 0
        try:
            minutes_available = int(arguments.get("minutes_available") or 0)
        except (TypeError, ValueError):
            minutes_available = 0

        candidates = []
        for drill in self.context.drills:
            if minutes_available and int(drill.get("minutes") or 0) > minutes_available:
                continue
            if group_size and int(drill.get("group_size") or 1) > group_size:
                continue
            if level and level in {"初学", "进阶"} and drill.get("level") == "进阶" and level == "初学":
                continue
            candidates.append((_relevance_score(drill, focus), drill))

        if not candidates:
            return ToolResult(
                ok=True,
                summary="没有匹配的练习，可放宽时长或人数",
                payload={
                    "drills": [],
                    "note": "条件过窄导致没有匹配练习。可以放宽 minutes_available 或只保留 focus。",
                },
            )

        candidates.sort(key=lambda pair: pair[0], reverse=True)
        top = [drill for _, drill in candidates[:5]]
        return ToolResult(
            ok=True,
            summary=f"命中 {len(top)} 条练习（按「{focus or '未指定问题'}」排序）",
            payload={
                "drills": [
                    {
                        "id": drill.get("id"),
                        "name": drill.get("name"),
                        "focus": drill.get("focus"),
                        "minutes": drill.get("minutes"),
                        "group_label": drill.get("group_label"),
                        "equipment": drill.get("equipment"),
                        "steps": drill.get("steps"),
                        "target": drill.get("target"),
                        "evidence_ids": drill.get("evidence_ids"),
                    }
                    for drill in top
                ],
                "note": "计划步骤请使用这里的 id；不要组合库外的练习。",
            },
        )

    # --- 工具 3：存计划 -----------------------------------------------
    def _save_training_plan(self, arguments: dict[str, Any]) -> ToolResult:
        goal = str(arguments.get("goal") or "").strip()
        steps = arguments.get("steps")
        try:
            total_minutes = int(arguments.get("total_minutes") or 0)
        except (TypeError, ValueError):
            total_minutes = 0

        if not goal:
            return ToolResult(ok=False, summary="缺少训练目标", payload={"error": "goal_required"})
        if not isinstance(steps, list) or not steps:
            return ToolResult(ok=False, summary="计划没有步骤", payload={"error": "steps_required"})
        if len(steps) > _MAX_PLAN_STEPS:
            return ToolResult(
                ok=False,
                summary=f"步骤过多（{len(steps)} > {_MAX_PLAN_STEPS}）",
                payload={"error": "too_many_steps", "hint": "合并成不超过 8 步"},
            )
        if not _MIN_PLAN_MINUTES <= total_minutes <= _MAX_PLAN_MINUTES:
            return ToolResult(
                ok=False,
                summary=f"总时长不合规（{total_minutes} 分钟）",
                payload={
                    "error": "invalid_total_minutes",
                    "hint": f"总时长需在 {_MIN_PLAN_MINUTES}–{_MAX_PLAN_MINUTES} 分钟之间",
                },
            )

        normalized_steps: list[dict[str, Any]] = []
        minutes_sum = 0
        known_evidence = self.context.evidence_ids
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                return ToolResult(ok=False, summary="步骤格式错误", payload={"error": "invalid_step"})
            title = str(step.get("title") or "").strip()
            if not title:
                return ToolResult(ok=False, summary="步骤缺标题", payload={"error": "step_title_required"})
            try:
                minutes = int(step.get("minutes") or 0)
            except (TypeError, ValueError):
                minutes = 0
            if minutes <= 0:
                return ToolResult(
                    ok=False,
                    summary=f"步骤「{title}」时长无效",
                    payload={"error": "invalid_step_minutes", "step": title},
                )
            step_evidence = [str(item) for item in (step.get("evidence_ids") or [])]
            unknown = [item for item in step_evidence if item and item not in known_evidence]
            if unknown:
                return ToolResult(
                    ok=False,
                    summary=f"引用了不存在的证据 {unknown}",
                    payload={"error": "unknown_evidence", "unknown": unknown, "allowed": sorted(known_evidence)},
                )
            minutes_sum += minutes
            normalized_steps.append(
                {
                    "id": f"s{index + 1}",
                    "title": title,
                    "minutes": minutes,
                    "note": str(step.get("note") or "").strip(),
                    "drillId": str(step.get("drill_id") or "").strip(),
                    "evidenceIds": step_evidence,
                }
            )

        if minutes_sum != total_minutes:
            return ToolResult(
                ok=False,
                summary=f"步骤合计 {minutes_sum} 分钟 ≠ 声明 {total_minutes} 分钟",
                payload={
                    "error": "minutes_mismatch",
                    "steps_total": minutes_sum,
                    "total_minutes": total_minutes,
                    "hint": "调整各步时长，使其之和等于总时长",
                },
            )

        plan_evidence = [str(item) for item in (arguments.get("evidence_ids") or [])]
        unknown_plan_evidence = [item for item in plan_evidence if item and item not in known_evidence]
        if unknown_plan_evidence:
            return ToolResult(
                ok=False,
                summary=f"计划引用了不存在的证据 {unknown_plan_evidence}",
                payload={"error": "unknown_evidence", "allowed": sorted(known_evidence)},
            )
        if not plan_evidence:
            plan_evidence = sorted({eid for step in normalized_steps for eid in step["evidenceIds"]})

        version = self.context.plan_version + 1
        plan = {
            "version": version,
            "goal": goal,
            "level": str(arguments.get("level") or "初学").strip(),
            "totalMinutes": total_minutes,
            "groupSize": f"{int(arguments.get('group_size') or 1)} 人",
            "steps": normalized_steps,
            "reassess": [str(item) for item in (arguments.get("reassess") or []) if str(item).strip()],
            "evidenceIds": plan_evidence,
            "savedAt": _now_iso(),
            "status": "saved",
        }
        self._saved_plan = plan
        return ToolResult(
            ok=True,
            summary=f"计划 v{version} 已保存 · {len(normalized_steps)} 步 · {total_minutes} 分钟",
            payload={"saved": True, "version": version, "total_minutes": total_minutes},
            plan=plan,
        )


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
