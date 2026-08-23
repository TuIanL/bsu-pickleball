"""多视角结果组装（multiview_result_composer）—— 把 P0 融合产物组装成 Parent 报告。

三步（对应 spec `multiview-analysis-result-composer`）：

1. **Select / Recompute**：用 fused trajectory + `metric_eligible` 重新计算位置类指标
   （distance / speed / heatmap / zone stats），**绝不复制 child 在 local frame 算好的指标**。
2. **Inherit**：从 reference view 继承 pose / ball / action / overlay 等非位置类产物
   （复制到 Parent 命名空间）。
3. **Normalize**：把 fused artifacts + diagnostics 发布到 Parent artifact 命名空间，
   写 `fused_manifest.json` 作为 Parent 唯一产品出口（前端只消费 manifest，永远不碰 fusion run）。

fallback 时同样经 Composer 重新生成 Parent 结果（内容可继承，所有权必须归 Parent）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.analysis import AnalysisJobSummary, build_match_context
from app.schemas.metrics import MetricStatus, PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
from app.services.analysis_progress import resolve_progress_mode, stage_definitions
from app.schemas.tracking import ImagePoint, ProjectedCourtPoint2D, ProjectedTrackPoint
from app.services.storage_service import StorageService
from app.vision.multiview.artifact import FUSED_DIAGNOSTICS_FILENAME, FUSED_TRAJECTORY_FILENAME
from app.vision.multiview.artifact import normalize_fusion_diagnostics
from app.vision.multiview.consumers import movement_points, visualization_points
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.metric_inputs import standard_court_metric_points
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell
from app.vision.player_tracking_engine.four_player_quality import build_quality_from_joint_artifacts

logger = logging.getLogger(__name__)


def _validate_ball_artifact_payloads(
    v3: dict[str, object] | None,
    evidence: dict[str, object] | None,
) -> str | None:
    """在 Parent 发布边界校验球产物的 schema、单位和质量字段。"""
    if evidence is not None:
        if evidence.get("schema_version") != "multiview_ball_stereo_evidence.v1":
            return "stereo evidence schema 版本不匹配"
        measurements = evidence.get("measurements")
        if not isinstance(measurements, list):
            return "stereo evidence measurements 必须是数组"
        for index, measurement in enumerate(measurements):
            if not isinstance(measurement, dict):
                return f"stereo evidence measurement[{index}] 不是对象"
            for field in ("take_timestamp_ms", "cam1_timestamp_ms", "cam2_timestamp_ms", "sync_error_ms"):
                value = measurement.get(field)
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    return f"stereo evidence {field} 必须是毫秒数值"
            if float(measurement.get("sync_error_ms", 0.0)) < 0:
                return "stereo evidence sync_error_ms 不能为负"

    if v3 is None:
        return None
    if v3.get("schema_version") != "reconstructed_ball_trajectory.v3":
        return "reconstructed ball trajectory schema 版本不匹配"
    overall = str(v3.get("overall_status", "UNAVAILABLE"))
    if overall not in {"FULL_ESTIMATED_3D", "PARTIAL_3D", "LANDING_ONLY", "UNAVAILABLE"}:
        return f"reconstructed ball trajectory overall status 非法：{overall}"
    coordinate_semantics = v3.get("coordinate_semantics")
    if not isinstance(coordinate_semantics, dict) or coordinate_semantics.get("xy") != "canonical_court_ft":
        return "reconstructed ball trajectory 缺少 canonical_court_ft 坐标声明"
    if coordinate_semantics.get("z") != "estimated_multiview_height_ft":
        return "reconstructed ball trajectory 缺少 estimated_multiview_height_ft 高度声明"
    segments = v3.get("segments")
    if not isinstance(segments, list):
        return "reconstructed ball trajectory segments 必须是数组"
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            return f"trajectory segment[{index}] 不是对象"
        quality = segment.get("quality")
        if isinstance(quality, dict):
            for field in ("observation_coverage", "predicted_ratio", "overall"):
                value = quality.get(field)
                if value is not None and (
                    not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1
                ):
                    return f"trajectory segment[{index}] quality.{field} 超出 0..1"
            rmse = quality.get("image_fit_rmse_px")
            if rmse is not None and (not isinstance(rmse, (int, float)) or (math.isfinite(float(rmse)) and float(rmse) < 0)):
                return f"trajectory segment[{index}] quality.image_fit_rmse_px 非法"
        metrics = segment.get("metrics")
        if isinstance(metrics, dict):
            speed = metrics.get("average_speed_kmh")
            if speed is not None and (
                not isinstance(speed, (int, float)) or not math.isfinite(float(speed)) or float(speed) < 0
            ):
                return f"trajectory segment[{index}] average_speed_kmh 必须是非负 km/h"
        samples = segment.get("samples")
        if not isinstance(samples, list):
            return f"trajectory segment[{index}] samples 必须是数组"
        for sample_index, sample in enumerate(samples):
            if not isinstance(sample, dict):
                return f"trajectory segment[{index}] sample[{sample_index}] 不是对象"
            timestamp = sample.get("timestamp_sec", sample.get("t_sec"))
            if timestamp is not None and (
                not isinstance(timestamp, (int, float)) or not math.isfinite(float(timestamp)) or float(timestamp) < 0
            ):
                return f"trajectory segment[{index}] sample[{sample_index}] 时间必须是非负秒数"
    return None

# 从 reference view 继承到 Parent 命名空间的产物契约：
#   artifacts 路径字段名 → (storage 访问器名, artifact 路由名, url 字段名, status 字段名 | None, 是否复制文件)
# 前端依赖 `*_url` 决定某个视觉层是否可加载，依赖 `*_status`/`*_detail` 展示层状态，
# 因此继承时必须同时补齐 url/status/detail，而不只是复制文件 + 填 `*_json_path`。
_INHERITED_ARTIFACT_SPECS: dict[str, tuple[str, str, str, str | None, bool]] = {
    "tracking_overlay_json_path": ("tracking_overlay_json_path", "tracking-overlay", "tracking_overlay_url", "tracking_overlay_status", True),
    "player_selection_json_path": ("player_selection_json_path", "player-selection", "player_selection_url", "player_selection_status", True),
    "player_selection_training_samples_json_path": (
        "player_selection_training_samples_json_path",
        "player-selection-training-samples",
        "player_selection_training_samples_url",
        None,
        True,
    ),
    "detections_jsonl_path": ("detections_jsonl_path", "detections", "detections_url", "detections_status", True),
    "ball_overlay_json_path": ("ball_overlay_json_path", "ball-overlay", "ball_overlay_url", "ball_overlay_status", True),
    "ball_trajectory_json_path": ("ball_trajectory_json_path", "ball-trajectory", "ball_trajectory_url", "ball_trajectory_status", True),
    "cleaned_ball_trajectory_json_path": (
        "cleaned_ball_trajectory_json_path",
        "cleaned-ball-trajectory",
        "cleaned_ball_trajectory_url",
        "cleaned_ball_trajectory_status",
        True,
    ),
    "bounce_events_json_path": ("bounce_events_json_path", "bounce-events", "bounce_events_url", "bounce_events_status", True),
    "reconstructed_ball_trajectory_json_path": (
        "reconstructed_ball_trajectory_json_path",
        "reconstructed-ball-trajectory",
        "reconstructed_ball_trajectory_url",
        "reconstructed_ball_trajectory_status",
        True,
    ),
    # 多视角球立体证据（不可变原始证据，joint 模式球 3D 链的输入证据）
    "multiview_ball_stereo_evidence_json_path": (
        "multiview_ball_stereo_evidence_path",
        "multiview-ball-stereo-evidence",
        "multiview_ball_stereo_evidence_url",
        "multiview_ball_stereo_evidence_status",
        True,
    ),
    # 叠加视频体积大（可达 GB 级），不复制到 Parent 命名空间，直接引用 child 的 URL。
    "analysis_overlay_video_path": ("analysis_overlay_video_path", "analysis-overlay-video", "analysis_overlay_video_url", "analysis_overlay_video_status", False),
    "heatmaps_manifest_json_path": ("heatmaps_manifest_json_path", "position-heatmaps", "heatmaps_url", "position_visualizations_status", True),
    "scatter_plots_manifest_json_path": ("scatter_plots_manifest_json_path", "position-scatter-plots", "scatter_plots_url", "position_visualizations_status", True),
    "pose_overlay_json_path": ("pose_overlay_json_path", "pose-overlay", "pose_overlay_url", "pose_overlay_status", True),
    "serve_events_json_path": ("serve_events_json_path", "serve-events", "serve_events_url", "serve_events_status", True),
    "serve_debug_candidates_json_path": (
        "serve_debug_candidates_json_path",
        "serve-debug-candidates",
        "serve_debug_candidates_url",
        None,
        True,
    ),
    "serve_score_series_json_path": ("serve_score_series_json_path", "serve-score-series", "serve_score_series_url", None, True),
    "serve_clips_manifest_json_path": ("serve_clips_manifest_json_path", "serve-clips-manifest", "serve_clips_manifest_url", None, True),
    "serve_debug_overlay_path": ("serve_debug_overlay_video_path", "serve-debug-overlay", "serve_debug_overlay_url", None, True),
    "player_trajectory_json_path": ("player_trajectory_json_path", "player-trajectories", "player_trajectory_url", "player_trajectory_status", True),
    "player_render_trajectory_json_path": ("player_render_trajectory_path", "player-render-trajectories", "player_render_trajectory_url", "player_render_trajectory_status", True),
    "court_view_roi_json_path": ("court_view_roi_json_path", "court-view-roi", "court_view_roi_url", "court_view_roi_status", True),
    "calibration_diagnostics_json_path": (
        "calibration_diagnostics_json_path",
        "calibration-diagnostics",
        "calibration_diagnostics_url",
        None,
        True,
    ),
}


def _copy_if_exists(src: Path, dst: Path) -> bool:
    """复制单个产物文件到目标；源缺失/目标已存在都幂等返回 False/True。"""
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _sample_timestamp_seconds(sample: dict[str, object]) -> float:
    """解析 fused 样本的秒级时间戳（2026-08-13 起 writer 必写 `timestamp_seconds`）。

    优先级：`timestamp_seconds` → 回退 `take_timestamp_ms / 1000.0`（兼容历史产物）
    → 仍缺失才 0.0。缺失时间戳会导致速度/厨房停留指标全 0、前端小地图时间窗口过滤全丢。
    """
    value = sample.get("timestamp_seconds")
    if value is not None and value != "":
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    take_ms = sample.get("take_timestamp_ms")
    if take_ms is not None and take_ms != "":
        try:
            return float(take_ms) / 1000.0
        except (TypeError, ValueError):
            pass
    return 0.0


def _copy_tree_if_exists(src: Path, dst: Path) -> bool:
    """复制产物目录（如 serve_clips / position heatmaps 目录）到目标。"""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dst)
    return True


def _build_aggregate_stages(
    *,
    view_a_status: str,
    view_b_status: str,
    fusion_performed: bool,
    composed: bool,
    execution_mode: str = "late_fusion_v1",
    include_legacy_joint_view_stages: bool = False,
    ball_analysis_status: str = "succeeded",
    ball_analysis_detail: str | None = None,
) -> list[PipelineStageResult]:
    """按执行模式构建与任务状态机相同的双摄聚合阶段。"""
    now = datetime.now(UTC).isoformat()
    mode = resolve_progress_mode("multiview", execution_mode)
    stages: list[PipelineStageResult] = []
    for definition in stage_definitions(mode):
        stage_id, label = definition.id, definition.label
        status = "done" if composed else "pending"
        detail = definition.detail
        progress = 100
        if stage_id == "multiview-input-check":
            status, progress = "done", 100
            detail = "双视频 / 双标定 / 同步信息检查通过"
        elif stage_id == "multiview-view-a":
            status = "done" if view_a_status in {"completed", "succeeded"} else "failed"
            detail = "A 机位视觉分析完成" if status == "done" else "A 机位分析失败"
        elif stage_id == "multiview-view-b":
            status = "done" if view_b_status in {"completed", "succeeded"} else "failed"
            detail = "B 机位视觉分析完成" if status == "done" else "B 机位分析失败"
        elif stage_id == "multiview-fusion":
            status = "done" if fusion_performed else "skipped"
            detail = "多视角球员轨迹融合" if fusion_performed else "未执行融合（单视角降级）"
        elif stage_id == "multiview-joint":
            status = "done" if composed else "pending"
            detail = "双摄协同跟踪完成" if composed else "双摄协同跟踪"
        elif stage_id == "multiview-ball-analysis":
            if not composed:
                status, progress = "pending", 0
                detail = "双摄球路分析"
            elif ball_analysis_status in {"succeeded", "available", "completed"}:
                status, progress = "done", 100
                detail = ball_analysis_detail or "双摄球路分析完成"
            elif ball_analysis_status in {"degraded", "partial", "landing_only"}:
                status, progress = "partial", 100
                detail = ball_analysis_detail or "双摄球路分析部分可用"
            elif ball_analysis_status in {"failed", "unavailable"}:
                status, progress = "unavailable", 100
                detail = ball_analysis_detail or "双摄球路分析不可用"
            else:
                status, progress = "unavailable", 100
                detail = ball_analysis_detail or f"双摄球路分析状态：{ball_analysis_status}"
        elif stage_id == "multiview-metrics":
            status = "done" if composed else "pending"
            detail = "基于 fused 轨迹重算运动指标"
        elif stage_id == "multiview-visualization":
            status = "done" if composed else "pending"
            detail = "生成双摄结果可视化产物"
        elif stage_id == "multiview-report":
            status = "done" if composed else "pending"
            detail = "生成 Parent 报告"
        stages.append(
            PipelineStageResult(
                id=stage_id,
                label=label,
                status=status,
                detail=detail,
                started_at=now,
                finished_at=now,
                progress=progress,
                public_message=detail,
            )
        )
    if include_legacy_joint_view_stages and mode == "joint_tracking_v2":
        # 旧的 result.json 消费方仍会读取 A/B 聚合节点；任务状态 API 会在
        # analysis_stages_from_pipeline 中按新 joint 图过滤掉它们。
        stages.extend(
            [
                PipelineStageResult(
                    id="multiview-view-a",
                    label="A 机位视觉分析",
                    status="done",
                    detail="A 机位视觉分析完成",
                    started_at=now,
                    finished_at=now,
                    progress=100,
                    public_message="A 机位视觉分析完成",
                ),
                PipelineStageResult(
                    id="multiview-view-b",
                    label="B 机位视觉分析",
                    status="done",
                    detail="B 机位视觉分析完成",
                    started_at=now,
                    finished_at=now,
                    progress=100,
                    public_message="B 机位视觉分析完成",
                ),
            ]
        )
    return stages


class MultiViewResultComposer:
    """把 P0 融合产物组装为 Parent-owned 结果。"""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()

    # ---- 第 1 步：Select / Recompute -------------------------------------

    def fused_to_projected_tracks(
        self,
        fused_artifact: dict[str, object],
        *,
        eligible_only: bool = False,
        roster_map: dict[str, str] | None = None,
    ) -> list[ProjectedTrackPoint]:
        """把 fused trajectory samples 转成标准球场轨迹点。

        `eligible_only=True` 仅取 metric-eligible 样本（进指标）；否则全部有坐标样本（可视化）。
        以 `global_player_id` 作为 `track_id`（可经 `roster_map` 映射为 canonical `Player_N`，
        stabilize-joint-global-player-roster：公开轨迹身份不得为 `global_player_`）。
        """
        points: list[ProjectedTrackPoint] = []
        for sample in fused_artifact.get("samples", []):
            if not isinstance(sample, dict):
                continue
            identity_status = str(sample.get("identity_status", "confirmed_observed"))
            if eligible_only and (
                not sample.get("metric_eligible")
                or identity_status not in {"confirmed_observed", "confirmed_recovered", "interpolated"}
            ):
                continue
            x = sample.get("x_ft")
            y = sample.get("y_ft")
            if x is None or y is None:
                continue
            raw_gid = str(sample.get("global_player_id", ""))
            points.append(
                ProjectedTrackPoint(
                    frame_index=int(sample.get("reference_frame_index", 0)),
                    timestamp_seconds=_sample_timestamp_seconds(sample),
                    track_id=str(roster_map.get(raw_gid, raw_gid) if roster_map else raw_gid),
                    image_point=ImagePoint(x=0.0, y=0.0),  # 指标只消费 court_point，图像点占位
                    confidence=1.0,
                    side="unknown",
                    court_point=ProjectedCourtPoint2D(x=float(x), y=float(y)),
                )
            )
        return points

    def recompute_metrics(
        self,
        fused_artifact: dict[str, object],
        match_context,
    ) -> PerformanceMetrics:
        """用 fused + metric_eligible 重算位置类指标（不复用 child local-frame 指标）。"""
        metric_tracks = standard_court_metric_points(
            self.fused_to_projected_tracks(fused_artifact, eligible_only=True)
        )
        ctx = match_context or build_match_context(None)
        statuses: dict[str, MetricStatus] = {}
        if ctx.enable_doubles_spacing:
            spacing_result = doubles_spacing(metric_tracks)
            statuses["doubles_spacing"] = MetricStatus(status="available")
        else:
            spacing_result = []
            statuses["doubles_spacing"] = MetricStatus(
                status="not_applicable",
                reason="singles_match",
                expected_player_count=ctx.expected_player_count,
            )
        return PerformanceMetrics(
            distances=total_distances(metric_tracks),
            speeds=speed_summaries(metric_tracks),
            kitchen_dwell=kitchen_dwell(metric_tracks),
            doubles_spacing=spacing_result,
            heatmap=generate_heatmap(metric_tracks),
            metric_statuses=statuses,
        )

    # ---- 第 2 步：Inherit reference-view 产物 ---------------------------------

    def _load_child_artifacts(self, child_id: str, capture_take_id: str | None) -> AnalysisArtifacts | None:
        """读取 reference child 已落盘的 AnalysisPipelineResult.artifacts（用于继承 status/detail）。"""
        if capture_take_id:
            self.storage.resolve_capture_job_root(child_id, capture_take_id)
        try:
            path = self.storage.output_json_path(child_id)
            if not path.exists():
                return None
            result = AnalysisPipelineResult.model_validate(self.storage.read_json(path))
            return result.artifacts
        except Exception:  # noqa: BLE001 - child 结果缺失/损坏时按无 status 处理
            return None

    def _inherit_reference_artifacts(
        self,
        parent_job_id: str,
        reference_child: AnalysisJobSummary,
        artifacts: AnalysisArtifacts,
    ) -> None:
        """把 reference child 已生成的单摄产物复制到 Parent 命名空间，并补齐 url/status/detail 契约。

        前端依赖 `*_url` 决定视觉层是否可加载、依赖 `*_status`/`*_detail` 展示层状态；
        仅填 `*_json_path` 会导致所有视觉层显示"不可用"。
        """
        capture_take_id = getattr(reference_child.metadata, "capture_take_id", None)
        if capture_take_id:
            # 重启后 _capture_job_roots 为空，必须重新注册 parent/child 的产物根，路径才能解析正确
            self.storage.resolve_capture_job_root(parent_job_id, capture_take_id)
            self.storage.resolve_capture_job_root(reference_child.id, capture_take_id)
        child_artifacts = self._load_child_artifacts(reference_child.id, capture_take_id)
        if child_artifacts is not None:
            artifacts.analysis_window = child_artifacts.analysis_window
            artifacts.analysis_overlay_video_metadata = child_artifacts.analysis_overlay_video_metadata

        for path_field, (getter_name, route, url_field, status_field, copy_file) in _INHERITED_ARTIFACT_SPECS.items():
            path_getter = getattr(self.storage, getter_name, None)
            if path_getter is None:
                continue
            src = path_getter(reference_child.id)
            dst = path_getter(parent_job_id)
            copied = _copy_if_exists(src, dst) if copy_file else False
            if copied:
                setattr(artifacts, path_field, str(dst))
                setattr(artifacts, url_field, f"/api/analysis/jobs/{parent_job_id}/artifacts/{route}")
            elif not copy_file and child_artifacts is not None:
                # 大视频不复制：直接引用 child 的 URL（内容即参考视角叠加视频）
                child_url = getattr(child_artifacts, url_field, None)
                if child_url:
                    setattr(artifacts, url_field, child_url)
            if status_field and child_artifacts is not None:
                child_status = getattr(child_artifacts, status_field, None)
                if child_status:
                    setattr(artifacts, status_field, child_status)
                detail_field = f"{status_field[: -len('status')]}detail"
                child_detail = getattr(child_artifacts, detail_field, None)
                if child_detail:
                    setattr(artifacts, detail_field, child_detail)

        # 目录型产物（position-heatmaps / position-scatter-plots / serve-clips）
        for field, dir_getter_name in (
            ("heatmaps_manifest", "heatmaps_dir"),
            ("scatter_plots_manifest", "scatter_plots_dir"),
            ("serve_clips_manifest", "serve_clips_dir"),
            ("position_visualizations", "position_visualizations_dir"),
        ):
            dir_getter = getattr(self.storage, dir_getter_name, None)
            if dir_getter is None:
                continue
            src = dir_getter(reference_child.id)
            dst = dir_getter(parent_job_id)
            _copy_tree_if_exists(src, dst)

    # ---- 第 3 步：Normalize 到 Parent namespace + manifest --------------------

    def publish_fused_artifacts(
        self,
        parent_job_id: str,
        fused_artifact: dict[str, object],
        diagnostics: dict[str, object],
        analysis_source: dict[str, str],
        *,
        fused_player_overlay_url: str | None = None,
    ) -> dict[str, object]:
        """把 fused + diagnostics 写入 Parent 命名空间，并写 fused_manifest.json 作为唯一出口。"""
        fused_path = self.storage.fused_trajectory_json_path(parent_job_id)
        diag_path = self.storage.fusion_diagnostics_json_path(parent_job_id)
        diagnostics = normalize_fusion_diagnostics(fused_artifact, diagnostics)
        evidence = {
            key: diagnostics[key]
            for key in (
                "secondary_available_samples",
                "dual_evidence_samples",
                "single_view_fallback_samples",
                "predicted_samples",
                "effective_multiview_ratio",
                "effective_mode",
            )
            if key in diagnostics
        }
        effective_mode = str(diagnostics.get("effective_mode", "single_view_fallback"))
        analysis_source = dict(analysis_source)
        analysis_source["effective_mode"] = effective_mode
        analysis_source.setdefault("requested_mode", analysis_source.get("mode"))
        if effective_mode != "multiview_fused" and analysis_source.get("reason") is None:
            analysis_source["reason"] = "; ".join(
                str(diagnostics.get(key))
                for key in ("authority_reason", "reason")
                if diagnostics.get(key)
            ) or "insufficient dual-view evidence"
        self.storage.write_json_atomic(fused_path, fused_artifact)
        self.storage.write_json_atomic(diag_path, diagnostics)

        manifest: dict[str, object] = {
            "schema_version": "fused_manifest.v1",
            "analysis_source": analysis_source,
            "evidence": evidence,
            "requested_mode": diagnostics.get("requested_mode"),
            "effective_mode": effective_mode,
            "canonical_frame_id": diagnostics.get("canonical_frame_id"),
            "artifacts": {
                "playerTrajectory": {
                    "source": "fused",
                    "url": f"/api/analysis/jobs/{parent_job_id}/artifacts/fused-trajectory",
                },
                "fusionDiagnostics": {
                    "url": f"/api/analysis/jobs/{parent_job_id}/artifacts/fusion-diagnostics",
                },
                "referenceOverlay": {"source": analysis_source.get("source_view")},
                "fusedPlayerOverlay": (
                    {"source": "fused", "url": fused_player_overlay_url}
                    if fused_player_overlay_url
                    else None
                ),
            },
        }
        self.storage.write_json_atomic(self.storage.fusion_manifest_json_path(parent_job_id), manifest)
        logger.info("发布 fused 产物到 Parent %s（manifest: %s）", parent_job_id, manifest)
        return manifest

    # ---- 组装 AnalysisPipelineResult -----------------------------------------

    def build_pipeline_result(
        self,
        *,
        job: AnalysisJobSummary,
        fused_artifact: dict[str, object],
        diagnostics: dict[str, object],
        analysis_source: dict[str, str],
        reference_child: AnalysisJobSummary | None,
        fusion_performed: bool,
        message: str,
    ) -> AnalysisPipelineResult:
        """组装 Parent 的 AnalysisPipelineResult（供现有报告构建路径消费）。"""
        match_context = build_match_context(
            job.metadata.matchFormat if hasattr(job.metadata, "matchFormat") else None
        )
        metrics = self.recompute_metrics(fused_artifact, match_context)
        tracks = self.fused_to_projected_tracks(fused_artifact)
        artifacts = AnalysisArtifacts()
        if reference_child is not None:
            self._inherit_reference_artifacts(job.id, reference_child, artifacts)
        # 前端用 source_video_url / video_id 作为视频源兜底；Parent 的 videoId 已在创建时
        # 从 reference child 继承（见 multiview_coordinator），此处显式补上 source_video_url。
        video_id = reference_child.videoId if reference_child else None
        if video_id and not artifacts.source_video_url:
            artifacts.source_video_url = f"/api/videos/{video_id}/stream"
        self.publish_fused_artifacts(
            job.id,
            fused_artifact,
            diagnostics,
            analysis_source,
        )
        view_a = job.viewRuns.get("cam_1") if job.viewRuns else None
        view_b = job.viewRuns.get("cam_2") if job.viewRuns else None
        stages = _build_aggregate_stages(
            view_a_status=view_a.status if view_a else "pending",
            view_b_status=view_b.status if view_b else "pending",
            fusion_performed=fusion_performed,
            composed=True,
            execution_mode=job.executionMode,
            include_legacy_joint_view_stages=True,
        )
        return AnalysisPipelineResult(
            job_id=job.id,
            video_id=video_id,
            calibration_id=reference_child.calibrationId if reference_child else None,
            status="completed",
            generated_at=datetime.now(UTC),
            stages=stages,
            tracks=tracks,
            metrics=metrics,
            artifacts=artifacts,
            message=message,
            match_context=match_context,
            observed_player_count=len({t.track_id for t in tracks if t.track_id}),
            analysis_window=artifacts.analysis_window,
            requested_execution_mode=job.executionMode,
            effective_multiview_mode=str(diagnostics.get("effective_mode", "single_view_fallback")),
            execution_mode=str(diagnostics.get("execution_mode")) if diagnostics.get("execution_mode") else None,
            authoritative_joint_eligible=(
                bool(diagnostics["authoritative_joint_eligible"])
                if "authoritative_joint_eligible" in diagnostics
                else None
            ),
        )

    def _publish_joint_visual_artifacts(
        self,
        *,
        job: AnalysisJobSummary,
        joint_output,
        reference_view_id: str,
        fused_artifact: dict[str, object],
        artifacts: AnalysisArtifacts,
        roster_map: dict[str, str] | None = None,
        roster_entries: list[dict[str, object]] | None = None,
    ) -> None:
        """joint 模式产出前端视觉层产物（2026-08-13 修复：此前 artifacts 全空）。

        - tracking_overlay（框架）：从 debug trace 聚合 reference view 检测，写 Parent 命名空间；
        - heatmaps / scatter / structured data：从 fused metric tracks 生成（canonical Player_N）；
        - roster.v1（诊断 / 映射 contract）：Global → Player_N 映射；
        - pose_overlay / render_trajectory / detections：joint 模式无法真实生成，显式 unavailable + reason。
        """
        from app.core.config import get_settings
        from app.services.joint_visual_artifacts import (
            JOINT_DETECTIONS_UNAVAILABLE,
            JOINT_POSE_UNAVAILABLE,
            JOINT_RENDER_TRAJECTORY_UNAVAILABLE,
            build_joint_position_visualizations,
            build_joint_roster_artifact,
            build_joint_tracking_overlay,
        )

        frame_size = (
            joint_output.diagnostics.get("frame_size")
            if isinstance(joint_output.diagnostics, dict)
            else None
        )
        fps = float(job.sourceFps or 0.0)
        stride = int(job.frameStride or 1)
        video_id = job.videoId

        # 1) tracking_overlay（框架）：debug trace 聚合。
        #    joint 模式正式视觉层已由 fused_player_overlay 承担（add-multiview-
        #    fused-player-overlay）；tracking_overlay 保留为历史 / debug fallback，
        #    前端加载优先级 fused overlay → trackingOverlay。
        debug_trace = getattr(joint_output, "debug_trace", None)
        if isinstance(debug_trace, dict) and isinstance(debug_trace.get("ticks"), list):
            try:
                overlay = build_joint_tracking_overlay(
                    job_id=job.id,
                    video_id=video_id,
                    debug_trace=debug_trace,
                    frame_size=frame_size if isinstance(frame_size, dict) else None,
                    fps=fps,
                    frame_stride=stride,
                    reference_view_id=reference_view_id,
                )
                self.storage.write_json(
                    self.storage.tracking_overlay_json_path(job.id), overlay.model_dump(mode="json")
                )
                artifacts.tracking_overlay_json_path = str(self.storage.tracking_overlay_json_path(job.id))
                artifacts.tracking_overlay_url = f"/api/analysis/jobs/{job.id}/artifacts/tracking-overlay"
                artifacts.tracking_overlay_status = overlay.status
                artifacts.tracking_overlay_detail = (
                    f"{overlay.detail}（joint 模式 debug fallback，正式视觉层见 fused_player_overlay）"
                )
            except Exception as exc:  # noqa: BLE001 - 视觉层失败不中断 compose
                logger.warning("joint tracking overlay build failed: %s", exc)
                artifacts.tracking_overlay_status = "unavailable"
                artifacts.tracking_overlay_detail = f"joint tracking overlay 生成失败：{exc}"

        # 2) heatmaps / scatter / structured data：从 fused metric-eligible 轨迹生成（canonical Player_N）
        metric_tracks = standard_court_metric_points(
            self.fused_to_projected_tracks(fused_artifact, eligible_only=True, roster_map=roster_map)
        )
        viz_fields = build_joint_position_visualizations(
            storage=self.storage,
            job_id=job.id,
            metric_tracks=metric_tracks,
            language=getattr(get_settings(), "visualization_language", "zh"),
            roster_map=roster_map,
        )
        for key, value in viz_fields.items():
            setattr(artifacts, key, value)
        self._augment_visualization_identity_quality(
            job_id=job.id,
            samples=list(fused_artifact.get("samples") or []),
            roster_map=roster_map or {},
        )

        # 2b) global-player-roster.v1（诊断 / 映射 contract，非用户展示 identity）
        if roster_entries is not None:
            expected_count = int(
                joint_output.diagnostics.get("expected_player_count", 4)
                if isinstance(joint_output.diagnostics, dict)
                else 4
            )
            roster_state = (
                joint_output.diagnostics.get("roster_state", "BOOTSTRAPPING")
                if isinstance(joint_output.diagnostics, dict)
                else "BOOTSTRAPPING"
            )
            roster_fields = build_joint_roster_artifact(
                storage=self.storage,
                job_id=job.id,
                roster=roster_entries,
                roster_map=roster_map or {},
                expected_player_count=expected_count,
                status="confirmed" if roster_state == "ROSTER_ACTIVE" else "bootstrap",
            )
            for key, value in roster_fields.items():
                setattr(artifacts, key, value)

        # 2c) multiview-fused-player-overlay.v1（joint 模式正式球员叠加层，
        #      add-multiview-fused-player-overlay）：F0/F1 evidence + roster +
        #      view geometry 只读消费，不依赖 debug trace。
        self._publish_joint_fused_player_overlay(
            job=job,
            joint_output=joint_output,
            reference_view_id=reference_view_id,
            frame_size=frame_size if isinstance(frame_size, dict) else None,
            roster_map=roster_map,
            artifacts=artifacts,
        )

        # 2d) player-display-diagnostics.v1（逐球员逐 stage 显示漏斗，
        #      add-player-display-diagnostics）：只读 observability，失败不影响核心结果。
        self._publish_joint_player_display_diagnostics(
            job=job,
            joint_output=joint_output,
            reference_view_id=reference_view_id,
            artifacts=artifacts,
        )

        self._publish_four_player_identification_quality(
            job=job,
            joint_output=joint_output,
            artifacts=artifacts,
        )

        # 3) 无法真实生成的产物显式 unavailable（不静默缺失）
        artifacts.pose_overlay_status = "unavailable"
        artifacts.pose_overlay_detail = JOINT_POSE_UNAVAILABLE
        artifacts.player_render_trajectory_status = "unavailable"
        artifacts.player_render_trajectory_detail = JOINT_RENDER_TRAJECTORY_UNAVAILABLE
        artifacts.detections_status = "unavailable"
        artifacts.detections_detail = JOINT_DETECTIONS_UNAVAILABLE

    def _publish_joint_ball_artifacts(
        self,
        *,
        job: AnalysisJobSummary,
        ball_analysis: object | None,
        artifacts: AnalysisArtifacts,
    ) -> tuple[str, str]:
        """发布 Parent-owned v3/evidence，并返回球路阶段状态与 detail。"""
        if ball_analysis is None:
            detail = "joint 运行未生成 canonical 球路阶段结果"
            artifacts.reconstructed_ball_trajectory_status = "unavailable"
            artifacts.reconstructed_ball_trajectory_detail = detail
            artifacts.multiview_ball_stereo_evidence_status = "unavailable"
            artifacts.multiview_ball_stereo_evidence_detail = detail
            return "unavailable", detail

        v3 = getattr(ball_analysis, "v3_trajectory", None)
        evidence = getattr(ball_analysis, "stereo_evidence", None)
        output_status = str(getattr(ball_analysis, "status", "unavailable"))
        output_detail = str(getattr(ball_analysis, "detail", "双摄球路分析不可用"))
        if not isinstance(v3, dict):
            v3 = None
        if not isinstance(evidence, dict):
            evidence = None

        v3_path = self.storage.reconstructed_ball_trajectory_json_path(job.id)
        evidence_path = self.storage.multiview_ball_stereo_evidence_path(job.id)

        validation_error = _validate_ball_artifact_payloads(v3, evidence)
        if validation_error is not None:
            detail = f"双摄球产物校验失败：{validation_error}"
            artifacts.reconstructed_ball_trajectory_status = "failed"
            artifacts.reconstructed_ball_trajectory_detail = detail
            artifacts.multiview_ball_stereo_evidence_status = "failed"
            artifacts.multiview_ball_stereo_evidence_detail = detail
            return "failed", detail

        def write_immutable(path: Path, payload: dict[str, object]) -> None:
            # hash 对未包含 hash 字段的 canonical JSON 计算，便于技术详情核验。
            body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            enriched = dict(payload)
            enriched["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
            self.storage.write_json_atomic(path, enriched)

        if evidence is not None and evidence.get("schema_version") == "multiview_ball_stereo_evidence.v1":
            write_immutable(evidence_path, evidence)
            artifacts.multiview_ball_stereo_evidence_json_path = str(evidence_path)
            artifacts.multiview_ball_stereo_evidence_url = (
                f"/api/analysis/jobs/{job.id}/artifacts/multiview-ball-stereo-evidence"
            )
            measurements = evidence.get("measurements")
            evidence_status = "available" if isinstance(measurements, list) and measurements else "unavailable"
            artifacts.multiview_ball_stereo_evidence_status = evidence_status
            artifacts.multiview_ball_stereo_evidence_detail = (
                f"已发布 {len(measurements or [])} 条 canonical 双摄球证据"
                if evidence_status == "available" else "未形成有效双摄球测量，保留诊断证据"
            )
        else:
            artifacts.multiview_ball_stereo_evidence_status = "failed"
            artifacts.multiview_ball_stereo_evidence_detail = "stereo evidence 缺失或 schema 版本不匹配"

        if v3 is not None and v3.get("schema_version") == "reconstructed_ball_trajectory.v3":
            write_immutable(v3_path, v3)
            artifacts.reconstructed_ball_trajectory_json_path = str(v3_path)
            artifacts.reconstructed_ball_trajectory_url = (
                f"/api/analysis/jobs/{job.id}/artifacts/reconstructed-ball-trajectory"
            )
            overall = str(v3.get("overall_status", "UNAVAILABLE"))
            v3_status = {
                "FULL_ESTIMATED_3D": "succeeded",
                "PARTIAL_3D": "degraded",
                "LANDING_ONLY": "degraded",
                "UNAVAILABLE": "unavailable",
            }.get(overall, "unavailable")
            artifacts.reconstructed_ball_trajectory_status = v3_status
            artifacts.reconstructed_ball_trajectory_detail = output_detail
            return v3_status, output_detail

        artifacts.reconstructed_ball_trajectory_status = "failed" if output_status == "failed" else "unavailable"
        artifacts.reconstructed_ball_trajectory_detail = output_detail
        return artifacts.reconstructed_ball_trajectory_status, output_detail

    def _publish_joint_fused_player_overlay(
        self,
        *,
        job: AnalysisJobSummary,
        joint_output,
        reference_view_id: str,
        frame_size: dict[str, int] | None,
        roster_map: dict[str, str] | None,
        artifacts: AnalysisArtifacts,
    ) -> None:
        """joint 模式发布 `multiview-fused-player-overlay.v1` 正式叠加层。

        数据源：F0 snapshot + accepted F1 recovered observations + final fused
        trajectory + roster map + view geometry（经 executor 挂到
        `joint_output.overlay_context`），**不依赖 debug trace**。
        overlay_context 缺失 / 构建失败 → 显式 unavailable，不中断 compose。
        """
        try:
            overlay_context = getattr(joint_output, "overlay_context", None)
            if not isinstance(overlay_context, dict):
                artifacts.fused_player_overlay_status = "unavailable"
                artifacts.fused_player_overlay_detail = "joint output 缺少 overlay context（view geometry / F1 evidence）"
                return
            from app.vision.multiview.fused_overlay_builder import (
                FusedPlayerOverlayBuilder,
            )
            from app.vision.multiview.fused_overlay_bundle import (
                build_overlay_evidence_bundle,
            )
            from app.vision.multiview.fused_overlay_types import (
                build_fused_player_overlay_payload,
            )

            geometry_map = overlay_context.get("view_geometry") or {}
            if not geometry_map or reference_view_id not in geometry_map:
                artifacts.fused_player_overlay_status = "unavailable"
                artifacts.fused_player_overlay_detail = "缺少 reference view 投影几何，无法生成 fused overlay"
                return

            bundle = build_overlay_evidence_bundle(
                f0_snapshot=getattr(joint_output, "f0_snapshot", None),
                reference_view_id=reference_view_id,
                roster_map=dict(roster_map or {}),
                view_geometry=geometry_map,
                fused_trajectory=joint_output.trajectory if isinstance(joint_output.trajectory, dict) else None,
                recovered_observations=list(overlay_context.get("recovered_observations") or []),
                final_source=str(overlay_context.get("final_source", "first_pass_f0")),
                bootstrap_backfill=getattr(joint_output, "bootstrap_display_backfill", None),
            )
            builder = FusedPlayerOverlayBuilder()
            frames = builder.build(bundle=bundle)
            expected_player_count = int(
                joint_output.diagnostics.get("expected_player_count", 4)
                if isinstance(joint_output.diagnostics, dict)
                else 4
            )
            payload = build_fused_player_overlay_payload(
                job_id=job.id,
                video_id=job.videoId,
                reference_view_id=reference_view_id,
                frame_size=frame_size,
                frames=frames,
                status="available" if frames and any(f.players for f in frames) else "no_detections",
                detail=(
                    f"已生成 {len(frames)} 帧 fused overlay（{expected_player_count} 名 canonical 球员，"
                    f"来源 F0/F1 evidence + roster + {reference_view_id} 几何）"
                ),
            )
            overlay_path = self.storage.fused_player_overlay_json_path(job.id)
            overlay_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage.write_json(overlay_path, payload)
            artifacts.fused_player_overlay_json_path = str(overlay_path)
            artifacts.fused_player_overlay_url = f"/api/analysis/jobs/{job.id}/artifacts/fused-player-overlay"
            artifacts.fused_player_overlay_status = payload["status"]
            artifacts.fused_player_overlay_detail = payload["detail"]
        except Exception as exc:  # noqa: BLE001 - fused overlay 失败不中断 compose
            logger.warning("joint fused player overlay build failed: %s", exc)
            artifacts.fused_player_overlay_status = "unavailable"
            artifacts.fused_player_overlay_detail = f"fused player overlay 生成失败：{exc}"

    def _publish_joint_player_display_diagnostics(
        self,
        *,
        job: AnalysisJobSummary,
        joint_output,
        reference_view_id: str,
        artifacts: AnalysisArtifacts,
    ) -> None:
        """joint 模式发布 `player-display-diagnostics.v1` 显示漏斗产物。

        数据源：joint run 内已构建的 `display_diagnostics_payload`（只读 observability，
        不依赖 debug trace）。产物缺失 / 构建失败 → 显式 unavailable/failed，
        不中断 compose，不影响核心 joint result。
        """
        try:
            payload = getattr(joint_output, "display_diagnostics_payload", None)
            if not isinstance(payload, dict):
                # fix-multiview-player-identity D1：payload 缺失/非 dict 时仍写盘占位
                # artifact（status=unavailable），保证查询 API 不因文件缺失返回 404。
                payload = {
                    "schema_version": "player-display-diagnostics.v1",
                    "job_id": job.id,
                    "video_id": (
                        getattr(joint_output, "capture_take_id", None) or job.videoId
                    ),
                    "reference_view_id": reference_view_id,
                    "status": "unavailable",
                    "detail": "joint output 缺少 player display diagnostics 产物",
                    "rows": [],
                }
            diag_path = self.storage.player_display_diagnostics_json_path(job.id)
            diag_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage.write_json(diag_path, payload)
            artifacts.player_display_diagnostics_json_path = str(diag_path)
            artifacts.player_display_diagnostics_url = (
                f"/api/analysis/jobs/{job.id}/artifacts/player-display-diagnostics"
            )
            artifacts.player_display_diagnostics_status = str(payload.get("status", "available"))
            artifacts.player_display_diagnostics_detail = str(payload.get("detail", ""))
            error = getattr(joint_output, "display_diagnostics_error", None)
            if error:
                artifacts.player_display_diagnostics_status = "failed"
                artifacts.player_display_diagnostics_detail = str(error)
        except Exception as exc:  # noqa: BLE001 - 显示诊断失败不中断 compose
            logger.warning("joint player display diagnostics publish failed: %s", exc)
            artifacts.player_display_diagnostics_status = "failed"
            artifacts.player_display_diagnostics_detail = f"player display diagnostics 发布失败：{exc}"

    def _publish_four_player_identification_quality(
        self,
        *,
        job: AnalysisJobSummary,
        joint_output,
        artifacts: AnalysisArtifacts,
    ) -> None:
        try:
            roster_path = self.storage.roster_manifest_json_path(job.id)
            diagnostics_path = self.storage.player_display_diagnostics_json_path(job.id)
            if not roster_path.exists():
                raise ValueError("roster artifact unavailable")
            quality = build_quality_from_joint_artifacts(
                job_id=job.id,
                trajectory=joint_output.trajectory,
                roster=self.storage.read_json(roster_path),
                display_diagnostics=(
                    self.storage.read_json(diagnostics_path) if diagnostics_path.exists() else None
                ),
                runtime_diagnostics=getattr(joint_output, "diagnostics", None),
                algorithm_version="motion-aware-v1+clothing-hsv-lab.v1",
            )
            path = self.storage.four_player_identification_quality_json_path(job.id)
            self.storage.write_json_atomic(path, quality.model_dump(mode="json"))
            artifacts.four_player_identification_quality_json_path = str(path)
            artifacts.four_player_identification_quality_url = (
                f"/api/analysis/jobs/{job.id}/artifacts/four-player-identification-quality"
            )
            artifacts.four_player_identification_quality_status = quality.status
            artifacts.four_player_identification_quality_detail = (
                "四人识别质量通过"
                if quality.verdict == "pass"
                else f"四人识别质量未通过：{', '.join(quality.failure_reasons)}"
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics must not abort the core result
            artifacts.four_player_identification_quality_status = "failed"
            artifacts.four_player_identification_quality_detail = f"四人识别质量产物生成失败：{exc}"

    def _augment_visualization_identity_quality(
        self,
        *,
        job_id: str,
        samples: list[object],
        roster_map: dict[str, str],
    ) -> None:
        """Add accepted/quarantine sufficiency facts without changing visualization math."""
        path = self.storage.structured_visualization_data_path(job_id)
        if not path.exists():
            return
        accepted_statuses = {"confirmed_observed", "confirmed_recovered", "interpolated"}
        attempted_ticks = len({
            int(sample.get("reference_frame_index", 0))
            for sample in samples if isinstance(sample, dict)
        })
        per_player: dict[str, dict[str, object]] = {}
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            player_id = roster_map.get(str(sample.get("global_player_id") or ""))
            if not player_id:
                continue
            summary = per_player.setdefault(player_id, {
                "accepted_count": 0,
                "quarantined_count": 0,
                "accepted_ticks": set(),
                "quarantine_reason_summary": {},
            })
            identity_status = str(sample.get("identity_status", "confirmed_observed"))
            accepted = bool(sample.get("metric_eligible")) and identity_status in accepted_statuses
            if accepted:
                summary["accepted_count"] = int(summary["accepted_count"]) + 1
                cast_ticks = summary["accepted_ticks"]
                if isinstance(cast_ticks, set):
                    cast_ticks.add(int(sample.get("reference_frame_index", 0)))
            else:
                summary["quarantined_count"] = int(summary["quarantined_count"]) + 1
                reason = str(sample.get("quarantine_reason") or identity_status or "untrusted_identity")
                reasons = summary["quarantine_reason_summary"]
                if isinstance(reasons, dict):
                    reasons[reason] = int(reasons.get(reason, 0)) + 1
        serialized: dict[str, dict[str, object]] = {}
        for player_id, summary in sorted(per_player.items()):
            accepted_ticks = summary.pop("accepted_ticks")
            accepted_tick_count = len(accepted_ticks) if isinstance(accepted_ticks, set) else 0
            coverage = accepted_tick_count / attempted_ticks if attempted_ticks else 0.0
            serialized[player_id] = {
                **summary,
                "attempted_ticks": attempted_ticks,
                "accepted_tick_count": accepted_tick_count,
                "coverage": coverage,
                "sufficiency": "sufficient" if coverage >= 0.70 else "insufficient",
            }
        payload = self.storage.read_json(path)
        payload["identity_quality"] = {
            "schema_version": "visualization-identity-quality.v1",
            "accepted_identity_statuses": sorted(accepted_statuses),
            "players": serialized,
        }
        self.storage.write_json_atomic(path, payload)

    def compose_joint_result(
        self,
        *,
        job: AnalysisJobSummary,
        joint_output,
        reference_view_id: str,
        message: str,
        refinement: dict[str, object] | None = None,
        ball_analysis: object | None = None,
    ) -> AnalysisPipelineResult:
        """joint_tracking_v2 的 Parent 结果组装：从 Parent-owned JointRun 获取，GlobalPlayer 标签。

        - 复用既有位置类指标数学（fused_to_projected_tracks + recompute_metrics）；
        - track_id = `GlobalPlayer_<id>`，overlay 标签来自全局身份而非 child 局部 Player_<id>；
        - 不依赖 reference child 继承路径。
        """
        match_context = build_match_context(
            job.metadata.matchFormat if hasattr(job.metadata, "matchFormat") else None
        )
        synthetic: dict[str, object] = {
            "schema_version": joint_output.trajectory.get("schema_version", "fused_player_trajectory.v2"),
            "samples": [
                {
                    "global_player_id": s.global_player_id,
                    "take_timestamp_ms": s.take_timestamp_ms,
                    "timestamp_seconds": s.timestamp_seconds,
                    "reference_frame_index": s.reference_frame_index,
                    "x_ft": s.x_ft,
                    "y_ft": s.y_ft,
                    "fusion_status": s.fusion_status,
                    "metric_eligible": s.metric_eligible,
                    "observation_origin": s.observation_origin,
                    "identity_status": s.identity_status,
                    "identity_epoch": s.identity_epoch,
                    "binding_provenance": s.binding_provenance,
                    "quarantine_reason": s.quarantine_reason,
                }
                for s in joint_output.normalized.samples
            ],
        }
        # Global Roster 公开映射（stabilize-joint-global-player-roster）：
        # reference view binding 决定 canonical Player_N（display anchor），缺 reference 用 slot 顺序 fallback。
        roster_entries = (
            joint_output.diagnostics.get("roster", [])
            if isinstance(joint_output.diagnostics, dict)
            else []
        )
        roster_map = _build_roster_map(roster_entries)
        metrics = self.recompute_metrics(synthetic, match_context)
        tracks = self.fused_to_projected_tracks(synthetic, roster_map=roster_map)  # track_id = Player_N
        artifacts = AnalysisArtifacts()
        artifacts.analysis_window = joint_output.diagnostics.get("analysis_window")
        video_id = job.videoId
        if video_id and not artifacts.source_video_url:
            artifacts.source_video_url = f"/api/videos/{video_id}/stream"
        self._publish_joint_visual_artifacts(
            job=job,
            joint_output=joint_output,
            reference_view_id=reference_view_id,
            fused_artifact=synthetic,
            artifacts=artifacts,
            roster_map=roster_map,
            roster_entries=roster_entries,
        )
        ball_status, ball_detail = self._publish_joint_ball_artifacts(
            job=job,
            ball_analysis=ball_analysis,
            artifacts=artifacts,
        )
        self.publish_fused_artifacts(
            job.id,
            joint_output.trajectory,
            joint_output.diagnostics,
            {
                "mode": "joint_tracking_v2",
                "source_job_id": job.id,
                "source_view": reference_view_id,
                "reason": "joint run",
                "execution_mode": str(joint_output.diagnostics.get("execution_mode", "unknown")),
                "authoritative_joint_eligible": str(
                    bool(joint_output.diagnostics.get("authoritative_joint_eligible", False))
                ),
            },
            fused_player_overlay_url=artifacts.fused_player_overlay_url,
        )
        if refinement is not None:
            # 把 offline refinement 生命周期写进 manifest(refinement.status / final_source / artifacts)
            manifest_path = self.storage.fusion_manifest_json_path(job.id)
            try:
                manifest = self.storage.read_json(manifest_path) or {}
                manifest["refinement"] = refinement
                self.storage.write_json_atomic(manifest_path, manifest)
            except Exception:  # noqa: BLE001
                pass
        # joint 模式下 viewRuns 创建后不再更新（停在 queued），A/B 状态取 joint run 完成结论，
        # 否则聚合 stage 会误报"A/B 机位分析失败"（2026-08-13 修复）。
        stages = _build_aggregate_stages(
            view_a_status="succeeded",
            view_b_status="succeeded",
            fusion_performed=True,
            composed=True,
            execution_mode=job.executionMode,
            include_legacy_joint_view_stages=True,
            ball_analysis_status=ball_status,
            ball_analysis_detail=ball_detail,
        )
        return AnalysisPipelineResult(
            job_id=job.id,
            video_id=video_id,
            calibration_id=job.calibrationId,
            status="completed",
            generated_at=datetime.now(UTC),
            stages=stages,
            tracks=tracks,
            metrics=metrics,
            artifacts=artifacts,
            message=message,
            match_context=match_context,
            observed_player_count=len({t.track_id for t in tracks if t.track_id}),
            analysis_window=artifacts.analysis_window,
            requested_execution_mode=job.executionMode,
            effective_multiview_mode=str(joint_output.diagnostics.get("effective_mode", "multiview_fused")),
            execution_mode=(
                str(joint_output.diagnostics["execution_mode"])
                if joint_output.diagnostics.get("execution_mode")
                else None
            ),
            authoritative_joint_eligible=(
                bool(joint_output.diagnostics["authoritative_joint_eligible"])
                if "authoritative_joint_eligible" in joint_output.diagnostics
                else None
            ),
        )


def _build_roster_map(roster_entries: list[dict[str, object]]) -> dict[str, str]:
    """由 joint run 的 roster 快照构建 `global_player_id → canonical Player_N` 映射。

    display anchor：优先采用 reference view binding 决定的 `player_id`；缺 reference binding
    或冲突时用 deterministic slot 顺序 fallback（Player_1..N 按 roster 顺序分配，避免重跑漂移）。
    """
    roster_map: dict[str, str] = {}
    used_ids: set[str] = set()
    next_slot = 1
    for entry in roster_entries:  # joint run 已按 global_player_id 排序（稳定）
        gid = str(entry.get("global_player_id", ""))
        pid = entry.get("player_id")
        if pid and str(pid) not in used_ids:
            roster_map[gid] = str(pid)
            used_ids.add(str(pid))
            continue
        while f"Player_{next_slot}" in used_ids:
            next_slot += 1
        fallback = f"Player_{next_slot}"
        roster_map[gid] = fallback
        used_ids.add(fallback)
        next_slot += 1
    return roster_map


def build_fallback_fused_artifact(
    *,
    run_id: str,
    capture_take_id: str,
    reference_view_id: str,
    observations,
    sync_quality: str,
    reference_orientation=None,
    canonical_frame_id: str | None = None,
) -> dict[str, object]:
    """单视角降级时的"伪 fused"轨迹：直接取 reference view 的 canonical 观测。

    用于 `A✓+B✕` / `A✓+B✓+sync✕` 分支——不执行真正融合，但 Composer 仍按
    fused 契约重算指标（metric-eligible = 观测点），保证报告与 fallback 前一致。
    """
    from app.vision.multiview.court_frame import local_to_canonical

    samples: list[dict[str, object]] = []
    for obs in observations:
        canonical = local_to_canonical(obs.local_x_ft, obs.local_y_ft, reference_orientation)
        samples.append(
            {
                "global_player_id": obs.view_player_id,
                "timestamp_seconds": obs.timestamp_seconds,
                "take_timestamp_ms": obs.timestamp_seconds * 1000.0,
                "reference_frame_index": obs.source_frame_index,
                "x_ft": canonical[0],
                "y_ft": canonical[1],
                "fusion_status": "single_view_fallback",
                "fusion_confidence": 0.0,
                "contributing_views": [reference_view_id],
                "selected_view": reference_view_id,
                "view_observations": {},
                "association_confidence": 0.0,
                "sync_quality": sync_quality,
                "court_frame_version": "canonical_court_frame.v1",
                "canonical_frame_id": canonical_frame_id,
                "measurement_source": "single_view_fallback",
                "metric_eligible": True,
            }
        )
    return {
        "schema_version": "fused_player_trajectory.v1",
        "run_id": run_id,
        "capture_take_id": capture_take_id,
        "reference_view_id": reference_view_id,
        "secondary_view_id": None,
        "sync_quality": sync_quality,
        "court_frame_version": "canonical_court_frame.v1",
        "players": sorted({s["global_player_id"] for s in samples}),
        "samples": samples,
    }
