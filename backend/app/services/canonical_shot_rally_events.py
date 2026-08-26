"""从既有事实产物组合 canonical Rally/Shot 与 Metric Snapshot。

组合层只读消费 reconstructed trajectory、serve events、roster 和人工时间轴，
不重新运行击球检测、球员归属或最近邻猜测。没有可靠 rally 边界时保留 Shot，
但 rally_id/ordinal 保持为空，指标按 fail-closed 语义降级。
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from math import hypot
from pathlib import Path
from typing import Any

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.pipeline import AnalysisPipelineResult
from app.schemas.shot_rally_events import (
    PRODUCT_REFERENCE_V1,
    CanonicalPlayer,
    EvidenceWindow,
    MetricSnapshotArtifact,
    MetricSnapshotEntry,
    RallyEvent,
    ShotEvent,
    ShotQuality,
    ShotRallyDiagnostics,
    ShotRallyEventsArtifact,
    ShotSpatialSummary,
    ShotTrajectorySummary,
)
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)

_EVENT_SOURCE_ARTIFACT = "reconstructed-ball-trajectory"
_CALCULATION_VERSION = "product_reference_v1"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _timestamp_ms(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return int(round(number * 1000.0))


def _point(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None


def _path_distance_ft(samples: list[dict[str, Any]]) -> float | None:
    points = [_point(sample.get("court_xy")) for sample in samples]
    points = [point for point in points if point is not None]
    if len(points) < 2:
        return None
    return round(sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:], strict=False)), 3)


def _quality(segment: dict[str, Any]) -> ShotQuality:
    quality = segment.get("quality") if isinstance(segment.get("quality"), dict) else {}
    raw_score = quality.get("overall")
    try:
        score = max(0.0, min(1.0, float(raw_score))) if raw_score is not None else None
    except (TypeError, ValueError):
        score = None
    band = quality.get("display_level")
    if band not in {"high", "medium", "low", "none"}:
        band = "none"
    reasons: list[str] = []
    if segment.get("status") and segment.get("status") != "reconstructed":
        reasons.append(str(segment["status"]))
    if segment.get("boundary_reason"):
        reasons.append(str(segment["boundary_reason"]))
    return ShotQuality(score=score, band=band, reasons=sorted(set(reasons)))


def _canonical_players(payload: dict[str, Any]) -> list[CanonicalPlayer]:
    players: list[CanonicalPlayer] = []
    for raw in payload.get("player_roster") or []:
        if not isinstance(raw, dict):
            continue
        player_id = raw.get("player_id")
        if not isinstance(player_id, str) or not player_id.startswith("Player_"):
            continue
        try:
            players.append(
                CanonicalPlayer(
                    player_id=player_id,
                    render_slot=raw.get("render_slot"),
                    initial_side=(
                        raw.get("initial_side")
                        if raw.get("initial_side") in {"near", "far", "unknown"}
                        else "unknown"
                    ),
                )
            )
        except ValueError:
            continue
    return sorted(players, key=lambda player: player.player_id)


def _load_rally_boundaries(capture_take_id: str | None) -> tuple[list[dict[str, Any]], list[str]]:
    """读取人工/修正时间轴中的成对 rally_start/rally_end。

    没有关联 CaptureTake、数据库未初始化或边界不成对时，返回空结果并保留 warning。
    """

    if not capture_take_id:
        return [], ["没有 capture_take_id，未发现权威 rally 边界"]
    try:
        from app.database import get_session_factory
        from app.models.timeline_event import SessionTimelineEvent, TimelineEventType

        db = get_session_factory()()
        try:
            events = (
                db.query(SessionTimelineEvent)
                .filter(
                    SessionTimelineEvent.capture_take_id == capture_take_id,
                    SessionTimelineEvent.is_undone == False,  # noqa: E712
                    SessionTimelineEvent.event_type.in_([TimelineEventType.rally_start, TimelineEventType.rally_end]),
                )
                .order_by(SessionTimelineEvent.timestamp_ms.asc(), SessionTimelineEvent.created_at.asc())
                .all()
            )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 - timeline is an optional input
        return [], [f"读取 rally 时间轴失败：{exc}"]

    boundaries: list[dict[str, Any]] = []
    warnings: list[str] = []
    open_start: Any | None = None
    ordinal = 0
    for event in events:
        event_type = getattr(event.event_type, "value", event.event_type)
        if event_type == "rally_start":
            if open_start is not None:
                warnings.append(f"rally_start 重复，忽略事件 {event.id}")
                continue
            open_start = event
        elif event_type == "rally_end":
            if open_start is None:
                warnings.append(f"rally_end 无对应开始，忽略事件 {event.id}")
                continue
            if int(event.timestamp_ms) < int(open_start.timestamp_ms):
                warnings.append(f"rally_end 早于 rally_start，忽略事件 {event.id}")
                open_start = None
                continue
            ordinal += 1
            boundaries.append(
                {
                    "rally_id": f"rally-{ordinal:04d}",
                    "ordinal": ordinal,
                    "start_ms": int(open_start.timestamp_ms),
                    "end_ms": int(event.timestamp_ms),
                    "source": "manual_timeline",
                    "start_event_id": open_start.id,
                    "end_event_id": event.id,
                }
            )
            open_start = None
    if open_start is not None:
        warnings.append(f"rally_start {open_start.id} 缺少 rally_end，未生成开放回合")
    return boundaries, warnings


def _rally_for_timestamp(timestamp_ms: int | None, boundaries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if timestamp_ms is None:
        return None
    matches = [item for item in boundaries if item["start_ms"] <= timestamp_ms <= item["end_ms"]]
    return matches[0] if len(matches) == 1 else None


def _team_for_player(player_id: str | None, players: list[CanonicalPlayer], match_format: str) -> str | None:
    if match_format != "doubles" or player_id is None:
        return None
    player = next((item for item in players if item.player_id == player_id), None)
    if player is None or player.initial_side not in {"near", "far"}:
        return None
    return f"team_{player.initial_side}"


def _stage(ordinal: int | None, start_event_type: str | None) -> str | None:
    if start_event_type == "serve_reset":
        return "serve"
    return {1: "serve", 2: "return", 3: "third"}.get(ordinal, "rally_shot" if ordinal else None)


def _build_shot(
    shot_id: str,
    segments: list[dict[str, Any]],
    raw_events: dict[str, dict[str, Any]],
    boundaries: list[dict[str, Any]],
    players: list[CanonicalPlayer],
    match_format: str,
) -> ShotEvent:
    ordered = sorted(segments, key=lambda item: str(item.get("segment_id") or ""))
    first = ordered[0]
    all_samples = [
        sample
        for segment in ordered
        for sample in (segment.get("samples") or [])
        if isinstance(sample, dict)
    ]
    sample_times = [_timestamp_ms(sample.get("timestamp_sec")) for sample in all_samples]
    sample_times = [value for value in sample_times if value is not None]
    source_event_id = first.get("start_event_id")
    source_event = raw_events.get(str(source_event_id)) if source_event_id else None
    contact_ms = _timestamp_ms((source_event or {}).get("timestamp_sec"))
    start_ms = min(sample_times) if sample_times else contact_ms or 0
    end_ms = max(sample_times) if sample_times else contact_ms or start_ms

    owners = {(segment.get("hitter_player_id"), segment.get("ownership_status")) for segment in ordered}
    valid_owners = [item for item in owners if item[0] is not None]
    player_id: str | None = None
    ownership_status = str(first.get("ownership_status") or "unassigned")
    if len(valid_owners) == 1:
        player_id = valid_owners[0][0]
        ownership_status = valid_owners[0][1] or ownership_status
    elif len({item[0] for item in valid_owners}) > 1:
        ownership_status = "ambiguous"
    if ownership_status not in {"confirmed", "ambiguous", "unassigned", "not_applicable"}:
        ownership_status = "unassigned"
    if ownership_status != "confirmed":
        player_id = player_id if ownership_status == "ambiguous" and len(valid_owners) == 1 else None

    raw_confidences = [segment.get("ownership_confidence") for segment in ordered]
    confidences = []
    for value in raw_confidences:
        try:
            if value is not None:
                confidences.append(float(value))
        except (TypeError, ValueError):
            continue
    ownership_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None
    rally = _rally_for_timestamp(contact_ms or start_ms, boundaries)
    quality = _quality(first)
    trajectory = ShotTrajectorySummary(
        available=bool(all_samples),
        source=_EVENT_SOURCE_ARTIFACT if all_samples else None,
        segment_ids=sorted({str(segment.get("segment_id")) for segment in ordered if segment.get("segment_id")}),
        sample_count=len(all_samples),
        path_distance_ft=_path_distance_ft(all_samples),
    )
    court_points = [_point(sample.get("court_xy")) for sample in all_samples]
    court_points = [point for point in court_points if point is not None]
    spatial = (
        ShotSpatialSummary(coordinate_system="court_ft", start_xy=court_points[0], end_xy=court_points[-1])
        if court_points
        else None
    )
    window = EvidenceWindow(
        id=f"{shot_id}:window",
        start_ms=start_ms,
        end_ms=end_ms,
        source_artifact=_EVENT_SOURCE_ARTIFACT,
    )
    diagnostic: list[str] = []
    if len({item[0] for item in valid_owners}) > 1:
        diagnostic.append("segments contain conflicting hitter ownership")
    if not rally:
        diagnostic.append("no unique authoritative rally boundary")
    team_id = _team_for_player(player_id, players, match_format)
    return ShotEvent(
        shot_id=shot_id,
        rally_id=rally["rally_id"] if rally else None,
        start_ms=start_ms,
        end_ms=end_ms,
        contact_ms=contact_ms,
        hitter_player_id=player_id,
        team_id=team_id,
        ownership_status=ownership_status,
        ownership_confidence=ownership_confidence,
        ownership_source="ball_hit_player_attributor" if ownership_status != "not_applicable" else None,
        stage=None,
        quality=quality,
        trajectory=trajectory,
        spatial=spatial,
        evidence_windows=[window],
        source_event_id=str(source_event_id) if source_event_id else None,
        source_artifacts=[_EVENT_SOURCE_ARTIFACT],
        provenance={
            "event_authority": "reconstructed_ball_trajectory.v2",
            "shot_assembly": "BallShotAssembler",
            "ownership_authority": "BallHitPlayerAttributor",
        },
        diagnostics=diagnostic,
    )


def build_shot_rally_events(
    *,
    job_id: str,
    video_id: str | None,
    match_format: str,
    reconstructed_payload: dict[str, Any] | None,
    serve_payload: dict[str, Any] | None = None,
    capture_take_id: str | None = None,
    generated_at: str | None = None,
) -> ShotRallyEventsArtifact:
    generated_at = generated_at or datetime.now(UTC).isoformat()
    if reconstructed_payload is None:
        return ShotRallyEventsArtifact(
            job_id=job_id,
            video_id=video_id,
            status="unavailable",
            detail="缺少 reconstructed_ball_trajectory.v2，无法确认 Shot 事件",
            generated_at=generated_at,
            diagnostics=ShotRallyDiagnostics(warnings=["reconstructed-ball-trajectory artifact missing"]),
            source_artifacts=["reconstructed-ball-trajectory"],
        )
    source_status = reconstructed_payload.get("status")
    if source_status == "failed":
        return ShotRallyEventsArtifact(
            job_id=job_id,
            video_id=video_id,
            status="failed",
            detail=str(reconstructed_payload.get("detail") or "reconstructed trajectory failed"),
            generated_at=generated_at,
            diagnostics=ShotRallyDiagnostics(warnings=["reconstructed-ball-trajectory status=failed"]),
            source_artifacts=["reconstructed-ball-trajectory"],
        )

    players = _canonical_players(reconstructed_payload)
    boundaries, warnings = _load_rally_boundaries(capture_take_id)
    raw_events = {
        str(item.get("event_id")): item
        for item in (reconstructed_payload.get("events") or [])
        if isinstance(item, dict) and item.get("event_id")
    }
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing_segment_ids: list[str] = []
    for segment in reconstructed_payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        shot_id = segment.get("shot_id")
        if not shot_id:
            missing_segment_ids.append(str(segment.get("segment_id") or "unknown-segment"))
            continue
        grouped[str(shot_id)].append(segment)

    shots = [
        _build_shot(shot_id, segments, raw_events, boundaries, players, match_format)
        for shot_id, segments in sorted(grouped.items())
    ]
    shots.sort(key=lambda shot: (shot.start_ms, shot.shot_id))
    duplicate_ids = sorted(shot_id for shot_id, segments in grouped.items() if len(segments) > 1)

    # 只在唯一的 authoritative rally 窗口内赋 ordinal；不会用全局数组下标重编号。
    shots_by_rally: dict[str, list[ShotEvent]] = defaultdict(list)
    for shot in shots:
        if shot.rally_id:
            shots_by_rally[shot.rally_id].append(shot)
    updated_shots: list[ShotEvent] = []
    for shot in shots:
        if shot.rally_id is None:
            updated_shots.append(shot)
            continue
        ordered = sorted(
            shots_by_rally[shot.rally_id],
            key=lambda item: (item.contact_ms or item.start_ms, item.shot_id),
        )
        ordinal = next(index for index, item in enumerate(ordered, start=1) if item.shot_id == shot.shot_id)
        start_event_type = raw_events.get(shot.source_event_id or "", {}).get("event_type")
        stage = _stage(ordinal, start_event_type)
        updated_shots.append(shot.model_copy(update={"ordinal_in_rally": ordinal, "stage": stage, "shot_type": stage}))
    shots = sorted(updated_shots, key=lambda shot: (shot.start_ms, shot.shot_id))

    rally_events: list[RallyEvent] = []
    for boundary in boundaries:
        shot_ids = [shot.shot_id for shot in shots if shot.rally_id == boundary["rally_id"]]
        rally_events.append(
            RallyEvent(
                rally_id=boundary["rally_id"],
                ordinal=boundary["ordinal"],
                start_ms=boundary["start_ms"],
                end_ms=boundary["end_ms"],
                shot_ids=shot_ids,
                source_artifacts=["timeline-events"],
                provenance="manual_timeline",
                evidence_windows=[
                    EvidenceWindow(
                        id=f"{boundary['rally_id']}:window",
                        start_ms=boundary["start_ms"],
                        end_ms=boundary["end_ms"],
                        source_artifact="timeline-events",
                    )
                ],
            )
        )

    if boundaries:
        warnings.append(f"已使用 {len(boundaries)} 个成对 rally 时间窗")
    if not boundaries:
        warnings.append("没有唯一 authoritative rally 边界，Shot ordinal 保持 null")
    if serve_payload and serve_payload.get("status") in {"available", "partial"}:
        source_artifacts = [_EVENT_SOURCE_ARTIFACT, "serve-events"]
    else:
        source_artifacts = [_EVENT_SOURCE_ARTIFACT]
    diagnostics = ShotRallyDiagnostics(
        duplicate_shot_ids=duplicate_ids,
        missing_shot_ids=sorted(missing_segment_ids),
        unassigned_shot_count=sum(1 for shot in shots if shot.ownership_status == "unassigned"),
        ambiguous_shot_count=sum(1 for shot in shots if shot.ownership_status == "ambiguous"),
        rally_boundary_status="available" if boundaries else "unavailable",
        warnings=sorted(set(warnings)),
    )
    detail = (
        f"已组合 {len(rally_events)} 个 Rally、{len(shots)} 个去重 Shot；"
        f"未归属 {diagnostics.unassigned_shot_count} 个、含糊 {diagnostics.ambiguous_shot_count} 个"
    )
    return ShotRallyEventsArtifact(
        job_id=job_id,
        video_id=video_id,
        status="available" if source_status in {"available", "no_candidates"} else "unavailable",
        detail=(
            detail
            if source_status in {"available", "no_candidates"}
            else str(reconstructed_payload.get("detail") or "事件源不可用")
        ),
        generated_at=generated_at,
        players=players,
        rallies=rally_events,
        shots=shots,
        diagnostics=diagnostics,
        source_artifacts=source_artifacts,
        provenance={
            "shot_authority": "reconstructed_ball_trajectory.v2",
            "rally_authority": "manual_timeline" if boundaries else "unavailable",
            "time_conversion": "timestamp_sec_to_ms_once_at_composition_boundary",
        },
    )


def _metric_id(scope: str, subject_id: str, metric_key: str) -> str:
    return f"{scope}:{subject_id}:{metric_key}"


def _metric(
    *,
    metric_key: str,
    scope: str,
    subject_id: str,
    value: float | int | None,
    unit: str,
    numerator: float | int | None,
    denominator: float | int | None,
    sample_count: int,
    status: str,
    reason: str | None,
    evidence_ids: list[str],
    confidence: float | None = None,
) -> MetricSnapshotEntry:
    return MetricSnapshotEntry(
        metric_id=_metric_id(scope, subject_id, metric_key),
        metric_key=metric_key,
        scope=scope,
        subject_id=subject_id,
        value=value,
        unit=unit,
        numerator=numerator,
        denominator=denominator,
        sample_count=sample_count,
        status=status,
        reason=reason,
        confidence=confidence,
        provenance="canonical_shot_rally_events",
        evidence_ids=sorted(set(evidence_ids)) or ["shot-rally-events.v1"],
        calculation_version=_CALCULATION_VERSION,
    )


def _count_metric(
    metric_key: str,
    scope: str,
    subject_id: str,
    shot_ids: list[str],
    *,
    require_sample: int = 1,
    reason_if_insufficient: str = "样本不足，无法形成稳定统计",
) -> MetricSnapshotEntry:
    count = len(shot_ids)
    sufficient = count >= require_sample
    return _metric(
        metric_key=metric_key,
        scope=scope,
        subject_id=subject_id,
        value=count if sufficient else None,
        unit="count",
        numerator=count,
        denominator=count,
        sample_count=count,
        status="available" if sufficient else "insufficient_evidence",
        reason=None if sufficient else reason_if_insufficient,
        evidence_ids=shot_ids,
    )


def build_metric_snapshot(
    events: ShotRallyEventsArtifact,
    *,
    match_format: str,
    generated_at: str | None = None,
) -> MetricSnapshotArtifact:
    generated_at = generated_at or datetime.now(UTC).isoformat()
    if events.status not in {"available"}:
        return MetricSnapshotArtifact(
            job_id=events.job_id,
            video_id=events.video_id,
            status=events.status,
            detail=f"事件产物不可用，未生成可审计指标：{events.detail}",
            generated_at=generated_at,
        )

    shots = list(events.shots)
    metrics: list[MetricSnapshotEntry] = []
    all_ids = [shot.shot_id for shot in shots]
    rally_ids = sorted({rally.rally_id for rally in events.rallies})
    metrics.append(
        _count_metric(
            "shot_count",
            "match",
            "match",
            all_ids,
            require_sample=1,
            reason_if_insufficient="当前没有可确认的 Shot 事件",
        )
    )
    metrics.append(
        _metric(
            metric_key="rally_count",
            scope="match",
            subject_id="match",
            value=len(rally_ids) if rally_ids else None,
            unit="count",
            numerator=len(rally_ids),
            denominator=len(rally_ids),
            sample_count=len(rally_ids),
            status="available" if rally_ids else "insufficient_evidence",
            reason=None if rally_ids else "没有唯一 authoritative rally 边界",
            evidence_ids=rally_ids,
        )
    )

    def stage_ids(stage: str) -> list[str]:
        return [shot.shot_id for shot in shots if shot.stage == stage]

    for key, stage in (("serve_count", "serve"), ("return_count", "return"), ("third_shot_count", "third")):
        ids = stage_ids(stage)
        metrics.append(
            _count_metric(
                key,
                "match",
                "match",
                ids,
                require_sample=1,
                reason_if_insufficient="没有可靠的回合拍序或该阶段样本不足",
            )
        )

    quality_shots = [shot for shot in shots if shot.quality.score is not None]
    quality_ids = [shot.shot_id for shot in quality_shots]
    quality_value = (
        round(sum(float(shot.quality.score or 0.0) for shot in quality_shots) / len(quality_shots), 4)
        if len(quality_shots) >= PRODUCT_REFERENCE_V1["min_quality_samples"]
        else None
    )
    metrics.append(
        _metric(
            metric_key="shot_quality_mean",
            scope="match",
            subject_id="match",
            value=quality_value,
            unit="ratio",
            numerator=len(quality_shots),
            denominator=len(quality_shots),
            sample_count=len(quality_shots),
            status="available" if quality_value is not None else "insufficient_evidence",
            reason=None if quality_value is not None else "轨迹质量样本低于 product_reference_v1 阈值",
            evidence_ids=quality_ids,
        )
    )

    player_ids = sorted({shot.hitter_player_id for shot in shots if shot.hitter_player_id})
    for player_id in player_ids:
        player_shots = [
            shot
            for shot in shots
            if shot.hitter_player_id == player_id and shot.ownership_status == "confirmed"
        ]
        ids = [shot.shot_id for shot in player_shots]
        metrics.append(_count_metric("shot_count", "player", player_id, ids))
        for key, stage in (("serve_count", "serve"), ("return_count", "return"), ("third_shot_count", "third")):
            stage_shots = [shot for shot in player_shots if shot.stage == stage]
            metrics.append(
                _count_metric(
                    key,
                    "player",
                    player_id,
                    [shot.shot_id for shot in stage_shots],
                    reason_if_insufficient="没有可靠的回合拍序或该球员该阶段样本不足",
                )
            )
        player_quality = [shot for shot in player_shots if shot.quality.score is not None]
        player_quality_ids = [shot.shot_id for shot in player_quality]
        player_quality_value = (
            round(sum(float(shot.quality.score or 0.0) for shot in player_quality) / len(player_quality), 4)
            if len(player_quality) >= PRODUCT_REFERENCE_V1["min_quality_samples"]
            else None
        )
        metrics.append(
            _metric(
                metric_key="shot_quality_mean",
                scope="player",
                subject_id=player_id,
                value=player_quality_value,
                unit="ratio",
                numerator=len(player_quality),
                denominator=len(player_quality),
                sample_count=len(player_quality),
                status="available" if player_quality_value is not None else "insufficient_evidence",
                reason=None if player_quality_value is not None else "该球员轨迹质量样本低于 product_reference_v1 阈值",
                evidence_ids=player_quality_ids,
            )
        )

    team_ids = sorted({shot.team_id for shot in shots if shot.team_id})
    for team_id in team_ids:
        team_shots = [shot for shot in shots if shot.team_id == team_id and shot.ownership_status == "confirmed"]
        metrics.append(_count_metric("shot_count", "team", team_id, [shot.shot_id for shot in team_shots]))

    if match_format == "singles":
        metrics.append(
            _metric(
                metric_key="doubles_cooperation",
                scope="match",
                subject_id="match",
                value=None,
                unit="ratio",
                numerator=None,
                denominator=None,
                sample_count=0,
                status="not_applicable",
                reason="单打比赛不适用双打协同指标",
                evidence_ids=["shot-rally-events.v1"],
            )
        )
    elif not team_ids:
        metrics.append(
            _metric(
                metric_key="doubles_cooperation",
                scope="match",
                subject_id="match",
                value=None,
                unit="ratio",
                numerator=None,
                denominator=None,
                sample_count=0,
                status="unavailable",
                reason="缺少可靠的 canonical 球员半场信息",
                evidence_ids=["shot-rally-events.v1"],
            )
        )

    return MetricSnapshotArtifact(
        job_id=events.job_id,
        video_id=events.video_id,
        status="available",
        detail=f"已生成 {len(metrics)} 条分母感知描述性指标；不包含技能评分",
        generated_at=generated_at,
        metrics=metrics,
    )


def _artifact_updates(
    result: AnalysisPipelineResult,
    storage: StorageService,
    *,
    events_status: str,
    events_detail: str,
    metrics_status: str,
    metrics_detail: str,
) -> AnalysisPipelineResult:
    events_path = storage.shot_rally_events_json_path(result.job_id)
    metrics_path = storage.metric_snapshot_json_path(result.job_id)
    artifacts = result.artifacts.model_copy(
        update={
            "shot_rally_events_json_path": str(events_path) if events_path.exists() else None,
            "shot_rally_events_url": (
                f"/api/analysis/jobs/{result.job_id}/artifacts/shot-rally-events"
                if events_path.exists()
                else None
            ),
            "shot_rally_events_status": events_status,
            "shot_rally_events_detail": events_detail,
            "metric_snapshot_json_path": str(metrics_path) if metrics_path.exists() else None,
            "metric_snapshot_url": (
                f"/api/analysis/jobs/{result.job_id}/artifacts/metric-snapshot"
                if metrics_path.exists()
                else None
            ),
            "metric_snapshot_status": metrics_status,
            "metric_snapshot_detail": metrics_detail,
        }
    )
    return result.model_copy(update={"artifacts": artifacts})


def generate_and_persist_canonical_events(
    job: AnalysisJobSummary,
    result: AnalysisPipelineResult,
    *,
    storage: StorageService | None = None,
) -> tuple[AnalysisPipelineResult, ShotRallyEventsArtifact, MetricSnapshotArtifact]:
    """为真实完成 job 生成并持久化 canonical artifacts。

    组合失败只会让两个可选 artifact 进入 failed/unavailable，不阻断主视觉结果。
    """

    storage = storage or StorageService()
    storage.resolve_capture_job_root(job.id, job.metadata.capture_take_id)
    generated_at = datetime.now(UTC).isoformat()
    reconstructed = _read_json(storage.reconstructed_ball_trajectory_json_path(job.id))
    serve = _read_json(storage.serve_events_json_path(job.id))
    try:
        events = build_shot_rally_events(
            job_id=job.id,
            video_id=result.video_id,
            match_format=job.metadata.matchFormat,
            reconstructed_payload=reconstructed,
            serve_payload=serve,
            capture_take_id=job.metadata.capture_take_id,
            generated_at=generated_at,
        )
        snapshot = build_metric_snapshot(events, match_format=job.metadata.matchFormat, generated_at=generated_at)
        storage.write_json(storage.shot_rally_events_json_path(job.id), events.model_dump(mode="json"))
        storage.write_json(storage.metric_snapshot_json_path(job.id), snapshot.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 - optional post-processing must not fail the pipeline
        logger.exception("canonical shot/rally artifact generation failed for %s", job.id)
        events = ShotRallyEventsArtifact(
            job_id=job.id,
            video_id=result.video_id,
            status="failed",
            detail=f"canonical Rally/Shot 组合失败：{exc}",
            generated_at=generated_at,
            diagnostics=ShotRallyDiagnostics(warnings=["composer_exception"]),
        )
        snapshot = MetricSnapshotArtifact(
            job_id=job.id,
            video_id=result.video_id,
            status="failed",
            detail=f"Metric Snapshot 组合失败：{exc}",
            generated_at=generated_at,
        )
        try:
            storage.write_json(storage.shot_rally_events_json_path(job.id), events.model_dump(mode="json"))
            storage.write_json(storage.metric_snapshot_json_path(job.id), snapshot.model_dump(mode="json"))
        except Exception:
            logger.exception("failed to persist canonical artifact failure state for %s", job.id)

    # CaptureTake 任务的公开 result 继续只暴露 logical reference，不泄漏本地绝对路径。
    updated = storage.publicize_pipeline_result(
        _artifact_updates(
            result,
            storage,
            events_status=events.status,
            events_detail=events.detail,
            metrics_status=snapshot.status,
            metrics_detail=snapshot.detail,
        )
    )
    storage.write_json(storage.output_json_path(job.id), updated.model_dump(mode="json"))
    return updated, events, snapshot
