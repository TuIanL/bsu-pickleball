"""事件切分球轨迹重建编排器（reconstruction_engine）。

把图像拟合、击球候选检测、事件仲裁、球员归属、Shot 组装、锚定 2.5D 重建与
质量评估串成一条完整链路，输出 `reconstructed_ball_trajectory.v2` 的 payload。

处理链（设计 D1）：
  cleaned trajectory + bounce events + (可选) serve events + homography + player context
    → BallContactEventDetector（纯球侧突变候选）
    → BallEventResolver.prefilter（弹地抑制唯一权威，非对称时间窗口）
    → BallHitPlayerAttributor（球员归属；serve 直接播种）
    → BallEventResolver.finalize（确认 / ambiguous / rejected → 正式事件）
    → BallFlightSegmenter（切段）
    → BallShotAssembler（shot_id 与归属传播）
    → ShotSequenceValidator（半场交替序列校验）
    → ImageSpaceTrajectoryFitter + EventAnchoredTrajectoryReconstructor（重建）
    → TrajectoryQualityEvaluator（质量）
    → payload
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.vision.courtvision_calibration_engine.court_geometry import PickleballCourtGeometry, standard_court
from app.vision.pickleball_game_analysis.ball_contact_event_detector import BallContactEventDetector
from app.vision.pickleball_game_analysis.ball_event_resolver import BallEventResolver
from app.vision.pickleball_game_analysis.ball_flight_segmenter import BallFlightSegmenter
from app.vision.pickleball_game_analysis.ball_hit_player_attributor import BallHitPlayerAttributor
from app.vision.pickleball_game_analysis.ball_shot_assembler import (
    BallShotAssembler,
    ShotSequenceValidator,
)
from app.vision.pickleball_game_analysis.event_anchored_trajectory_reconstructor import (
    EventAnchoredTrajectoryReconstructor,
)
from app.vision.pickleball_game_analysis.image_space_trajectory_fitter import ImageSpaceTrajectoryFitter
from app.vision.pickleball_game_analysis.player_attribution_context import PlayerAttributionContext
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    OwnershipStatus,
    ReconstructedSample,
    ReconstructionConfig,
    TrajectoryEvent,
    TrajectoryEventType,
    event_to_payload,
)
from app.vision.pickleball_game_analysis.schemas import BounceEvent, TrajectoryPoint
from app.vision.pickleball_game_analysis.trajectory_quality_evaluator import TrajectoryQualityEvaluator

# 重建产物固定标识（v2：增加球员归属与 Shot 信息）
RECONSTRUCTED_SCHEMA_VERSION = "reconstructed_ball_trajectory.v2"
RECONSTRUCTION_MODE = "event_anchored_2_5d"


def _serve_reset_events(serve_events: list[Any] | None, confidence_threshold: float) -> list[TrajectoryEvent]:
    """把高可信 serve 事件转换为 serve_reset 边界事件（可选增强）。

    保留 serve 事件的 `player_id` 供 Shot 播种（不变量 I9：只允许 canonical）。
    """
    if not serve_events:
        return []
    resets: list[TrajectoryEvent] = []
    for index, serve in enumerate(serve_events):
        frame = _get(serve, "frame_index", "frame")
        timestamp = _get(serve, "timestamp_seconds", "timestamp_sec", "timestamp")
        confidence = _get(serve, "confidence")
        if frame is None or confidence is None:
            continue
        if float(confidence) < confidence_threshold:
            continue
        player_id = _get(serve, "player_id", "player")
        if player_id is not None and not str(player_id).startswith("Player_"):
            player_id = None
        resets.append(
            TrajectoryEvent(
                event_id=f"serve-{index + 1}",
                event_type=TrajectoryEventType.SERVE_RESET,
                frame_index=int(frame),
                timestamp_sec=float(timestamp if timestamp is not None else 0.0),
                confidence=float(confidence),
                source="serve",
                hitter_player_id=str(player_id) if player_id is not None else None,
                ownership_status=(
                    OwnershipStatus.CONFIRMED.value if player_id is not None else OwnershipStatus.UNASSIGNED.value
                ),
                ownership_confidence=float(confidence) if player_id is not None else None,
            )
        )
    return resets


def _get(obj: Any, *names: str) -> Any:
    """从对象或字典中按多个候选字段名取值。"""
    if isinstance(obj, dict):
        for name in names:
            if name in obj:
                return obj[name]
        return None
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _sample_to_payload(sample: ReconstructedSample) -> dict:
    return {
        "frame_index": int(sample.frame_index),
        "timestamp_sec": round(float(sample.timestamp_sec), 6),
        "court_xy": [round(sample.court_xy[0], 4), round(sample.court_xy[1], 4)] if sample.court_xy else None,
        "estimated_height_ft": sample.estimated_height_ft,
        "source": sample.source,
        "confidence": sample.confidence,
        "height_source": sample.height_source,
        "height_confidence": sample.height_confidence,
        "height_uncertainty_ft": sample.height_uncertainty_ft,
        "gap_length_frames": sample.gap_length_frames,
        "reprojection_error_px": sample.reprojection_error_px,
    }


def reconstruct_ball_trajectory(
    *,
    job_id: str,
    cleaned_points: list[TrajectoryPoint],
    bounce_events: list[BounceEvent],
    serve_events: list[Any] | None = None,
    homography: list[list[float]] | None = None,
    fps: float = 30.0,
    config: ReconstructionConfig | None = None,
    court: PickleballCourtGeometry | None = None,
    player_context: PlayerAttributionContext | None = None,
) -> dict:
    """运行完整重建链，返回重建产物 payload（第三套数据，不覆盖 raw/cleaned）。

    player_context 为 None 时（旧路径 / 无球员证据）仍完成事件切段与重建，
    归属字段保持 unassigned/not_applicable，不伪造归属（I4 / I6）。
    """
    cfg = config or ReconstructionConfig()
    court_geom = court or standard_court()

    if not cleaned_points:
        return {
            "schema_version": RECONSTRUCTED_SCHEMA_VERSION,
            "job_id": job_id,
            "status": "no_candidates",
            "detail": "没有可重建的清洗轨迹",
            "reconstruction_mode": RECONSTRUCTION_MODE,
            "coordinate_semantics": _coordinate_semantics(),
            "player_roster": _player_roster_payload(player_context),
            "suppression_snapshot": {},
            "events": [],
            "segments": [],
        }

    try:
        # 1) 击球候选检测（纯球侧，不读取 bounce_events，不变量 I7）
        detector = BallContactEventDetector()
        candidates = detector.detect(cleaned_points, fps=fps)

        # 2) prefilter：弹地抑制唯一权威（非对称时间窗口，I8）
        resolver = BallEventResolver()
        prefiltered = resolver.prefilter(candidates, bounce_events, fps=fps)

        # 3) 球员归属（serve 事件直接播种）
        attributions: dict[str, Any] = {}
        if player_context is not None:
            attributor = BallHitPlayerAttributor()
            attributions = attributor.attribute(prefiltered, player_context)

        # 4) finalize：生成正式事件列表（suppressed/rejected 只进 diagnostics，I1）
        events = resolver.finalize(prefiltered, bounce_events, attributions=attributions)
        events.extend(_serve_reset_events(serve_events, cfg.serve_confidence_threshold))
        events.sort(key=lambda e: (e.frame_index, e.timestamp_sec))

        # 5) 飞行段切分
        segmenter = BallFlightSegmenter(cfg)
        segments = segmenter.segment(cleaned_points, events)
        events_by_id = {event.event_id: event for event in events}

        # 6) Shot 组装 + 半场交替序列校验
        assembler = BallShotAssembler()
        shots = assembler.assemble(segments, events_by_id)
        if player_context is not None:
            validator = ShotSequenceValidator()
            downgraded = validator.validate(shots, segments, player_context)
            events_by_id, events = _apply_downgrade(downgraded, events_by_id, events)

        # 7) 重建 + 质量评估
        fitter = ImageSpaceTrajectoryFitter()
        reconstructor = EventAnchoredTrajectoryReconstructor(cfg, court_geom)
        evaluator = TrajectoryQualityEvaluator(court=court_geom)

        segment_payloads: list[dict] = []
        for segment in segments:
            seg_points = [cleaned_points[i] for i in segment.point_indices]
            fit = fitter.fit(seg_points)
            reconstructed = reconstructor.reconstruct(segment, cleaned_points, events_by_id, homography)
            reconstructed.quality = evaluator.evaluate(reconstructed, fit, events_by_id)
            segment_payloads.append(_segment_to_payload(reconstructed, segment))

        status = "available" if segment_payloads else "no_candidates"
        detail = (
            f"重建 {len(segment_payloads)} 个飞行段（事件锚定 2.5D，仅可视化）"
            if segment_payloads
            else "重建运行完成，但没有足够的飞行段"
        )
        return {
            "schema_version": RECONSTRUCTED_SCHEMA_VERSION,
            "job_id": job_id,
            "status": status,
            "detail": detail,
            "reconstruction_mode": RECONSTRUCTION_MODE,
            "coordinate_semantics": _coordinate_semantics(),
            "player_roster": _player_roster_payload(player_context),
            "suppression_snapshot": resolver.suppression_config_snapshot(fps, frame_stride=1),
            "events": [event_to_payload(event) for event in events],
            "segments": segment_payloads,
        }
    except Exception as exc:  # 重建失败不阻断整个任务，降级为 failed 产物
        return {
            "schema_version": RECONSTRUCTED_SCHEMA_VERSION,
            "job_id": job_id,
            "status": "failed",
            "detail": f"球轨迹重建失败：{exc}",
            "reconstruction_mode": RECONSTRUCTION_MODE,
            "coordinate_semantics": _coordinate_semantics(),
            "player_roster": _player_roster_payload(player_context),
            "suppression_snapshot": {},
            "events": [],
            "segments": [],
        }


def _apply_downgrade(
    downgraded: list[Any],
    events_by_id: dict[str, TrajectoryEvent],
    events: list[TrajectoryEvent],
) -> tuple[dict[str, TrajectoryEvent], list[TrajectoryEvent]]:
    """降级 Shot 的开启事件：hitter 置空、ownership 降为 ambiguous（与段一致）。"""
    if not downgraded:
        return events_by_id, events
    source_ids = {shot.source_event_id for shot in downgraded}
    updated: dict[str, TrajectoryEvent] = dict(events_by_id)
    for event_id, event_obj in events_by_id.items():
        if event_id not in source_ids or event_obj.event_type != TrajectoryEventType.HIT:
            continue
        updated[event_id] = replace(
            event_obj,
            hitter_player_id=None,
            hitter_render_slot=None,
            ownership_status=OwnershipStatus.AMBIGUOUS.value,
        )
    return updated, [updated.get(e.event_id, e) for e in events]


def _player_roster_payload(player_context: PlayerAttributionContext | None) -> list[dict]:
    """产物顶层的球员名单（来自归属上下文的 roster）。"""
    if player_context is None:
        return []
    roster: list[dict] = []
    for player_id in player_context.player_ids:
        entry = player_context.roster.get(player_id)
        roster.append(
            {
                "player_id": player_id,
                "render_slot": entry.render_slot if entry else None,
                "initial_side": entry.initial_side if entry else None,
            }
        )
    return roster


def _coordinate_semantics() -> dict:
    return {
        "xy": "court_ft_visual_estimate",
        "z": "estimated_height_ft",
        "metric_validity": "visualization_only",
    }


def _segment_to_payload(segment, source: Any) -> dict:
    return {
        "segment_id": segment.segment_id,
        "reconstruction_mode": segment.reconstruction_mode,
        "status": segment.status,
        "start_event_id": segment.start_event_id,
        "end_event_id": segment.end_event_id,
        "start_event_type": segment.start_event_type,
        "end_event_type": segment.end_event_type,
        "boundary_reason": segment.boundary_reason,
        "fit_space": segment.fit_space,
        "model": segment.model,
        "anchors": segment.anchors,
        "quality": segment.quality,
        "shot_id": source.shot_id,
        "hitter_player_id": source.hitter_player_id,
        "hitter_render_slot": source.hitter_render_slot,
        "ownership_status": source.ownership_status,
        "ownership_confidence": (
            round(float(source.ownership_confidence), 3) if source.ownership_confidence is not None else None
        ),
        "ownership_source_event_id": source.ownership_source_event_id,
        "samples": [_sample_to_payload(sample) for sample in segment.samples],
    }
