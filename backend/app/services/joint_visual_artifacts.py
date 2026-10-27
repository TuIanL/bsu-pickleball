"""joint_tracking_v2 结果链路的视觉层产物生成（2026-08-13 新增）。

joint 模式无 child 单摄产物可继承，前端视觉层（框架/热力图）依赖本模块从
joint run 自身产物聚合生成：

- `build_joint_tracking_overlay`: 从 debug trace（每 tick detections）聚合 tracking_overlay，
  对齐单摄 `TrackingOverlayArtifact` 契约（bbox / footpoint / player_id / timestamp）。
- `build_joint_position_visualizations`: 从 fused metric tracks 生成 heatmaps / scatter
  （复用 PositionVisualizer），供 VisualizationArtifactGallery 消费。
- `JOINT_POSE_UNAVAILABLE` / `JOINT_RENDER_TRAJECTORY_UNAVAILABLE`: 无法真实生成的
  产物（骨架 / 逐帧渲染轨迹）显式 unavailable + 结构化 reason，而非静默缺失。
"""

from __future__ import annotations

import json
import logging

from app.schemas.tracking import (
    DetectionOverlayFrame,
    FrameDetection,
    SourceFrameSize,
    TrackingOverlayArtifact,
)
from app.services.storage_service import StorageService
from app.vision.pickleball_game_analysis.position_visualizer import PositionVisualizer
from app.vision.pickleball_game_analysis.visualization_schemas import VisualizationConfig, VisualizationPoint

logger = logging.getLogger(__name__)

JOINT_POSE_UNAVAILABLE = "joint_tracking_v2 未接入 RTMPose 姿态推理，无法生成骨架产物"
JOINT_RENDER_TRAJECTORY_UNAVAILABLE = "joint 模式无逐帧图像坐标，渲染轨迹未生成"
JOINT_DETECTIONS_UNAVAILABLE = "joint 模式不产出逐帧检测 jsonl（检测框见 tracking overlay）"


def build_joint_tracking_overlay(
    *,
    job_id: str,
    video_id: str | None,
    debug_trace: dict[str, object] | None,
    frame_size: dict[str, int] | None,
    fps: float,
    frame_stride: int,
    reference_view_id: str,
) -> TrackingOverlayArtifact:
    """从 debug trace 聚合 reference view 的逐帧检测，构造 TrackingOverlayArtifact。

    每 tick 生成一条 DetectionOverlayFrame（frame_index = 该 tick 的 reference_frame_index，
    timestamp_seconds = canonical_timestamp_ms / 1000）。bbox 为源帧坐标。
    """
    width = max(1, int((frame_size or {}).get("width") or 0))
    height = max(1, int((frame_size or {}).get("height") or 0))
    frames: list[DetectionOverlayFrame] = []
    detection_count = 0

    ticks = debug_trace.get("ticks") if isinstance(debug_trace, dict) else None
    if isinstance(ticks, list):
        for tick in ticks:
            if not isinstance(tick, dict):
                continue
            views = tick.get("views")
            if not isinstance(views, dict):
                continue
            view = views.get(reference_view_id)
            if not isinstance(view, dict):
                continue
            detections = view.get("detections")
            if not isinstance(detections, list):
                continue
            frame_index = int(tick.get("reference_frame_index") or 0)
            timestamp_seconds = float(tick.get("canonical_timestamp_ms") or 0.0) / 1000.0
            frame_detections: list[FrameDetection] = []
            for det in detections:
                if not isinstance(det, dict):
                    continue
                bbox = det.get("bbox")
                if not isinstance(bbox, list) or len(bbox) != 4:
                    continue
                confidence = float(det.get("confidence") or 0.0)
                track_id = det.get("track_id")
                player_id = det.get("player_id")
                frame_detections.append(
                    FrameDetection(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        bbox=[float(v) for v in bbox],
                        confidence=confidence,
                        track_id=str(track_id) if track_id is not None else None,
                        player_id=str(player_id) if player_id is not None else None,
                        source_width=width,
                        source_height=height,
                    )
                )
            if frame_detections:
                frames.append(
                    DetectionOverlayFrame(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp_seconds,
                        detections=frame_detections,
                    )
                )
                detection_count += len(frame_detections)

    if detection_count:
        status = "available"
        detail = (
            f"已从 joint debug trace 聚合 {len(frames)} 帧、{detection_count} 个检测框"
            f"（GlobalPlayer 标签，来源 {reference_view_id}）"
        )
    else:
        status = "no_detections"
        detail = "joint debug trace 中无可用检测框；请检查 debugTraceEnabled 或模型输出"

    frame_count = 0
    for frame in frames:
        frame_count = max(frame_count, frame.frame_index + 1)
    return TrackingOverlayArtifact(
        job_id=job_id,
        video_id=video_id,
        status=status,
        detail=detail,
        source=SourceFrameSize(width=width, height=height),
        fps=max(0.0, fps),
        frame_count=frame_count,
        processed_frame_count=len(frames),
        frame_stride=max(1, frame_stride),
        timing_provenance={"source": "joint_debug_trace.v1", "reference_view_id": reference_view_id},
        frames=frames,
    )


