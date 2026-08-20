"""Insight Engine 编排服务 —— 生成 / 落盘 / 再生成 performance_insights 产物。

持久化顺序（change design.md D2，防 /report 与 /result 双真值）：
① Worker 已保存基础 result.json；
② 本服务生成 insights 并原子写入 performance_insights.json；
③ model_copy(update=...) 更新 AnalysisArtifacts 的 performance_insights_* 四字段；
④ 原子重写 result.json（调用方负责同步内存 RESULTS cache）；
⑤ 最后才执行 Report Projector。

再生成（regenerate）：仅凭已落盘 result.json + artifacts 重跑（换 rule_profile 版本
无需重跑视觉 pipeline），含 evidence_input_signature 变化检测。

失败语义：洞察生成失败只降级报告洞察区块，绝不回退 demo，也绝不拖垮报告请求。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.performance_insights import PerformanceInsightsArtifact
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.performance_insights.evidence_assembler import (
    AssemblerInputs,
    assemble_evidence,
)
from app.services.performance_insights.rule_engine import run_insight_rules

logger = logging.getLogger(__name__)


def _load_structured_viz(storage, job_id: str) -> dict | None:
    """只读已落盘的 structured visualization data.json。"""
    if storage is None:
        return None
    path = storage.structured_visualization_data_path(job_id)
    if not path.exists():
        return None
    try:
        return storage.read_json(path)
    except Exception:  # noqa: BLE001 - 损坏的产物不应拖垮洞察
        logger.warning("structured visualization data 读取失败：%s", path)
        return None


def _resolve_windows(storage, job: AnalysisJobSummary, result: AnalysisPipelineResult):
    """解析有效时间窗口（clip / manual timeline / 回退），返回 (windows, source)。"""
    analysis_window = result.analysis_window or {}
    clip_start = analysis_window.get("clip_start_ms")
    clip_end = analysis_window.get("clip_end_ms")
    if clip_start is not None and clip_end is not None and clip_end > clip_start:
        return [(clip_start / 1000.0, clip_end / 1000.0)], "clip"

    capture_take_id = (
        getattr(job.metadata, "capture_take_id", None)
        if job.metadata is not None
        else None
    )
    if capture_take_id:
        from app.vision.pickleball_game_analysis.effective_time_windows import resolve_effective_windows

        windows = resolve_effective_windows(
            clip_start_ms=None,
            clip_end_ms=None,
            capture_take_id=capture_take_id,
        )
        if windows:
            return windows, "manual_timeline"
    return None, None


def _build_inputs(storage, job: AnalysisJobSummary, result: AnalysisPipelineResult) -> AssemblerInputs:
    windows, source = _resolve_windows(storage, job, result)
    # input_files 只放被消费的 evidence 产物；不含 result.json 本身
    # （insights 持久化会重写 result.json，签名自引用会导致缓存永久失效）。
    input_files: list = []
    if storage is not None:
        structured_path = storage.structured_visualization_data_path(job.id)
        if structured_path.exists():
            input_files.append(structured_path)
    return AssemblerInputs(
        result=result,
        structured_viz=_load_structured_viz(storage, job.id),
        effective_windows=windows,
        window_source=source,
        input_files=input_files,
    )


def generate_insights_for_result(
    job: AnalysisJobSummary,
    result: AnalysisPipelineResult | None,
    *,
    storage=None,
) -> tuple[PerformanceInsightsArtifact | None, str | None]:
    """生成 insights（不落盘）：返回 (artifact, None) 或 (None, 降级原因)。"""
    if result is None or result.status != "completed":
        return None, "pipeline 结果不可用，无法生成洞察。"
    try:
        inputs = _build_inputs(storage, job, result)
        bundle = assemble_evidence(job, inputs)
        artifact = run_insight_rules(job, bundle, generated_at=datetime.now(UTC).isoformat())
        return artifact, None
    except Exception as exc:  # noqa: BLE001 - 洞察失败不拖垮报告
        logger.warning("insights 生成失败（job=%s）：%s", job.id, exc)
        return None, f"洞察生成失败：{exc}"


def generate_and_persist_insights(
    job: AnalysisJobSummary,
    result: AnalysisPipelineResult,
    *,
    storage,
) -> tuple[AnalysisPipelineResult, PerformanceInsightsArtifact | None]:
    """生成 + 落盘 insights，并返回带 performance_insights_* 字段的更新 result。

    按固定顺序执行（design D2）：生成 insights → 原子写 performance_insights.json →
    model_copy 更新 artifacts 四字段 → 原子重写 result.json。
    调用方负责：同步内存 RESULTS cache，之后再执行 Report Projector。
    失败时返回 (原 result, None)——洞察状态保持缺失，报告显式降级。
    """
    if storage is None:
        return result, None
    artifact, reason = generate_insights_for_result(job, result, storage=storage)
    if artifact is None:
        # 显式记录失败状态到 artifacts（不影响视觉 pipeline 结果本身）。
        updated_artifacts = result.artifacts.model_copy(
            update={
                "performance_insights_status": "failed",
                "performance_insights_detail": reason,
            }
        )
        return result.model_copy(update={"artifacts": updated_artifacts}), None

    try:
        insights_path = storage.performance_insights_json_path(job.id)
        storage.write_json_atomic(insights_path, artifact.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 - 落盘失败不拖垮
        logger.warning("performance_insights.json 写入失败（job=%s）：%s", job.id, exc)
        updated_artifacts = result.artifacts.model_copy(
            update={
                "performance_insights_status": "failed",
                "performance_insights_detail": f"洞察产物写入失败：{exc}",
            }
        )
        return result.model_copy(update={"artifacts": updated_artifacts}), None

    artifacts_payload = result.artifacts.model_dump()
    artifacts_payload.update(
        {
            "performance_insights_json_path": str(insights_path),
            "performance_insights_url": f"/api/analysis/jobs/{job.id}/artifacts/performance-insights",
            "performance_insights_status": "available",
            "performance_insights_detail": "performance-insights.v1 已生成（rule profile 版本见产物）",
        }
    )
    from app.schemas.pipeline import AnalysisArtifacts

    updated_result = result.model_copy(
        update={"artifacts": AnalysisArtifacts.model_validate(artifacts_payload)}
    )
    # 原子重写 result.json，保证 /result 与 /report 状态一致。
    try:
        storage.write_json_atomic(storage.output_json_path(job.id), updated_result.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("result.json 二次写入失败（job=%s）：%s", job.id, exc)
    return updated_result, artifact


def regenerate_insights_for_job(
    job_id: str,
    *,
    storage,
    job: AnalysisJobSummary | None = None,
) -> tuple[PerformanceInsightsArtifact | None, str | None]:
    """独立再生成入口：仅凭已落盘 result.json + artifacts 重跑 insights。

    不触发视觉阶段重跑；用于 rule_profile 版本升级后重出洞察。
    同时重写 result.json 的 performance_insights_* 字段（保持 /result 一致）。
    """
    if storage is None:
        return None, "storage 不可用。"
    if job is None:
        from app.services.mock_analysis import get_mock_job

        job = get_mock_job(job_id)
    if job is None:
        return None, "任务不存在。"

    result_path = storage.output_json_path(job_id)
    if not result_path.exists():
        return None, "result.json 不存在，无法再生成洞察。"
    try:
        result = AnalysisPipelineResult.model_validate(storage.read_json(result_path))
    except Exception as exc:  # noqa: BLE001
        return None, f"result.json 读取失败：{exc}"
    if result.status != "completed":
        return None, "仅已完成的任务可再生成洞察。"

    # 缓存校验：evidence 输入未变 + rule 版本未变 → 直接返回现有产物。
    existing_path = storage.performance_insights_json_path(job_id)
    if existing_path.exists():
        artifact, reason = generate_insights_for_result(job, result, storage=storage)
        if artifact is not None:
            try:
                existing = PerformanceInsightsArtifact.model_validate(storage.read_json(existing_path))
                if (
                    existing.evidence_input_signature == artifact.evidence_input_signature
                    and existing.rule_profile_version == artifact.rule_profile_version
                ):
                    return existing, None
            except Exception:  # noqa: BLE001 - 损坏的现有产物直接覆盖
                pass

    _, artifact = generate_and_persist_insights(job, result, storage=storage)
    if artifact is None:
        return None, "再生成失败。"
    return artifact, None
