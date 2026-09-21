"""分析名册确认与分析回合上下文：bootstrap、冻结、合成、绑定与身份连续性审计。

分工：

- `build_player_bootstrap()` —— 受限 player bootstrap。**不启动完整 Pipeline**，
  优先消费该 owner 已有分析产物里的 roster / 轨迹 / 质量诊断；首次分析在模型
  显式开启且源视频可读时，仅对开头稀疏帧做轻量人体候选预检。
- `freeze_roster_snapshot()` —— Job 创建时冻结名册；冻结后不再受可编辑来源名册影响。
- `compose_rally_context()` —— 由 scoring snapshot + Job roster + court-end projection
  合成不可变 `AnalysisRallyContextSnapshot`，并给出 context-set hash。
- `bind_formal_window()` —— formal window 与回合上下文的优先级绑定。
- `build_bootstrap_binding_audit()` —— bootstrap anchor → 正式 canonical Player 的可审计绑定。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from math import hypot
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4
from urllib.parse import quote

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment
from app.models.rally_context import AnalysisRallyContextSet, AnalysisRosterSnapshot
from app.schemas.rally_context import (
    REASON_AMBIGUOUS_TEMPORAL_MATCH,
    REASON_BOOTSTRAP_BINDING_FAILED,
    REASON_BOOTSTRAP_BINDING_PARTIAL,
    REASON_NO_CAPTURE_TAKE,
    REASON_NO_SCORING_SNAPSHOTS,
    REASON_NO_TEMPORAL_CANDIDATE,
    REASON_ROSTER_INSUFFICIENT_CANDIDATES,
    REASON_ROSTER_NOT_CONFIRMED,
    REASON_ROSTER_SKIPPED_BY_USER,
    AnalysisRallyContextRally,
    AnalysisRallyContextSnapshotPayload,
    AnalysisRosterConfirmationEntry,
    AnalysisRosterSnapshotPayload,
    BootstrapBindingAuditEntry,
    BootstrapBindingAuditPayload,
    ContextBinding,
    PlayerBootstrapCandidate,
    PlayerBootstrapQualityDiagnostic,
    PlayerBootstrapResult,
    RosterConfirmationRequest,
)
from app.services import court_end_projection_service as court_end_svc
from app.services import rally_scoring_service as scoring_svc

_ID_PREFIX_ROSTER = "ars"
_ID_PREFIX_CONTEXT = "arc"

# 唯一时间降级的容差：超过该距离不再认为候选可以匹配。
DEFAULT_TEMPORAL_TOLERANCE_MS = 3000

CANONICAL_SLOTS = ("Player_1", "Player_2", "Player_3", "Player_4")

DIAG_BOOTSTRAP_NO_SOURCE_JOB = "bootstrap_no_source_job"
DIAG_BOOTSTRAP_NO_ARTIFACT = "bootstrap_artifact_unavailable"
DIAG_BOOTSTRAP_INSUFFICIENT = "bootstrap_insufficient_candidates"
DIAG_ANCHOR_EVIDENCE_UNAVAILABLE = "bootstrap_anchor_evidence_unavailable"
DIAG_BOOTSTRAP_VIDEO_UNAVAILABLE = "bootstrap_video_unavailable"
DIAG_BOOTSTRAP_MODEL_DISABLED = "bootstrap_model_inference_disabled"
DIAG_BOOTSTRAP_DETECTOR_UNAVAILABLE = "bootstrap_detector_unavailable"
DIAG_BOOTSTRAP_NO_DETECTIONS = "bootstrap_no_detections"
DIAG_ROSTER_SKIPPED = "roster_confirmation_skipped"
DIAG_COURT_END_NOT_CONFIRMED = "court_end_not_confirmed"
DIAG_NO_FORMAL_WINDOWS = "no_formal_windows"
DIAG_REUSED_EXISTING_CONTEXT = "context_reused_for_same_job"


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def owner_key_for(capture_take_id: str | None = None, video_id: str | None = None) -> str:
    return court_end_svc.owner_key_for(capture_take_id, video_id)


def expected_player_count(match_format: str | None) -> int:
    return 2 if match_format == "singles" else 4


def _consumers_enabled() -> bool:
    """`rally_context_enabled` 的只读镜像；配置不可用时按关闭处理（保守）。"""
    try:
        from app.core.config import get_settings

        return bool(get_settings().rally_context_enabled)
    except Exception:  # noqa: BLE001
        return False


# ── 1. 受限 player bootstrap ──


def build_player_bootstrap(
    db: Session,
    *,
    capture_take_id: str | None = None,
    video_id: str | None = None,
    match_format: str | None = "doubles",
    source_job_ids: Iterable[str] = (),
    storage: Any | None = None,
) -> PlayerBootstrapResult:
    """构造 P1–P4 候选；绝不启动完整视觉 Pipeline，也绝不编造锚点。

    `source_job_ids` 由调用方按"最近优先"给出（通常来自任务控制面）；没有可复用
    产物时会按配置尝试首段轻量预检。
    """
    owner = owner_key_for(capture_take_id, video_id)
    job_ids = [job_id for job_id in source_job_ids if job_id]
    consumers_enabled = _consumers_enabled()
    base = {
        "owner_key": owner,
        "capture_take_id": capture_take_id,
        "video_id": video_id,
        "consumers_enabled": consumers_enabled,
    }
    if not job_ids:
        # 首次分析不能依赖“已有成功任务”。在模型推理已显式开启且视频可读时，
        # 只抽取最前 3 秒的稀疏帧做轻量候选预检；这不是完整 Pipeline，也不会写
        # tracking/metric 产物。模型不可用时仍诚实返回 unavailable，用户可手工确认或跳过。
        if video_id:
            fresh = _bootstrap_from_video(
                video_id=video_id,
                capture_take_id=capture_take_id,
                match_format=match_format,
                base=base,
            )
            if fresh is not None:
                return fresh
        return PlayerBootstrapResult(
            status="unavailable",
            unavailable_reason=DIAG_BOOTSTRAP_NO_SOURCE_JOB,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_NO_SOURCE_JOB,
                    detail="该素材还没有可复用的分析产物，无法生成候选参考帧；可手工确认或跳过",
                    severity="warning",
                )
            ],
            **base,
        )

    from app.services.storage_service import StorageService

    store = storage or StorageService()
    for job_id in job_ids:
        trajectory = _read_json(store.player_trajectory_json_path(job_id))
        roster_manifest = _read_json(store.roster_manifest_json_path(job_id))
        quality = _read_json(store.four_player_identification_quality_json_path(job_id))
        candidates = _candidates_from_trajectory(trajectory) or _candidates_from_roster(roster_manifest)
        if not candidates:
            continue
        diagnostics = _quality_diagnostics(quality)
        expected = expected_player_count(match_format)
        status = "available" if len(candidates) >= expected else "insufficient_candidates"
        if status == "insufficient_candidates":
            diagnostics.append(
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_INSUFFICIENT,
                    detail=f"仅识别到 {len(candidates)} 名候选，少于预期的 {expected} 名",
                    severity="warning",
                )
            )
        if all(candidate.anchor_court_xy is None for candidate in candidates):
            diagnostics.append(
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_ANCHOR_EVIDENCE_UNAVAILABLE,
                    detail="候选缺少球场坐标锚点，身份连续性只能按时间连续性降级判定",
                    severity="warning",
                )
            )
        reference_ms = next(
            (candidate.anchor_timestamp_ms for candidate in candidates if candidate.anchor_timestamp_ms),
            0,
        )
        return PlayerBootstrapResult(
            status=status,
            unavailable_reason=None if status == "available" else REASON_ROSTER_INSUFFICIENT_CANDIDATES,
            bootstrap_run_id=job_id,
            bootstrap_model_version=(
                str((trajectory or {}).get("schema_version") or "player-render-trajectory.v2")
            ),
            reference_timestamp_ms=reference_ms,
            reference_frame_url=_bootstrap_reference_frame_url(video_id, reference_ms),
            candidates=candidates,
            diagnostics=diagnostics,
            **base,
        )

    return PlayerBootstrapResult(
        status="unavailable",
        unavailable_reason=DIAG_BOOTSTRAP_NO_ARTIFACT,
        diagnostics=[
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_BOOTSTRAP_NO_ARTIFACT,
                detail="已有任务尚未产出可消费的球员产物，无法生成候选；可手工确认或跳过",
                severity="warning",
            )
        ],
        **base,
    )


def _bootstrap_reference_frame_url(video_id: str | None, timestamp_ms: int) -> str | None:
    if not video_id:
        return None
    return (
        "/api/analysis/players/bootstrap/frame?"
        f"videoId={quote(video_id, safe='')}&timestampMs={max(0, int(timestamp_ms))}"
    )


def _bootstrap_from_video(
    *,
    video_id: str,
    capture_take_id: str | None,
    match_format: str | None,
    base: dict[str, Any],
) -> PlayerBootstrapResult | None:
    """从源视频建立一次性候选参考帧。

    这是确认页的预检，不使用完整跟踪器、标定器或指标计算。故意把失败变成
    可解释的 unavailable/insufficient，而不是阻塞普通分析创建。
    """
    from app.core.config import get_settings
    from app.services.video_service import video_service

    settings = get_settings()
    video = video_service.get_available_video(video_id)
    if video is None:
        return PlayerBootstrapResult(
            status="unavailable",
            unavailable_reason=DIAG_BOOTSTRAP_VIDEO_UNAVAILABLE,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_VIDEO_UNAVAILABLE,
                    detail="源视频不可读，无法生成参考帧；可手工指定或跳过",
                    severity="warning",
                )
            ],
            **base,
        )
    if not settings.enable_model_inference:
        return PlayerBootstrapResult(
            status="unavailable",
            unavailable_reason=DIAG_BOOTSTRAP_MODEL_DISABLED,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_MODEL_DISABLED,
                    detail="当前部署未开启人体模型推理，无法自动生成候选；可手工指定或跳过",
                    severity="warning",
                )
            ],
            **base,
        )

    try:
        import cv2  # type: ignore

        from app.vision.player_tracking_engine.person_detector import PersonDetector

        detector = PersonDetector(
            model_path=settings.default_detector_model,
            conf_threshold=settings.detector_confidence,
            device=settings.detector_device,
        )
        capture = cv2.VideoCapture(str(video.path))
        if not capture.isOpened():
            return PlayerBootstrapResult(
                status="unavailable",
                unavailable_reason=DIAG_BOOTSTRAP_VIDEO_UNAVAILABLE,
                diagnostics=[
                    PlayerBootstrapQualityDiagnostic(
                        code=DIAG_BOOTSTRAP_VIDEO_UNAVAILABLE,
                        detail="OpenCV 无法打开源视频，无法生成参考帧",
                        severity="warning",
                    )
                ],
                **base,
            )
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        max_seconds = 3.0
        if frame_count > 0 and fps > 0:
            max_seconds = min(max_seconds, max(0.0, (frame_count - 1) / fps))
        sample_count = max(1, min(12, int(max_seconds * 4) + 1))
        tracks: list[dict[str, Any]] = []
        best_timestamp_ms = 0
        best_detection_count = 0
        try:
            for sample_index in range(sample_count):
                timestamp_s = 0.0 if sample_count == 1 else max_seconds * sample_index / (sample_count - 1)
                frame_index = int(round(timestamp_s * fps))
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                detections = detector.detect(frame)
                visible = [item for item in detections if len(item.bbox) == 4 and item.confidence >= settings.detector_confidence]
                if len(visible) > best_detection_count:
                    best_detection_count = len(visible)
                    best_timestamp_ms = int(round(timestamp_s * 1000))
                height, width = frame.shape[:2]
                for detection in visible:
                    x1, y1, x2, y2 = [float(value) for value in detection.bbox]
                    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
                    area = max(1.0, (x2 - x1) * (y2 - y1))
                    match = None
                    match_score = 0.0
                    for track in tracks:
                        tx, ty = track["last_center"]
                        distance = hypot((cx - tx) / max(width, 1), (cy - ty) / max(height, 1))
                        if distance < 0.15 and (1.0 - distance / 0.15) > match_score:
                            match = track
                            match_score = 1.0 - distance / 0.15
                    if match is None:
                        match = {
                            "first_timestamp_ms": int(round(timestamp_s * 1000)),
                            "first_bbox": [x1, y1, x2, y2],
                            "first_center": [cx, cy],
                            "last_center": (cx, cy),
                            "hits": 0,
                            "confidence_sum": 0.0,
                            "best_confidence": 0.0,
                            "area": area,
                        }
                        tracks.append(match)
                    match["last_center"] = (cx, cy)
                    match["hits"] += 1
                    match["confidence_sum"] += float(detection.confidence)
                    match["best_confidence"] = max(match["best_confidence"], float(detection.confidence))
        finally:
            capture.release()
    except Exception as exc:  # noqa: BLE001 - optional preflight must never block analysis
        return PlayerBootstrapResult(
            status="unavailable",
            unavailable_reason=DIAG_BOOTSTRAP_DETECTOR_UNAVAILABLE,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_DETECTOR_UNAVAILABLE,
                    detail=f"候选预检不可用（{exc}）；可手工指定或跳过",
                    severity="warning",
                )
            ],
            **base,
        )

    expected = expected_player_count(match_format)
    tracks.sort(key=lambda item: (-int(item["hits"]), -float(item["best_confidence"])))
    selected = tracks[:expected]
    selected.sort(key=lambda item: (float(item["first_center"][0]), float(item["first_center"][1])))
    candidates = [
        PlayerBootstrapCandidate(
            canonical_player_id=f"Player_{index + 1}",
            display_name=f"P{index + 1}",
            anchor_timestamp_ms=int(item["first_timestamp_ms"]),
            anchor_bbox=[float(value) for value in item["first_bbox"]],
            confidence=(float(item["confidence_sum"]) / max(1, int(item["hits"]))),
        )
        for index, item in enumerate(selected)
    ]
    if not candidates:
        return PlayerBootstrapResult(
            status="unavailable",
            unavailable_reason=DIAG_BOOTSTRAP_NO_DETECTIONS,
            diagnostics=[
                PlayerBootstrapQualityDiagnostic(
                    code=DIAG_BOOTSTRAP_NO_DETECTIONS,
                    detail="前 3 秒稀疏帧没有稳定的人体候选；可手工指定或跳过",
                    severity="warning",
                )
            ],
            **base,
        )
    status = "available" if len(candidates) >= expected else "insufficient_candidates"
    diagnostics = [
        PlayerBootstrapQualityDiagnostic(
            code=DIAG_ANCHOR_EVIDENCE_UNAVAILABLE,
            detail="预检仅有画面 bbox，尚未进行球场标定；Team A/B 与端位仍需用户确认",
            severity="info",
        )
    ]
    if status == "insufficient_candidates":
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=DIAG_BOOTSTRAP_INSUFFICIENT,
                detail=f"仅识别到 {len(candidates)} 名候选，少于预期的 {expected} 名",
                severity="warning",
            )
        )
    run_id = f"bootstrap_{uuid4().hex[:12]}"
    model_version = str(settings.default_detector_model)
    return PlayerBootstrapResult(
        status=status,
        unavailable_reason=None if status == "available" else REASON_ROSTER_INSUFFICIENT_CANDIDATES,
        bootstrap_run_id=run_id,
        bootstrap_model_version=model_version,
        reference_timestamp_ms=best_timestamp_ms,
        reference_frame_url=_bootstrap_reference_frame_url(video_id, best_timestamp_ms),
        candidates=candidates,
        diagnostics=diagnostics,
        **base,
    )


def _candidates_from_trajectory(trajectory: dict[str, Any] | None) -> list[PlayerBootstrapCandidate]:
    if not isinstance(trajectory, dict):
        return []
    samples_by_player: dict[str, dict[str, Any]] = {}
    for sample in trajectory.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        player_id = sample.get("player_id")
        if not isinstance(player_id, str) or not player_id.startswith("Player_"):
            continue
        existing = samples_by_player.get(player_id)
        if existing is None or float(sample.get("timestamp_seconds") or 0) < float(
            existing.get("timestamp_seconds") or 0
        ):
            samples_by_player[player_id] = sample

    candidates: list[PlayerBootstrapCandidate] = []
    for player in trajectory.get("players") or []:
        if not isinstance(player, dict):
            continue
        player_id = player.get("player_id")
        if not isinstance(player_id, str) or not player_id.startswith("Player_"):
            continue
        sample = samples_by_player.get(player_id) or {}
        court_xy = None
        if sample.get("x_ft") is not None and sample.get("y_ft") is not None:
            court_xy = [float(sample["x_ft"]), float(sample["y_ft"])]
        bbox = sample.get("bbox")
        candidates.append(
            PlayerBootstrapCandidate(
                canonical_player_id=player_id,
                display_name=player.get("render_slot") or player_id,
                anchor_timestamp_ms=int(round(float(sample.get("timestamp_seconds") or 0) * 1000)),
                anchor_bbox=[float(value) for value in bbox] if isinstance(bbox, list) and len(bbox) == 4 else None,
                anchor_court_xy=court_xy,
                confidence=(
                    float(sample["confidence"]) if sample.get("confidence") is not None else None
                ),
            )
        )
    return sorted(candidates, key=lambda item: item.canonical_player_id)


def _candidates_from_roster(roster_manifest: dict[str, Any] | None) -> list[PlayerBootstrapCandidate]:
    if not isinstance(roster_manifest, dict):
        return []
    candidates: list[PlayerBootstrapCandidate] = []
    for player in roster_manifest.get("players") or []:
        if not isinstance(player, dict):
            continue
        player_id = player.get("player_id")
        if not isinstance(player_id, str) or not player_id.startswith("Player_"):
            continue
        candidates.append(
            PlayerBootstrapCandidate(
                canonical_player_id=player_id,
                display_name=player.get("label") or player_id,
            )
        )
    return sorted(candidates, key=lambda item: item.canonical_player_id)


def _quality_diagnostics(quality: dict[str, Any] | None) -> list[PlayerBootstrapQualityDiagnostic]:
    if not isinstance(quality, dict):
        return []
    diagnostics: list[PlayerBootstrapQualityDiagnostic] = []
    status = quality.get("status")
    if status and status != "available":
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=f"four_player_quality_{status}",
                detail=str(quality.get("detail") or "四球员身份质量产物不可用"),
                severity="warning",
            )
        )
    verdict = quality.get("verdict")
    if verdict and verdict != "pass":
        reason = ", ".join(str(item) for item in (quality.get("failure_reasons") or [])) or "未说明原因"
        diagnostics.append(
            PlayerBootstrapQualityDiagnostic(
                code=f"four_player_quality_verdict_{verdict}",
                detail=reason,
                severity="warning",
            )
        )
    return diagnostics


# ── 2. 冻结分析名册 ──


def _roster_payload_of(row: AnalysisRosterSnapshot) -> AnalysisRosterSnapshotPayload:
    try:
        entries_raw = json.loads(row.entries_json or "[]")
    except json.JSONDecodeError:
        entries_raw = []
    entries = [AnalysisRosterConfirmationEntry(**item) for item in entries_raw if isinstance(item, dict)]
    return AnalysisRosterSnapshotPayload(
        snapshot_id=row.id,
        owner_key=row.owner_key,
        capture_take_id=row.capture_take_id,
        video_id=row.video_id,
        job_id=row.job_id,
        status=row.status,  # type: ignore[arg-type]
        unavailable_reason=row.unavailable_reason,
        source=row.source,  # type: ignore[arg-type]
        initial_team_a_end=row.initial_team_a_end,  # type: ignore[arg-type]
        entries=entries,
        confirmed_at=row.confirmed_at,
    )


def _build_roster_payload(
    *,
    capture_take_id: str | None,
    video_id: str | None,
    request: RosterConfirmationRequest,
    match_format: str | None = "doubles",
) -> AnalysisRosterSnapshotPayload:
    """构造名册快照的纯结果（不写库）。跳过与候选不足都显式降级。"""
    owner = owner_key_for(capture_take_id, video_id)
    expected = expected_player_count(match_format)

    if request.skipped:
        status, reason, source = "skipped", REASON_ROSTER_SKIPPED_BY_USER, "skipped"
    elif not request.entries:
        status, reason, source = "unavailable", REASON_ROSTER_NOT_CONFIRMED, "bootstrap_default"
    elif len(request.entries) < expected:
        status, reason, source = "insufficient_candidates", REASON_ROSTER_INSUFFICIENT_CANDIDATES, "manual"
    else:
        status, reason, source = "available", None, "manual"

    entries = [
        entry.model_copy(
            update={
                "bootstrap_run_id": entry.bootstrap_run_id or request.bootstrap_run_id,
                "bootstrap_model_version": entry.bootstrap_model_version or request.bootstrap_model_version,
            }
        )
        for entry in request.entries
    ]
    return AnalysisRosterSnapshotPayload(
        snapshot_id=_generate_id(_ID_PREFIX_ROSTER),
        owner_key=owner,
        capture_take_id=capture_take_id,
        video_id=video_id,
        job_id=None,
        status=status,  # type: ignore[arg-type]
        unavailable_reason=reason,
        source=source,  # type: ignore[arg-type]
        initial_team_a_end=request.initial_team_a_end,
        entries=entries,
        confirmed_at=datetime.now(UTC),
    )


def _persist_roster_payload(db: Session, payload: AnalysisRosterSnapshotPayload, *, job_id: str) -> AnalysisRosterSnapshot:
    row = AnalysisRosterSnapshot(
        id=payload.snapshot_id,
        owner_key=payload.owner_key,
        capture_take_id=payload.capture_take_id,
        video_id=payload.video_id,
        job_id=job_id,
        status=payload.status,
        unavailable_reason=payload.unavailable_reason,
        source=payload.source,
        initial_team_a_end=payload.initial_team_a_end,
        entries_json=json.dumps(
            [entry.model_dump(mode="json") for entry in payload.entries], ensure_ascii=False
        ),
        roster_hash=payload.roster_hash,
        confirmed_at=payload.confirmed_at,
        created_at=payload.confirmed_at,
    )
    db.add(row)
    db.flush()
    return row


def freeze_roster_snapshot(
    db: Session,
    *,
    capture_take_id: str | None,
    video_id: str | None,
    job_id: str,
    request: RosterConfirmationRequest | None,
    match_format: str | None = "doubles",
) -> AnalysisRosterSnapshotPayload:
    """Job 创建时冻结名册。名册一旦冻结，后续编辑只能产生新 Job 的新名册。"""
    payload = _build_roster_payload(
        capture_take_id=capture_take_id,
        video_id=video_id,
        request=request or RosterConfirmationRequest(skipped=True),
        match_format=match_format,
    )
    _persist_roster_payload(db, payload, job_id=job_id)

    # Job 级端位确认：Job 提交时一并落盘，作为端位投影的种子。
    if payload.initial_team_a_end in ("end_a", "end_b"):
        court_end_svc.confirm_initial_court_end(
            db,
            capture_take_id=capture_take_id,
            video_id=video_id,
            team_a_end=payload.initial_team_a_end,
            job_id=job_id,
        )
    return payload


def get_roster_snapshot(db: Session, *, job_id: str | None = None, owner_key: str | None = None):
    query = db.query(AnalysisRosterSnapshot)
    if job_id:
        query = query.filter(AnalysisRosterSnapshot.job_id == job_id)
    elif owner_key:
        query = query.filter(AnalysisRosterSnapshot.owner_key == owner_key)
    else:
        return None
    return query.order_by(AnalysisRosterSnapshot.created_at.desc()).first()


def roster_payload_for_job(db: Session, job_id: str) -> AnalysisRosterSnapshotPayload | None:
    row = get_roster_snapshot(db, job_id=job_id)
    return _roster_payload_of(row) if row is not None else None


def roster_snapshot_hash_for_job(db: Session, job_id: str) -> str | None:
    payload = roster_payload_for_job(db, job_id)
    return payload.roster_hash if payload is not None else None


# ── 3. formal window 绑定 ──


def _segment_start_event_id(db: Session, segment_id: str | None) -> tuple[str | None, str | None]:
    if not segment_id:
        return None, None
    segment = db.query(CaptureSegment).filter(CaptureSegment.id == segment_id).first()
    if segment is None:
        return None, None
    return segment.id, segment.start_event_id


def bind_formal_window(
    db: Session,
    *,
    capture_take_id: str,
    window: dict[str, Any],
    snapshots: list,
    tolerance_ms: int = DEFAULT_TEMPORAL_TOLERANCE_MS,
) -> tuple[ContextBinding, Any | None]:
    """按证据强度绑定：direct_segment_link > direct_start_event_link > unique_temporal_match > unavailable。"""
    diagnostics: list[str] = []
    start_ms = int(window.get("start_ms") or 0)

    # 1) 直接 segment 链路：window 携带源 rally segment id，从其 start_event_id 命中快照
    segment_id = window.get("source_rally_segment_id")
    resolved_segment_id, start_event_id = _segment_start_event_id(db, segment_id)
    if resolved_segment_id and start_event_id:
        snapshot = scoring_svc.find_by_start_event_id(db, capture_take_id, start_event_id)
        if snapshot is not None:
            return (
                ContextBinding(
                    method="direct_segment_link",
                    source_segment_id=resolved_segment_id,
                    source_start_event_id=start_event_id,
                    candidate_count=1,
                    diagnostics=["源 rally segment 的 start_event_id 直接命中计分快照"],
                ),
                snapshot,
            )
        diagnostics.append("源 rally segment 存在但没有对应计分快照")

    # 2) 直接 start-event 链路：window 自己携带 start_event_id
    direct_event_id = window.get("source_start_event_id")
    if direct_event_id:
        snapshot = scoring_svc.find_by_start_event_id(db, capture_take_id, direct_event_id)
        if snapshot is not None:
            return (
                ContextBinding(
                    method="direct_start_event_link",
                    source_segment_id=window.get("segment_id"),
                    source_start_event_id=direct_event_id,
                    candidate_count=1,
                    diagnostics=["window 的 start_event_id 直接命中计分快照"],
                ),
                snapshot,
            )
        diagnostics.append("window 的 start_event_id 没有对应计分快照")

    # 3) 唯一时间匹配：合法顺序（回合开始不晚于窗口开始）+ 容差 + 唯一性
    candidates = [
        snapshot
        for snapshot in snapshots
        if snapshot.start_ms <= start_ms and (start_ms - snapshot.start_ms) <= tolerance_ms
    ]
    if len(candidates) == 1:
        return (
            ContextBinding(
                method="unique_temporal_match",
                source_segment_id=window.get("segment_id"),
                candidate_count=1,
                diagnostics=[f"唯一时间候选（Δt={start_ms - candidates[0].start_ms}ms，容差 {tolerance_ms}ms）"],
            ),
            candidates[0],
        )
    if len(candidates) > 1:
        diagnostics.append(f"{len(candidates)} 个时间候选，歧义降级为 unavailable")
        return (
            ContextBinding(method="unavailable", candidate_count=len(candidates), diagnostics=diagnostics),
            None,
        )
    diagnostics.append(REASON_NO_TEMPORAL_CANDIDATE)
    return ContextBinding(method="unavailable", candidate_count=0, diagnostics=diagnostics), None


# ── 4. 合成 Job-bound 分析回合上下文 ──


def compose_rally_context(
    db: Session,
    *,
    job_id: str,
    capture_take_id: str | None,
    owner_key: str | None = None,
    match_format: str | None = "doubles",
    formal_windows: list[dict[str, Any]] | None = None,
    temporal_tolerance_ms: int = DEFAULT_TEMPORAL_TOLERANCE_MS,
    roster_payload: AnalysisRosterSnapshotPayload | None = None,
    initial_team_a_end: str | None = None,
) -> AnalysisRallyContextSnapshotPayload:
    """由三份冻结来源合成不可变回合上下文（本函数只读，不写库）。

    ``roster_payload`` 与 ``initial_team_a_end`` 支持 Job 提交前的纯规划：
    用户刚确认的输入尚未持久化时，composer 仍必须使用这份待冻结事实，
    不能回查空的 job_id 或 owner 上一次的可变确认。
    """
    diagnostics: list[str] = []
    roster = roster_payload if roster_payload is not None else roster_payload_for_job(db, job_id)
    roster_hash = roster.roster_hash if roster is not None else None
    if roster is None or roster.status != "available":
        diagnostics.append((roster.unavailable_reason if roster is not None else None) or REASON_ROSTER_NOT_CONFIRMED)

    court_projection = court_end_svc.build_court_end_projection(
        db,
        capture_take_id=capture_take_id,
        owner_key=owner_key,
        initial_team_a_end=initial_team_a_end,
    )
    if court_projection.status != "available":
        diagnostics.append(court_projection.unavailable_reason or "court_end_unavailable")

    snapshots = scoring_svc.effective_scoring_snapshots(db, capture_take_id) if capture_take_id else []
    if not snapshots:
        diagnostics.append(REASON_NO_SCORING_SNAPSHOTS)

    rallies: list[AnalysisRallyContextRally] = []

    if formal_windows:
        for window in formal_windows:
            binding, snapshot = bind_formal_window(
                db,
                capture_take_id=capture_take_id or "",
                window=window,
                snapshots=snapshots,
                tolerance_ms=temporal_tolerance_ms,
            )
            rallies.append(
                _build_context_rally(
                    rally_id=str(window.get("segment_id") or ""),
                    ordinal=int(window.get("ordinal") or len(rallies) + 1),
                    start_ms=int(window.get("start_ms") or 0),
                    end_ms=int(window.get("end_ms")) if window.get("end_ms") is not None else None,
                    binding=binding,
                    snapshot=snapshot,
                    roster=roster,
                    court_projection=court_projection,
                    job_id=job_id,
                )
            )
    else:
        diagnostics.append(DIAG_NO_FORMAL_WINDOWS)
        # 没有正式窗口计划时，直接用录制期 rally 事实组织上下文（人工时间轴路径）。
        for snapshot in snapshots:
            binding = ContextBinding(method="direct_segment_link" if snapshot.rally_id else "unavailable")
            if snapshot.rally_id:
                binding = binding.model_copy(update={"source_segment_id": snapshot.rally_id})
            rallies.append(
                _build_context_rally(
                    rally_id=snapshot.rally_id or f"rally-{snapshot.ordinal}",
                    ordinal=snapshot.ordinal,
                    start_ms=snapshot.start_ms,
                    end_ms=None,
                    binding=binding,
                    snapshot=snapshot,
                    roster=roster,
                    court_projection=court_projection,
                    job_id=job_id,
                )
            )

    available = [item for item in rallies if item.status == "available"]
    if not rallies:
        status = "unavailable"
    elif len(available) == len(rallies):
        status = "available"
    elif available:
        status = "partial"
    else:
        status = "unavailable"

    scoring_hashes = sorted({item.scoring_hash for item in available if item.scoring_hash})
    payload = AnalysisRallyContextSnapshotPayload(
        context_set_id=_generate_id(_ID_PREFIX_CONTEXT),
        job_id=job_id,
        capture_take_id=capture_take_id,
        status=status,  # type: ignore[arg-type]
        unavailable_reason=None if status == "available" else (diagnostics[0] if diagnostics else "context_unavailable"),
        scoring_hash=(scoring_hashes[0] if len(scoring_hashes) == 1 else None),
        roster_hash=roster_hash,
        court_end_hash=court_projection.court_end_hash,
        rallies=rallies,
        diagnostics=diagnostics,
        created_at=datetime.now(UTC),
    )
    return _with_context_hashes(payload)


def _with_context_hashes(payload: AnalysisRallyContextSnapshotPayload) -> AnalysisRallyContextSnapshotPayload:
    from app.schemas.rally_context import context_hash as compute_context_hash

    rallies = [
        item.model_copy(update={"context_hash": compute_context_hash(item.model_dump(mode="json"))})
        for item in payload.rallies
    ]
    return payload.model_copy(update={"rallies": rallies})


def _build_context_rally(
    *,
    rally_id: str,
    ordinal: int,
    start_ms: int,
    end_ms: int | None,
    binding: ContextBinding,
    snapshot: Any | None,
    roster: AnalysisRosterSnapshotPayload | None,
    court_projection: Any,
    job_id: str,
) -> AnalysisRallyContextRally:
    team_a_end, team_b_end = court_projection.team_end_at(start_ms)
    roster_available = roster is not None and roster.status == "available"
    team_a_players = roster.players_for_team("A") if roster_available else []
    team_b_players = roster.players_for_team("B") if roster_available else []

    reasons: list[str] = []
    if binding.method == "unavailable":
        reasons.append(
            REASON_AMBIGUOUS_TEMPORAL_MATCH
            if binding.candidate_count > 1
            else (binding.diagnostics[-1] if binding.diagnostics else REASON_NO_TEMPORAL_CANDIDATE)
        )
    if snapshot is None:
        reasons.append(REASON_NO_SCORING_SNAPSHOTS)
    if not roster_available:
        reasons.append((roster.unavailable_reason if roster is not None else None) or REASON_ROSTER_NOT_CONFIRMED)
    if team_a_end is None:
        reasons.append(court_projection.unavailable_reason or "court_end_unavailable")

    status = "available" if not reasons else "unavailable"
    return AnalysisRallyContextRally(
        rally_id=rally_id,
        ordinal=ordinal,
        start_ms=start_ms,
        end_ms=end_ms,
        status=status,  # type: ignore[arg-type]
        unavailable_reason=(reasons[0] if reasons else None),
        scoring_snapshot_id=(snapshot.id if snapshot is not None else None),
        scoring_hash=(scoring_svc.snapshot_hash_of(snapshot) if snapshot is not None else None),
        start_event_id=(snapshot.event_id if snapshot is not None else None),
        server_team=(snapshot.server_team if snapshot is not None else None),
        score_a_before=(snapshot.score_a_before if snapshot is not None else None),
        score_b_before=(snapshot.score_b_before if snapshot is not None else None),
        team_a_end=team_a_end,
        team_b_end=team_b_end,
        team_a_players=team_a_players,
        team_b_players=team_b_players,
        binding=binding,
    )


def persist_rally_context(db: Session, payload: AnalysisRallyContextSnapshotPayload) -> AnalysisRallyContextSet:
    """持久化不可变上下文集合。同一 Job 已有上下文时返回既有版本（不回写）。"""
    existing = get_context_set(db, payload.job_id)
    if existing is not None:
        return existing

    owner = payload.capture_take_id or payload.job_id
    row = AnalysisRallyContextSet(
        id=payload.context_set_id,
        owner_key=owner,
        job_id=payload.job_id,
        capture_take_id=payload.capture_take_id,
        status=payload.status,
        unavailable_reason=payload.unavailable_reason,
        scoring_hash=payload.scoring_hash,
        roster_hash=payload.roster_hash,
        court_end_hash=payload.court_end_hash,
        context_set_hash=payload.context_set_hash(),
        payload_json=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
        version=payload.version,
        supersedes_context_set_id=payload.supersedes_context_set_id,
        created_at=payload.created_at,
    )
    db.add(row)
    db.flush()
    return row


def get_context_set(db: Session, job_id: str, version: int | None = None) -> AnalysisRallyContextSet | None:
    query = db.query(AnalysisRallyContextSet).filter(AnalysisRallyContextSet.job_id == job_id)
    if version is not None:
        query = query.filter(AnalysisRallyContextSet.version == version)
    return query.order_by(AnalysisRallyContextSet.version.desc()).first()


def context_payload(row: AnalysisRallyContextSet | None) -> AnalysisRallyContextSnapshotPayload | None:
    if row is None:
        return None
    try:
        raw = json.loads(row.payload_json or "{}")
    except json.JSONDecodeError:
        return None
    return AnalysisRallyContextSnapshotPayload(**raw)


def context_input_hash(payload: AnalysisRallyContextSnapshotPayload) -> str:
    """Job 输入签名用的上下文 hash：排除 job_id 等运行期标识。

    去重必须只依赖"素材 + 名册 + 计分事实 + 端位 + 绑定结果"，否则每次新建 job
    都会因为 job_id 不同而无法去重。
    """
    from app.schemas.rally_context import canonical_hash

    material = {
        key: value
        for key, value in payload.model_dump(mode="json").items()
        if key not in {"job_id", "context_set_id", "created_at", "version", "supersedes_context_set_id"}
    }
    material["rallies"] = [
        {key: value for key, value in item.items() if key != "context_hash"}
        for item in material.get("rallies", [])
    ]
    return canonical_hash(material)


def context_set_hash_for_job(db: Session, job_id: str) -> str | None:
    row = get_context_set(db, job_id)
    return row.context_set_hash if row is not None else None


# ── 5. bootstrap → 正式身份的可审计绑定 ──


def build_bootstrap_binding_audit(
    *,
    job_id: str,
    roster: AnalysisRosterSnapshotPayload | None,
    formal_roster_payload: dict[str, Any] | None,
    position_tolerance_ft: float = 32.0,
) -> BootstrapBindingAuditPayload | None:
    """为每个确认条目产出一条绑定结论；绑定不成立时明确 unavailable，不静默改编号。

    判定顺序：

    1. 正式 roster 里不存在该 canonical player → `unavailable`（confirmed=False）。
    2. 存在且 anchor 有球场坐标、正式产物里能找到容差内的同 id 观测 → `anchor_reacquire`。
    3. 存在但缺少位置锚点证据 → `unavailable`（不把编号/时间连续性当作身份确认）。
    """
    if roster is None or roster.status != "available":
        return None

    payload = formal_roster_payload or {}
    # 正式 roster 的字段名随产物而异：`player_roster`（reconstructed v2 报告）与
    # `players`（global-player-roster / render trajectory）都要接受。
    formal_entries = payload.get("players") or payload.get("player_roster") or []
    formal_players = {
        str(item.get("player_id")): item
        for item in formal_entries
        if isinstance(item, dict) and item.get("player_id")
    }
    formal_positions: dict[str, list[tuple[float, float]]] = {}
    for sample in payload.get("samples") or []:
        if not isinstance(sample, dict):
            continue
        player_id = sample.get("player_id")
        if not isinstance(player_id, str) or sample.get("x_ft") is None or sample.get("y_ft") is None:
            continue
        formal_positions.setdefault(player_id, []).append((float(sample["x_ft"]), float(sample["y_ft"])))

    entries: list[BootstrapBindingAuditEntry] = []
    for entry in roster.entries:
        player_id = entry.canonical_player_id
        base = {
            "canonical_player_id": player_id,
            "bootstrap_run_id": entry.bootstrap_run_id,
            "source_view_id": entry.source_view_id,
            "anchor_timestamp_ms": entry.anchor_timestamp_ms,
            "anchor_court_xy": entry.anchor_court_xy,
        }
        if player_id not in formal_players:
            entries.append(
                BootstrapBindingAuditEntry(
                    method="unavailable",
                    confirmed=False,
                    reason=REASON_BOOTSTRAP_BINDING_FAILED,
                    **base,
                )
            )
            continue
        anchor_xy = entry.anchor_court_xy
        positions = formal_positions.get(player_id) or []
        if anchor_xy and len(anchor_xy) == 2 and positions:
            nearest = min(
                (abs(x - anchor_xy[0]) ** 2 + abs(y - anchor_xy[1]) ** 2) ** 0.5 for x, y in positions
            )
            if nearest <= position_tolerance_ft:
                entries.append(
                    BootstrapBindingAuditEntry(
                        formal_canonical_player_id=player_id,
                        method="anchor_reacquire",
                        confidence=entry.bootstrap_confidence,
                        confirmed=True,
                        reason=f"锚点在容差内重新捕获（最近距离 {nearest:.1f}ft）",
                        **base,
                    )
                )
                continue
            entries.append(
                BootstrapBindingAuditEntry(
                    formal_canonical_player_id=player_id,
                    method="temporal_fallback",
                    confidence=entry.bootstrap_confidence,
                    confirmed=False,
                    reason=f"锚点位置失配（最近距离 {nearest:.1f}ft），拒绝静默换绑",
                    **base,
                )
            )
            continue
        entries.append(
            BootstrapBindingAuditEntry(
                # 没有 anchor_court_xy 就没有足够证据证明 bootstrap 人员和
                # formal canonical player 是同一人。这里必须 fail closed：
                # 保留原始 bootstrap 编号供审计，但不确认 formal 身份，
                # 也不能把 temporal/slot continuity 冒充成正式绑定。
                method="unavailable",
                confidence=entry.bootstrap_confidence,
                confirmed=False,
                reason=REASON_BOOTSTRAP_BINDING_FAILED,
                **base,
            )
        )

    confirmed_count = sum(1 for entry in entries if entry.confirmed)
    if confirmed_count == len(entries):
        status = "available"
        reason = None
    elif confirmed_count:
        status = "partial"
        reason = REASON_BOOTSTRAP_BINDING_PARTIAL
    else:
        status = "unavailable"
        reason = REASON_BOOTSTRAP_BINDING_FAILED

    return BootstrapBindingAuditPayload(
        job_id=job_id,
        roster_hash=roster.roster_hash,
        status=status,  # type: ignore[arg-type]
        unavailable_reason=reason,
        entries=entries,
    )


# ── 6. formal segment 的源 rally 引用（direct link 的材料）──


def attach_window_context_binding(
    db: Session,
    *,
    capture_take_id: str | None,
    segments: Iterable[dict[str, Any]],
    context: AnalysisRallyContextSnapshotPayload | None,
    tolerance_ms: int = DEFAULT_TEMPORAL_TOLERANCE_MS,
) -> list[dict[str, Any]]:
    """为 formal window 挂上源 rally 引用与 job-bound 上下文绑定（优先级同 `bind_formal_window`）。

    这些字段**不参与 window plan 的 hash 计算**，因此不会改变既有计划的身份；
    但会写进计划 JSON，让 formal Rally 能引用冻结上下文而不是查询可变现场状态。

    歧义或多候选一律降级为 `unavailable` 并记录诊断，绝不猜测。
    """
    items = [dict(segment) for segment in segments]
    if not capture_take_id:
        return items

    manual_rallies = [
        segment
        for segment in db.query(CaptureSegment).filter(CaptureSegment.capture_take_id == capture_take_id).all()
        if segment.segment_type.value == "rally" and segment.segmentation_run_id is None and segment.start_event_id
    ]
    context_rallies = list(context.rallies) if context is not None else []

    for item in items:
        try:
            start_ms = int(item.get("start_ms"))
        except (TypeError, ValueError):
            continue
        diagnostics: list[str] = []

        # 1) direct_segment_link：唯一命中录制期 rally 区间，其 start_event_id 是直接证据
        #    未结束的 rally 区间（effective_end_ms 为 None）视为向上开放。
        matches = [
            segment
            for segment in manual_rallies
            if segment.start_ms <= start_ms
            and (segment.effective_end_ms is None or start_ms <= segment.effective_end_ms)
            and abs(start_ms - segment.start_ms) <= tolerance_ms
        ]
        if len(matches) == 1:
            source = matches[0]
            item["source_rally_segment_id"] = source.id
            item["source_start_event_id"] = source.start_event_id
            bound = next((rally for rally in context_rallies if rally.rally_id == source.id), None)
            if bound is not None:
                item["context_rally_id"] = bound.rally_id
                item["context_hash"] = bound.context_hash
                item["binding_method"] = "direct_segment_link"
                item["binding_diagnostics"] = ["源 rally segment 直接命中冻结上下文"]
                continue
            diagnostics.append("源 rally segment 命中，但冻结上下文中没有对应回合（可能名册/计分未确认）")

        # 2) direct_start_event_link：窗口自带 start_event_id
        if item.get("source_start_event_id") and context_rallies:
            bound = next(
                (
                    rally
                    for rally in context_rallies
                    if rally.scoring_snapshot_id and rally.binding.source_start_event_id == item["source_start_event_id"]
                ),
                None,
            )
            if bound is not None:
                item["context_rally_id"] = bound.rally_id
                item["context_hash"] = bound.context_hash
                item["binding_method"] = "direct_start_event_link"
                item["binding_diagnostics"] = ["start_event_id 命中冻结上下文"]
                continue

        # 3) unique_temporal_match：合法顺序 + 容差 + 唯一性
        candidates = [
            rally
            for rally in context_rallies
            if rally.start_ms <= start_ms and (start_ms - rally.start_ms) <= tolerance_ms
        ]
        if len(candidates) == 1:
            item["context_rally_id"] = candidates[0].rally_id
            item["context_hash"] = candidates[0].context_hash
            item["binding_method"] = "unique_temporal_match"
            item["binding_diagnostics"] = [f"唯一时间候选（Δt={start_ms - candidates[0].start_ms}ms）"]
            continue

        # 4) unavailable
        if len(candidates) > 1:
            diagnostics.append(f"{len(candidates)} 个时间候选，歧义降级为 unavailable")
        elif not context_rallies:
            diagnostics.append(REASON_NO_SCORING_SNAPSHOTS)
        else:
            diagnostics.append(REASON_NO_TEMPORAL_CANDIDATE)
        item["binding_method"] = "unavailable"
        item["binding_diagnostics"] = diagnostics
    return items


def plan_context_for_job(db: Session, *, payload: Any) -> dict[str, Any]:
    """签名前计算名册与上下文的**纯**结果（不写库）。

    因为去重可能直接复用既有 Job，这里绝不能产生副作用；否则会留下绑定到不存在
    Job 的孤儿名册/上下文记录。
    """
    capture_take_id = payload.metadata.capture_take_id
    video_id = payload.videoId
    roster_payload = None
    if payload.rosterConfirmation is not None:
        roster_payload = _build_roster_payload(
            capture_take_id=capture_take_id,
            video_id=video_id,
            request=payload.rosterConfirmation,
            match_format=payload.metadata.matchFormat,
        )

    context = compose_rally_context(
        db,
        job_id="",
        capture_take_id=capture_take_id,
        match_format=payload.metadata.matchFormat,
        roster_payload=roster_payload,
        initial_team_a_end=(
            roster_payload.initial_team_a_end
            if roster_payload is not None
            else None
        ),
    )
    context = _with_context_hashes(context)
    return {
        "roster_payload": roster_payload,
        "context_payload": context,
        "roster_hash": roster_payload.roster_hash if roster_payload is not None else None,
        "context_input_hash": context_input_hash(context),
    }


def persist_context_binding(db: Session, *, job_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """去重通过后落盘名册与上下文，并返回写入 Job 摘要的 hash/状态字段。"""
    roster_payload = plan.get("roster_payload")
    context: AnalysisRallyContextSnapshotPayload = plan["context_payload"]

    if roster_payload is not None:
        _persist_roster_payload(db, roster_payload, job_id=job_id)
        if roster_payload.initial_team_a_end in ("end_a", "end_b"):
            court_end_svc.confirm_initial_court_end(
                db,
                capture_take_id=roster_payload.capture_take_id,
                video_id=roster_payload.video_id,
                team_a_end=roster_payload.initial_team_a_end,
                job_id=job_id,
            )

    # 规划阶段使用空 Job id 以保持纯函数；真正落库时 Job id 已确定，
    # 因而必须重新计算逐回合 context_hash，再计算 context-set hash，
    # 否则 payload 内部 hash 会与其 provenance 的实际 Job 不一致。
    context = _with_context_hashes(context.model_copy(update={"job_id": job_id}))
    row = persist_rally_context(db, context)
    return {
        "roster_hash": roster_payload.roster_hash if roster_payload is not None else None,
        "roster_status": roster_payload.status if roster_payload is not None else None,
        "context_input_hash": plan["context_input_hash"],
        "context_set_hash": row.context_set_hash,
        "context_status": context.status,
    }