def build_joint_position_visualizations(
    *,
    storage: StorageService,
    job_id: str,
    metric_tracks,
    language: str,
    roster_map: dict[str, str] | None = None,
    identity_slots: list[dict[str, object]] | None = None,
    frozen_roster_job: bool = False,
) -> dict[str, object]:
    """从 fused metric tracks 生成 heatmaps / scatter / structured data 产物并发布 Parent 命名空间。

    返回 artifacts 字段增量：heatmaps_manifest_json_path / heatmaps_url /
    scatter_plots_manifest_json_path / scatter_plots_url / structured_visualization_data_path /
    position_visualizations_status / detail。
    失败时返回 unavailable 状态（不抛错中断 compose）。
    """
    fields: dict[str, object] = {}
    try:
        from app.vision.pickleball_game_analysis.visualization_schemas import (
            VisualizationPoint,  # noqa: F401  # 已在顶部 import，避免遗漏
        )

        points = _metric_tracks_to_visualization_points(metric_tracks)
        if not points:
            from app.vision.pickleball_game_analysis.visualization_data_builder import (
                PositionVisualizationDataBuilder,
            )

            data_path = storage.structured_visualization_data_path(job_id)
            PositionVisualizationDataBuilder().build_and_write(
                output_path=data_path,
                player_points=[],
                ball_points=[],
                bounce_points=[],
            )
            payload = storage.read_json(data_path)
            payload["heatmaps"] = {
                "visual_grid": {"rows": 22, "cols": 10, "max_count": 0, "cells": []},
                "players": [],
                "identity_slots": _identity_slots_payload(identity_slots or []),
                "aggregate_source": (
                    "confirmed_frozen_roster_only" if frozen_roster_job
                    else "legacy_or_unfrozen_tracks"
                ),
            }
            storage.write_json_atomic(data_path, payload)
            fields["structured_visualization_data_path"] = str(data_path)
            fields["position_visualizations_status"] = "no_data"
            fields["position_visualizations_detail"] = (
                "没有已确认身份的有效球场坐标；匿名轨迹不会计入个人 P 热力图"
                if identity_slots else "fused 轨迹无有效球场坐标点"
            )
            return fields
        config = VisualizationConfig(language=language)
        heatmaps_url = f"/api/analysis/jobs/{job_id}/artifacts/position-heatmaps"
        scatter_url = f"/api/analysis/jobs/{job_id}/artifacts/position-scatter-plots"
        image_prefix = f"/api/analysis/jobs/{job_id}/artifacts/position-visualization-images"
        # 0) 生成与单摄同契约的 structured visualization data（前端 SVG 渲染，stabilize-joint-global-player-roster）
        structured_data = None
        try:
            from app.vision.pickleball_game_analysis.visualization_data_builder import (
                PositionVisualizationDataBuilder,
            )

            structured_data = PositionVisualizationDataBuilder().build_and_write(
                output_path=storage.structured_visualization_data_path(job_id),
                player_points=points,
                ball_points=[],
                bounce_points=[],
            )
            path = storage.structured_visualization_data_path(job_id)
            payload = storage.read_json(path)
            if isinstance(payload.get("heatmaps"), dict):
                payload["heatmaps"]["identity_slots"] = _identity_slots_payload(identity_slots or [])
                payload["heatmaps"]["aggregate_source"] = (
                    "confirmed_frozen_roster_only" if frozen_roster_job
                    else "legacy_or_unfrozen_tracks"
                )
                storage.write_json_atomic(path, payload)
            fields["structured_visualization_data_path"] = str(storage.structured_visualization_data_path(job_id))
        except Exception as exc:  # noqa: BLE001 - structured data 失败不中断 PNG 产物
            logger.warning("joint structured visualization data failed: %s", exc)
            fields["structured_visualization_data_path"] = None
        # 1) PNG（消费结构化数据避免重复计算 22×10 网格）
        heat_result, scatter_result = PositionVisualizer(config=config).generate(
            job_id=job_id,
            structured_data=structured_data,
            heatmaps_dir=storage.heatmaps_dir(job_id),
            scatter_plots_dir=storage.scatter_plots_dir(job_id),
            heatmaps_manifest_path=storage.heatmaps_manifest_json_path(job_id),
            scatter_manifest_path=storage.scatter_plots_manifest_json_path(job_id),
            image_url_prefix=image_prefix,
            heatmaps_artifact_url=heatmaps_url,
            scatter_artifact_url=scatter_url,
            player_points=points,
            ball_points=[],
            bounce_points=[],
        )
        fields["heatmaps_manifest_json_path"] = str(heat_result.path)
        fields["heatmaps_url"] = heatmaps_url
        fields["scatter_plots_manifest_json_path"] = str(scatter_result.path)
        fields["scatter_plots_url"] = scatter_url
        fields["position_visualizations_status"] = (
            "available"
            if any(result.status == "available" for result in [heat_result, scatter_result])
            else "no_data"
        )
        fields["position_visualizations_detail"] = f"{heat_result.detail}；{scatter_result.detail}"
    except Exception as exc:  # noqa: BLE001 - 可视化失败不中断 compose
        logger.warning("joint position visualizations failed: %s", exc)
        fields["position_visualizations_status"] = "unavailable"
        fields["position_visualizations_detail"] = f"位置可视化生成失败：{exc}"
    return fields


