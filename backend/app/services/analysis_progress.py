"""分析任务的模式化阶段图、状态转换和进度聚合。

这个模块只处理“任务状态如何对外表达”，不参与任何视觉算法。单摄流水线
内部仍然可以产生球轨迹、发球检测等诊断阶段，但它们不会被加入顶层任务
进度条；双摄 Parent 则必须使用自己的阶段图，不能在单摄列表后追加阶段。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

from app.schemas.analysis import AnalysisStage, AnalysisStageStatus

ProgressMode = Literal["single_view", "late_fusion_v1", "joint_tracking_v2"]


@dataclass(frozen=True)
class StageDefinition:
    id: str
    label: str
    detail: str
    weight: int


SINGLE_VIEW_STAGE_DEFINITIONS: tuple[StageDefinition, ...] = (
    StageDefinition("upload", "视频上传", "保存视频和基础比赛信息", 4),
    StageDefinition("queue", "任务排队", "等待视觉分析任务执行", 4),
    StageDefinition("calibration", "场地标定", "读取或跳过四角手工标定", 7),
    StageDefinition("video-read", "读取视频", "读取上传视频元数据和帧流", 9),
    StageDefinition("frame-sampling", "抽帧采样", "按时间轴抽取关键帧", 8),
    StageDefinition("detection", "目标检测", "运行或跳过人体检测模型", 10),
    StageDefinition("pose", "人体姿态", "运行或跳过 RTMPose26 关键点识别", 10),
    StageDefinition("tracking", "轨迹跟踪", "关联球员移动轨迹", 13),
    StageDefinition("projection", "脚点投影", "映射画面坐标到匹克球场", 10),
    StageDefinition("metrics", "运动指标", "计算移动距离、速度、厨房区停留和热力图", 10),
    StageDefinition("visualization", "可视化输出", "生成可供前端展示的结果引用", 8),
    StageDefinition("report", "报告生成", "生成报告 JSON 并交给前端展示", 7),
)

LATE_FUSION_STAGE_DEFINITIONS: tuple[StageDefinition, ...] = (
    StageDefinition("multiview-input-check", "素材与同步检查", "检查双视频、双标定和同步信息", 5),
    StageDefinition("multiview-view-a", "A 机位视觉分析", "聚合 A 机位 child 的视觉分析进度", 12),
    StageDefinition("multiview-view-b", "B 机位视觉分析", "聚合 B 机位 child 的视觉分析进度", 12),
    StageDefinition("multiview-fusion", "多视角球员轨迹融合", "融合两路机位的轨迹证据", 24),
    StageDefinition("multiview-metrics", "运动指标重算", "基于融合轨迹重算位置类指标", 16),
    StageDefinition("multiview-visualization", "可视化输出", "生成双摄结果可视化产物", 16),
    StageDefinition("multiview-report", "报告生成", "生成 Parent 报告", 15),
)

JOINT_TRACKING_STAGE_DEFINITIONS: tuple[StageDefinition, ...] = (
    StageDefinition("multiview-input-check", "素材与同步检查", "检查双视频、双标定和同步信息", 5),
    StageDefinition("multiview-joint", "双摄协同跟踪", "在 canonical 时间轴上协同处理 A/B 机位", 50),
    StageDefinition("multiview-ball-analysis", "双摄球路分析", "基于共享同步帧生成球路与立体证据", 12),
    StageDefinition("multiview-metrics", "运动指标重算", "基于协同轨迹重算位置类指标", 15),
    StageDefinition("multiview-visualization", "可视化输出", "生成双摄结果可视化产物", 10),
    StageDefinition("multiview-report", "报告生成", "生成 Parent 报告", 8),
)

STAGE_GRAPHS: Mapping[ProgressMode, tuple[StageDefinition, ...]] = {
    "single_view": SINGLE_VIEW_STAGE_DEFINITIONS,
    "late_fusion_v1": LATE_FUSION_STAGE_DEFINITIONS,
    "joint_tracking_v2": JOINT_TRACKING_STAGE_DEFINITIONS,
}


class StageTransitionError(ValueError):
    """阶段事件不属于当前图，或会造成不可解释的状态回退。"""


def resolve_progress_mode(
    analysis_kind: str | None = None,
    execution_mode: str | None = None,
) -> ProgressMode:
    if analysis_kind != "multiview":
        return "single_view"
    if execution_mode == "joint_tracking_v2":
        return "joint_tracking_v2"
    return "late_fusion_v1"


def stage_definitions(mode: ProgressMode) -> tuple[StageDefinition, ...]:
    return STAGE_GRAPHS[mode]


def stage_ids(mode: ProgressMode) -> tuple[str, ...]:
    return tuple(item.id for item in stage_definitions(mode))


def stage_definition(mode: ProgressMode, stage_id: str) -> StageDefinition:
    for definition in stage_definitions(mode):
        if definition.id == stage_id:
            return definition
    raise StageTransitionError(f"stage {stage_id!r} is not part of {mode} progress graph")


def build_stage_snapshot(
    mode: ProgressMode,
    active_stage: str = "queue",
    *,
    failed: bool = False,
) -> list[AnalysisStage]:
    """按阶段图构造初始化/兼容快照。"""
    definitions = stage_definitions(mode)
    ids = stage_ids(mode)
    if active_stage not in ids:
        active_stage = ids[0]
    active_index = ids.index(active_stage)
    result: list[AnalysisStage] = []
    for index, definition in enumerate(definitions):
        status: AnalysisStageStatus = "pending"
        progress = 0
        if index < active_index or (active_stage == ids[-1] and not failed):
            status, progress = "done", 100
        elif index == active_index:
            status = "failed" if failed else "active"
            progress = 100 if failed else 10
        result.append(
            AnalysisStage(
                id=definition.id,
                label=definition.label,
                status=status,
                detail=definition.detail,
                progress=progress,
                publicMessage=definition.detail,
            )
        )
    return result


def canonicalize_stages(
    stages: Sequence[AnalysisStage],
    mode: ProgressMode,
) -> list[AnalysisStage]:
    """只保留当前图中的阶段，并按图排序。

    历史任务和单摄内部 pipeline 可能带有不属于顶层图的诊断阶段；这些阶段
    继续留在 pipeline result 中，但不会进入任务状态 API 的顶层进度条。
    """
    existing = {stage.id: stage for stage in stages if stage.id in stage_ids(mode)}
    return [existing[definition.id] for definition in stage_definitions(mode) if definition.id in existing]


def normalize_stage_snapshot(
    stages: Sequence[AnalysisStage],
    mode: ProgressMode,
) -> list[AnalysisStage]:
    """返回包含当前阶段图全部节点的规范快照。"""
    existing = {stage.id: stage for stage in canonicalize_stages(stages, mode)}
    return [
        existing.get(
            definition.id,
            AnalysisStage(
                id=definition.id,
                label=definition.label,
                status="pending",
                detail=definition.detail,
                progress=0,
                publicMessage=definition.detail,
            ),
        )
        for definition in stage_definitions(mode)
    ]


def validate_stage_snapshot(stages: Sequence[AnalysisStage], mode: ProgressMode) -> None:
    """校验顶层阶段快照的顺序和 active 唯一性。"""
    definitions = stage_definitions(mode)
    expected_ids = [definition.id for definition in definitions]
    actual_ids = [stage.id for stage in stages]
    unknown = [stage_id for stage_id in actual_ids if stage_id not in expected_ids]
    if unknown:
        raise StageTransitionError(f"unknown stages for {mode}: {unknown}")
    if actual_ids != sorted(actual_ids, key=expected_ids.index):
        raise StageTransitionError(f"stages are not ordered by {mode} progress graph")
    active = [stage for stage in stages if stage.status == "active"]
    if len(active) > 1:
        raise StageTransitionError("at most one top-level stage may be active")
    if active:
        active_index = expected_ids.index(active[0].id)
        for index, stage in enumerate(stages):
            if index < active_index and stage.status not in {"done", "skipped", "failed", "canceled"}:
                raise StageTransitionError(f"stage {stage.id} before active stage is not terminal")
            if index > active_index and stage.status != "pending":
                raise StageTransitionError(f"future stage {stage.id} must remain pending")


def merge_stage_event(
    stages: Sequence[AnalysisStage],
    event: AnalysisStage,
    mode: ProgressMode,
) -> list[AnalysisStage]:
    """把一个阶段事件合并到规范化快照。

    事件来自不同执行器，允许它跳过中间阶段（例如没有标定时直接报告
    skipped），但不会允许未知阶段污染顶层列表或让后续阶段提前完成。
    """
    definition = stage_definition(mode, event.id)
    definitions = stage_definitions(mode)
    ids = [item.id for item in definitions]
    existing = {stage.id: stage for stage in normalize_stage_snapshot(stages, mode)}
    prior = existing.get(event.id)
    payload = event.model_dump()
    now = _utc_now()
    if event.status == "active":
        payload["startedAt"] = payload.get("startedAt") or (prior.startedAt if prior else now)
        payload["progress"] = max(0, min(100, int(event.progress)))
    elif event.status in {"done", "skipped", "failed", "canceled"}:
        payload["startedAt"] = payload.get("startedAt") or (prior.startedAt if prior else now)
        payload["endedAt"] = payload.get("endedAt") or now
        payload["progress"] = 100 if event.status in {"done", "skipped"} else max(0, min(100, int(event.progress)))
        payload["durationMs"] = payload.get("durationMs") or _duration_ms(payload["startedAt"], payload["endedAt"])
    payload["publicMessage"] = payload.get("publicMessage") or payload.get("detail")
    existing[event.id] = AnalysisStage.model_validate(payload)

    event_index = ids.index(event.id)
    if event.status == "active":
        for index, definition in enumerate(definitions):
            current = existing.get(definition.id)
            if current is None or definition.id == event.id:
                continue
            if index < event_index and current.status == "active":
                existing[definition.id] = _terminalize(current, "done", now)
            elif index > event_index and current.status != "pending":
                # 延迟旧遥测不能重新点亮或完成未来阶段。
                existing[definition.id] = current.model_copy(update={"status": "pending", "progress": 0})
    elif event.status in {"done", "skipped", "failed", "canceled"}:
        for index, definition in enumerate(definitions[:event_index]):
            current = existing.get(definition.id)
            if current is not None and current.status == "active":
                existing[definition.id] = _terminalize(current, "done", now)

    result = [existing[definition.id] for definition in definitions if definition.id in existing]
    validate_stage_snapshot(result, mode)
    return result


def aggregate_progress(
    stages: Sequence[AnalysisStage],
    mode: ProgressMode,
    *,
    previous_progress: int = 0,
    view_progress: Mapping[str, object] | None = None,
    terminal_status: str | None = None,
) -> int:
    """按模式权重聚合 0~100 的单调总体进度。"""
    view_progress = view_progress or {}
    total = 0.0
    by_id = {stage.id: stage for stage in stages}
    for definition in stage_definitions(mode):
        stage = by_id.get(definition.id)
        fraction = 0.0
        if definition.id == "multiview-view-a":
            fraction = _view_fraction(view_progress.get("cam_1"), stage)
        elif definition.id == "multiview-view-b":
            fraction = _view_fraction(view_progress.get("cam_2"), stage)
        elif stage is not None:
            if stage.status in {"done", "skipped"}:
                fraction = 1.0
            elif stage.status in {"active", "failed", "canceled"}:
                fraction = max(0.0, min(1.0, stage.progress / 100.0))
        total += definition.weight * fraction

    if terminal_status == "succeeded":
        return 100
    return max(0, min(100, max(int(previous_progress), int(round(total)))))


def _view_fraction(value: object, stage: AnalysisStage | None) -> float:
    progress = None
    status = None
    if isinstance(value, Mapping):
        progress = value.get("progress")
        status = value.get("status")
    else:
        progress = getattr(value, "progress", None)
        status = getattr(value, "status", None)
    if progress is None and stage is not None:
        progress = stage.progress
        status = stage.status
    try:
        fraction = max(0.0, min(1.0, float(progress or 0) / 100.0))
    except (TypeError, ValueError):
        fraction = 0.0
    if status in {"succeeded", "completed", "done"}:
        return 1.0
    return fraction


def _terminalize(stage: AnalysisStage, status: AnalysisStageStatus, ended_at: str) -> AnalysisStage:
    return stage.model_copy(
        update={
            "status": status,
            "progress": 100,
            "endedAt": stage.endedAt or ended_at,
            "durationMs": stage.durationMs or _duration_ms(stage.startedAt, stage.endedAt or ended_at),
        }
    )


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _duration_ms(started: str | None, ended: str | None) -> int | None:
    if not started or not ended:
        return None
    from datetime import datetime

    try:
        return max(0, int((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() * 1000))
    except ValueError:
        return None