def _identity_slots_payload(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    slots: list[dict[str, object]] = []
    for entry in entries:
        player_id = str(entry.get("canonical_player_id") or "")
        if not player_id.startswith("Player_"):
            continue
        slots.append({
            "id": player_id,
            "label": f"P{player_id.rsplit('_', 1)[-1]}",
            "status": (
                str(entry.get("status"))
                if entry.get("status") in {"confirmed", "unconfirmed", "unavailable"}
                else "confirmed" if entry.get("confirmed") is True else "unconfirmed"
            ),
            "reason": entry.get("reason"),
            "canonical_end": entry.get("canonical_end"),
            "global_player_id": entry.get("global_player_id"),
            "tracklet_lineage_id": entry.get("tracklet_lineage_id"),
            "anchor_timestamp_ms": entry.get("anchor_timestamp_ms"),
            "observed_samples": int(entry.get("observed_samples") or 0),
        })
    return sorted(slots, key=lambda slot: slot["id"])


def build_joint_roster_artifact(
    *,
    storage: StorageService,
    job_id: str,
    roster: list[dict[str, object]],
    roster_map: dict[str, str],
    expected_player_count: int,
    status: str,
    confirmed_identity_only: bool = False,
    roster_hash: str | None = None,
    anchor_binding_audit: dict[str, object] | None = None,
) -> dict[str, object]:
    """写出 `global-player-roster.v1`（诊断 / 映射 contract，非用户展示 identity）。

    返回 artifacts 字段增量：roster_manifest_json_path / roster_url / roster_status / roster_detail。

    7.3：`anchor_binding_audit` 是身份确认的唯一权威来源。传入时`mapping_confirmed`
    只按审计结论求值，并把与 registry 快照的分歧记入 `mapping_conflict_with_registry`；
    未传入时保留历史行为（历史 Job 不可回填伪确认）。
    """
    audit_entries = {
        str(entry.get("canonical_player_id")): entry
        for entry in ((anchor_binding_audit or {}).get("entries") or [])
        if isinstance(entry, dict) and entry.get("canonical_player_id")
    }
    players: list[dict[str, object]] = []
    conflicts: dict[str, dict[str, object]] = {}
    for entry in roster:
        global_player_id = str(entry.get("global_player_id") or "")
        direct_player_id = entry.get("player_id")
        frozen_player_id = entry.get("frozen_player_id")
        frozen_confirmed = entry.get("frozen_identity_confirmed") is True
        player_id = (
            frozen_player_id if frozen_confirmed else None
        ) if confirmed_identity_only else (direct_player_id or roster_map.get(global_player_id))
        # ``roster_map`` deliberately provides a deterministic slot fallback
        # for display continuity.  That fallback must never be reused as proof
        # of a fused global identity by downstream factual metrics.
        direct_reference_binding = bool(
            global_player_id
            and isinstance(direct_player_id, str)
            and direct_player_id.startswith("Player_")
        )
        mapping_confirmed = bool(
            frozen_confirmed if confirmed_identity_only
            else direct_reference_binding and entry.get("status") == "confirmed"
        )
        if confirmed_identity_only and audit_entries and isinstance(frozen_player_id, str):
            audit_entry = audit_entries.get(frozen_player_id)
            if audit_entry is not None:
                audited = (
                    audit_entry.get("confirmed") is True
                    and audit_entry.get("formal_canonical_player_id") == frozen_player_id
                    and audit_entry.get("global_player_id") == global_player_id
                )
                if audited != mapping_confirmed:
                    conflicts[frozen_player_id] = {
                        "audit_confirmed": audited,
                        "registry_confirmed": mapping_confirmed,
                        "audit_reason": audit_entry.get("reason"),
                        "audit_global_player_id": audit_entry.get("global_player_id"),
                        "registry_global_player_id": global_player_id,
                    }
                mapping_confirmed = audited
        players.append(
            {
                "global_player_id": global_player_id,
                "player_id": player_id,
                "label": (
                    f"P{str(frozen_player_id).rsplit('_', 1)[-1]}"
                    if confirmed_identity_only and frozen_confirmed and isinstance(frozen_player_id, str)
                    else None if confirmed_identity_only else entry.get("label")
                ),
                "bindings": entry.get("bindings", {}),
                "mapping_method": (
                    "anchor_simultaneous_match" if confirmed_identity_only and mapping_confirmed
                    else "unconfirmed_anchor" if confirmed_identity_only
                    else "direct_reference_binding" if direct_reference_binding else "slot_fallback"
                ),
                "mapping_confirmed": mapping_confirmed,
                "frozen_player_id": frozen_player_id if mapping_confirmed else None,
                "frozen_identity_confirmed_from_ms": (
                    entry.get("frozen_identity_confirmed_from_ms") if mapping_confirmed else None
                ),
                "canonical_end": entry.get("canonical_end"),
                "identity_evidence": entry.get("frozen_identity_evidence") if mapping_confirmed else None,
            }
        )

    payload = {
        "schema_version": "global-player-roster.v1",
        "expected_player_count": expected_player_count,
        "roster_occupied_count": len(roster),
        "confirmed_player_count": (
            sum(player["mapping_confirmed"] is True for player in players)
            if confirmed_identity_only
            else sum(1 for r in roster if r.get("status") == "confirmed")
        ),
        "status": status,
        "roster_hash": roster_hash,
        "players": players,
        # 7.3：非空表示registry 快照与独立身份审计对同一槽位结论不一致。
        "mapping_conflict_with_audit": conflicts,
        "mapping_authority": "anchor_binding_audit" if audit_entries else "registry_snapshot",
    }
    path = storage.roster_manifest_json_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "roster_manifest_json_path": str(path),
        "roster_url": f"/api/analysis/jobs/{job_id}/artifacts/roster",
        "roster_status": "available",
        "roster_detail": f"已生成 {len(payload['players'])} 名 roster 玩家映射（diagnostic contract）",
    }


def _metric_tracks_to_visualization_points(metric_tracks) -> list[VisualizationPoint]:
    """ProjectedTrackPoint 列表 → VisualizationPoint（x/y 英尺坐标 + 时间戳）。"""
    points: list[VisualizationPoint] = []
    for track in metric_tracks:
        court = track.court_point
        if court is None:
            continue
        points.append(
            VisualizationPoint(
                x_ft=float(court.x),
                y_ft=float(court.y),
                frame_index=track.frame_index,
                timestamp_seconds=track.timestamp_seconds,
                label=track.track_id,
                source="fused",
            )
        )
    return points
