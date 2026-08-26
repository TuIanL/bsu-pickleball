"""评分校准标注工作台的持久化、候选适配和 Gold Set 服务。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.capture_segment import CaptureSegment
from app.models.capture_take import CaptureTake
from app.models.scoring_calibration_annotation import (
    ScoringCalibrationAnnotation,
    ScoringCalibrationCandidateDecision,
    ScoringCalibrationPackage,
)
from app.schemas.scoring_calibration_annotation import (
    AnnotationCandidate,
    AnnotationDecision,
    AnnotationPackageCreateRequest,
    AnnotationPackageRevisionRequest,
    AnnotationPackageStatus,
    AnnotationRecord,
    AnnotationSource,
    AnnotationUpdateRequest,
    AnnotationUpsertRequest,
    CandidateDecisionRequest,
    GoldSetResponse,
    QualitySummary,
    SCORING_CALIBRATION_SCHEMA_VERSION,
    ValidationIssue,
    annotation_semantic_issues,
)
from app.services.capture_track_service import get_tracks_for_take
from app.services.storage_service import StorageService


class ScoringCalibrationError(ValueError):
    """可安全展示给 API 调用方的工作台错误。"""

    def __init__(self, message: str, *, code: str = "scoring_calibration_error") -> None:
        super().__init__(message)
        self.code = code


class ScoringCalibrationValidationError(ScoringCalibrationError):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        super().__init__("标注包未通过锁定校验", code="annotation_validation_failed")
        self.issues = issues


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _video_ids(db: Session, take: CaptureTake) -> list[str]:
    ids = [track.video_id for track in get_tracks_for_take(db, take.id) if track.video_id]
    if ids:
        return list(dict.fromkeys(ids))
    # Legacy takes may only reference the source recording session. Reuse the
    # same registered metadata path used by the CaptureTake detail endpoint.
    try:
        if take.source_session_type.value == "sync_recording":
            from app.camera.sync_recorder_service import sync_recording_service

            session = sync_recording_service.get_session(take.source_session_id)
            registered = getattr(session, "registered_video_ids", {}) if session else {}
            ids = [registered.get("cam_1"), registered.get("cam_2"), getattr(session, "default_analysis_video_id", None)]
        else:
            from app.camera.session_service import session_service

            session = session_service.get_session(take.source_session_id)
            ids = [getattr(session, "video_id", None)]
    except Exception:  # noqa: BLE001 - legacy metadata must not block the workbench
        ids = []
    return list(dict.fromkeys(str(value) for value in ids if value))


def _source_snapshot(db: Session, take: CaptureTake, source_job_id: str | None) -> dict:
    segments = (
        db.query(CaptureSegment)
        .filter(CaptureSegment.capture_take_id == take.id, CaptureSegment.edit_status != "superseded")
        .order_by(CaptureSegment.start_ms.asc())
        .all()
    )
    return {
        "capture_take_id": take.id,
        "capture_take_revision": take.revision,
        "video_ids": _video_ids(db, take),
        "duration_ms": take.duration_ms,
        "source_job_id": source_job_id,
        "segment_ids": [segment.id for segment in segments],
        "segment_revision": {segment.id: segment.edit_version for segment in segments},
    }


def _candidate_from_payload(
    payload: dict,
    *,
    source_job_id: str | None,
    candidate_type: str,
    artifact_name: str | None = None,
    detector_version: str | None = None,
    coverage_warning: str | None = None,
    coverage: dict | None = None,
) -> AnnotationCandidate | None:
    timestamp = payload.get("timestamp_ms")
    if timestamp is None:
        timestamp = payload.get("contact_ms", payload.get("start_ms"))
    if timestamp is None and payload.get("timestamp_seconds") is not None:
        timestamp = float(payload["timestamp_seconds"]) * 1000
    if timestamp is None:
        return None
    try:
        timestamp_ms = max(0, int(round(float(timestamp))))
    except (TypeError, ValueError):
        return None
    candidate_id = str(payload.get("candidate_id") or payload.get("id") or f"{candidate_type}:{timestamp_ms}")
    confidence = payload.get("confidence")
    if confidence is None:
        confidence = payload.get("score")
    try:
        confidence = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        confidence = None
    if confidence is not None:
        confidence = max(0.0, min(1.0, confidence))
    return AnnotationCandidate(
        candidate_id=candidate_id,
        candidate_type=candidate_type,
        source="algorithm",
        source_job_id=source_job_id,
        timestamp_ms=timestamp_ms,
        start_ms=_int_or_none(payload.get("start_ms")),
        end_ms=_int_or_none(payload.get("end_ms")),
        player_id=str(payload.get("player_id")) if payload.get("player_id") is not None else None,
        rally_id=str(payload.get("rally_id")) if payload.get("rally_id") is not None else None,
        confidence=confidence,
        payload=payload,
        artifact_name=artifact_name,
        detector_version=detector_version,
        coverage_warning=coverage_warning,
        coverage=coverage or {},
    )


def _int_or_none(value) -> int | None:
    try:
        return int(round(float(value))) if value is not None else None
    except (TypeError, ValueError):
        return None


def _load_persisted_candidates(
    db: Session,
    take: CaptureTake,
    source_job_id: str | None = None,
) -> list[AnnotationCandidate]:
    """从 CaptureTake 的落盘分析目录恢复候选，不依赖进程内 job registry。"""

    if not take.session_dir:
        return []
    analysis_root = Path(take.session_dir).expanduser() / "analysis"
    if not analysis_root.is_dir():
        return []
    allowed_video_ids = set(_video_ids(db, take))
    candidates: list[AnnotationCandidate] = []
    for job_dir in sorted(analysis_root.glob("job-*")):
        if not job_dir.is_dir():
            continue
        job_video_id = None
        result_path = job_dir / "result.json"
        if result_path.is_file():
            try:
                result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(result_payload, dict):
                    job_video_id = result_payload.get("video_id")
            except (OSError, TypeError, ValueError):
                pass
        path_specs = [
            ("serve_events.json", "serve", ("events",)),
            ("shot_rally_events.json", "shot", ("shots", "events", "candidates")),
            ("serve_debug_candidates.json", "serve", ("candidates",)),
        ]
        for filename, candidate_type, list_keys in path_specs:
            path = job_dir / filename
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue
            payload_job_id = str(payload.get("job_id") or "")
            if source_job_id and source_job_id not in {job_dir.name, payload_job_id}:
                continue
            file_video_id = payload.get("video_id") or job_video_id
            if file_video_id and allowed_video_ids and file_video_id not in allowed_video_ids:
                continue
            values = next((payload.get(key) for key in list_keys if isinstance(payload.get(key), list)), None)
            if not values:
                continue
            coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
            warning_values = coverage.get("warnings") or coverage.get("gaps") or []
            if isinstance(warning_values, list):
                coverage_warning = "；".join(str(value) for value in warning_values) or None
            else:
                coverage_warning = str(warning_values) if warning_values else None
            artifact_name = str(path.relative_to(analysis_root))
            for value in values:
                if not isinstance(value, dict):
                    continue
                candidate = _candidate_from_payload(
                    {**value, "video_id": file_video_id} if file_video_id else value,
                    source_job_id=str(job_dir.name),
                    candidate_type=candidate_type,
                    artifact_name=artifact_name,
                    detector_version=payload.get("detector_version"),
                    coverage_warning=coverage_warning,
                    coverage=coverage,
                )
                if candidate:
                    candidates.append(
                        candidate.model_copy(
                            update={"candidate_id": f"{job_dir.name}:{filename}:{candidate.candidate_id}"}
                        )
                    )
            # Prefer the canonical serve/shot artifact over its debug fallback.
            if candidates and filename != "serve_debug_candidates.json":
                break
    return candidates


def _load_algorithm_candidates(
    take_id: str,
    source_job_id: str | None = None,
    *,
    db: Session | None = None,
) -> list[AnnotationCandidate]:
    """从与 CaptureTake 关联的已完成分析任务中读取候选。

    AnalysisJob 目前由 JobStore 持久化而不是独立 SQL 表，因此适配器只读取
    已知任务和其 artifact；找不到任务时返回空列表，人工创建路径仍然可用。
    """

    candidates: list[AnnotationCandidate] = []
    try:
        from app.services.mock_analysis import JOBS

        jobs = list(JOBS.values())
    except Exception:  # noqa: BLE001 - candidate suggestions are optional
        jobs = []
    for job in jobs:
        metadata = getattr(job, "metadata", None)
        if getattr(metadata, "capture_take_id", None) != take_id:
            continue
        if source_job_id and job.id != source_job_id:
            continue
        storage = StorageService()
        root = storage.resolve_capture_job_root(job.id, take_id)
        if root is None:
            continue
        for path, candidate_type, list_key in (
            (storage.shot_rally_events_json_path(job.id), "shot", "shots"),
            (storage.serve_events_json_path(job.id), "serve", "events"),
        ):
            if not Path(path).exists():
                continue
            try:
                payload = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError):
                continue
            values = payload.get(list_key, []) if isinstance(payload, dict) else []
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                candidate = _candidate_from_payload(value, source_job_id=job.id, candidate_type=candidate_type)
                if candidate:
                    candidate_id = f"{job.id}:{candidate.candidate_id}"
                    candidates.append(candidate.model_copy(update={"candidate_id": candidate_id}))
    if db is not None:
        take = db.get(CaptureTake, take_id)
        if take is not None:
            candidates.extend(_load_persisted_candidates(db, take, source_job_id))
    unique: dict[str, AnnotationCandidate] = {}
    for candidate in candidates:
        unique[candidate.candidate_id] = candidate
    return sorted(unique.values(), key=lambda item: item.timestamp_ms)


def _annotation_record(annotation: ScoringCalibrationAnnotation) -> AnnotationRecord:
    return AnnotationRecord.model_validate(
        {
            "id": annotation.id,
            "package_revision_id": annotation.package_revision_id,
            "source": annotation.source,
            "candidate_id": annotation.candidate_id,
            "event_ms": annotation.event_ms,
            "evidence_start_ms": annotation.evidence_start_ms,
            "evidence_end_ms": annotation.evidence_end_ms,
            "video_id": annotation.video_id,
            "rally_segment_id": annotation.rally_segment_id,
            "player_id": annotation.player_id,
            "stage": annotation.stage,
            "opportunity_status": annotation.opportunity_status,
            "outcome": annotation.outcome,
            "landing_status": annotation.landing_status,
            "landing_zone": annotation.landing_zone,
            "confidence": annotation.confidence,
            "note": annotation.note,
            "decision": annotation.decision,
            "revoked": annotation.revoked,
            "created_at": annotation.created_at,
            "updated_at": annotation.updated_at,
        }
    )


def _quality(
    annotations: list[ScoringCalibrationAnnotation],
    candidates: list[AnnotationCandidate],
    issues: list[ValidationIssue],
) -> QualitySummary:
    active = [annotation for annotation in annotations if not annotation.revoked]
    confirmed = [annotation for annotation in active if annotation.decision in {"accepted", "corrected"}]
    unknown = [
        annotation
        for annotation in active
        if annotation.opportunity_status in {"unobservable", "unknown"}
        or annotation.outcome == "unknown"
        or annotation.landing_status == "unobservable"
    ]
    linked = {annotation.candidate_id for annotation in active if annotation.candidate_id}
    decisions = {candidate.candidate_id: candidate.decision for candidate in candidates}
    unmatched = [candidate for candidate in candidates if candidate.candidate_id not in linked and decisions.get(candidate.candidate_id) == "unreviewed"]
    complete = sum(1 for annotation in active if annotation.evidence_end_ms > annotation.evidence_start_ms)
    return QualitySummary(
        total_count=len(active),
        confirmed_count=len(confirmed),
        unknown_or_unobservable_count=len(unknown),
        unmatched_candidate_count=len(unmatched),
        conflict_count=sum(1 for issue in issues if issue.code in {"duplicate_serve", "semantic_conflict"}),
        evidence_complete_rate=(complete / len(active)) if active else 0,
        blocking_error_count=sum(1 for issue in issues if issue.severity == "error"),
        warning_count=sum(1 for issue in issues if issue.severity == "warning"),
    )


def _package_annotations(db: Session, package: ScoringCalibrationPackage) -> list[ScoringCalibrationAnnotation]:
    return (
        db.query(ScoringCalibrationAnnotation)
        .filter(
            ScoringCalibrationAnnotation.package_revision_id == package.id,
            ScoringCalibrationAnnotation.revoked.is_(False),
        )
        .order_by(ScoringCalibrationAnnotation.event_ms.asc())
        .all()
    )


def _candidate_source_info(
    db: Session,
    package: ScoringCalibrationPackage,
    candidates: list[AnnotationCandidate],
) -> dict[str, str | None]:
    take = db.get(CaptureTake, package.capture_take_id)
    if take is None or not take.session_dir:
        return {
            "candidate_status": "unavailable",
            "candidate_message": "CaptureTake 没有可读取的本地分析目录",
            "candidate_coverage_warning": None,
        }
    analysis_root = Path(take.session_dir).expanduser() / "analysis"
    if not analysis_root.is_dir():
        return {
            "candidate_status": "unavailable",
            "candidate_message": "本地分析目录不可用，仍可直接人工快速标注",
            "candidate_coverage_warning": None,
        }
    warnings = sorted({candidate.coverage_warning for candidate in candidates if candidate.coverage_warning})
    if candidates:
        return {
            "candidate_status": "available",
            "candidate_message": f"已读取 {len(candidates)} 条落盘候选，仅作为人工定位建议",
            "candidate_coverage_warning": "；".join(warnings) if warnings else None,
        }
    return {
        "candidate_status": "empty",
        "candidate_message": "分析目录存在，但没有与当前 CaptureTake 视频匹配的发球/击球候选；可直接人工快速标注",
        "candidate_coverage_warning": None,
    }


def _package_summary(db: Session, package: ScoringCalibrationPackage, *, include_candidates: bool = True):
    annotations = _package_annotations(db, package)
    issues = [ValidationIssue.model_validate(item) for item in _json_loads(package.validation_json, [])]
    candidates = _load_algorithm_candidates(package.capture_take_id, package.source_job_id, db=db) if include_candidates else []
    decisions = {
        row.candidate_id: row
        for row in db.query(ScoringCalibrationCandidateDecision)
        .filter(ScoringCalibrationCandidateDecision.package_revision_id == package.id)
        .all()
    }
    decorated = [
        candidate.model_copy(
            update={
                "decision": decisions[candidate.candidate_id].decision,
                "annotation_id": decisions[candidate.candidate_id].annotation_id,
            }
        )
        if candidate.candidate_id in decisions
        else candidate
        for candidate in candidates
    ]
    quality = QualitySummary.model_validate(_json_loads(package.quality_summary_json, {}))
    if not package.quality_summary_json or quality.total_count != len(annotations):
        quality = _quality(annotations, decorated, issues)
    candidate_info = _candidate_source_info(db, package, decorated) if include_candidates else {}
    return {
        "id": package.id,
        "package_id": package.package_id,
        "capture_take_id": package.capture_take_id,
        "revision": package.revision,
        "schema_version": package.schema_version,
        "status": package.status,
        "annotator": package.annotator,
        "note": package.note,
        "source_job_id": package.source_job_id,
        "supersedes_id": package.supersedes_id,
        "quality": quality,
        "validation_issues": issues,
        "annotations": [_annotation_record(annotation) for annotation in annotations],
        "candidates": decorated,
        **candidate_info,
        "created_at": package.created_at,
        "updated_at": package.updated_at,
        "locked_at": package.locked_at,
    }


def get_package(db: Session, revision_id: str) -> ScoringCalibrationPackage | None:
    return db.get(ScoringCalibrationPackage, revision_id)


def list_packages(db: Session, capture_take_id: str) -> list[dict]:
    packages = (
        db.query(ScoringCalibrationPackage)
        .filter(ScoringCalibrationPackage.capture_take_id == capture_take_id)
        .order_by(ScoringCalibrationPackage.revision.desc())
        .all()
    )
    return [_package_summary(db, package, include_candidates=False) for package in packages]


def create_package(db: Session, capture_take_id: str, request: AnnotationPackageCreateRequest) -> dict:
    take = db.get(CaptureTake, capture_take_id)
    if take is None:
        raise ScoringCalibrationError("CaptureTake 不存在", code="capture_take_not_found")
    videos = _video_ids(db, take)
    if not videos:
        raise ScoringCalibrationError("CaptureTake 没有可播放视频，请先注册原始比赛视频", code="capture_take_video_missing")
    package_id = _id("sca")
    package = ScoringCalibrationPackage(
        id=_id("scar"),
        package_id=package_id,
        capture_take_id=capture_take_id,
        revision=1,
        schema_version=SCORING_CALIBRATION_SCHEMA_VERSION,
        status=AnnotationPackageStatus.draft.value,
        annotator=request.annotator,
        note=request.note,
        source_job_id=request.source_job_id,
        source_snapshot_json=json.dumps(_source_snapshot(db, take, request.source_job_id), ensure_ascii=False),
        quality_summary_json=json.dumps(QualitySummary().model_dump(mode="json"), ensure_ascii=False),
        validation_json="[]",
    )
    db.add(package)
    db.flush()
    return _package_summary(db, package)


def create_revision(db: Session, package: ScoringCalibrationPackage, request: AnnotationPackageRevisionRequest) -> dict:
    if package.status != AnnotationPackageStatus.locked.value:
        raise ScoringCalibrationError("只有 locked 标注包可以创建修订版本", code="package_not_locked")
    latest = (
        db.query(ScoringCalibrationPackage)
        .filter(ScoringCalibrationPackage.package_id == package.package_id)
        .order_by(ScoringCalibrationPackage.revision.desc())
        .first()
    )
    revision = (latest.revision if latest else package.revision) + 1
    created = ScoringCalibrationPackage(
        id=_id("scar"),
        package_id=package.package_id,
        capture_take_id=package.capture_take_id,
        revision=revision,
        schema_version=package.schema_version,
        status=AnnotationPackageStatus.draft.value,
        annotator=request.annotator or package.annotator,
        note=request.note if request.note is not None else package.note,
        source_job_id=package.source_job_id,
        source_snapshot_json=package.source_snapshot_json,
        quality_summary_json="{}",
        validation_json="[]",
        supersedes_id=package.id,
    )
    db.add(created)
    db.flush()
    for old in _package_annotations(db, package):
        db.add(
            ScoringCalibrationAnnotation(
                id=_id("scaann"),
                package_revision_id=created.id,
                source=old.source,
                candidate_id=old.candidate_id,
                event_ms=old.event_ms,
                evidence_start_ms=old.evidence_start_ms,
                evidence_end_ms=old.evidence_end_ms,
                video_id=old.video_id,
                rally_segment_id=old.rally_segment_id,
                player_id=old.player_id,
                stage=old.stage,
                opportunity_status=old.opportunity_status,
                outcome=old.outcome,
                landing_status=old.landing_status,
                landing_zone=old.landing_zone,
                confidence=old.confidence,
                note=old.note,
                decision=old.decision,
            )
        )
    for old_decision in db.query(ScoringCalibrationCandidateDecision).filter(ScoringCalibrationCandidateDecision.package_revision_id == package.id).all():
        db.add(
            ScoringCalibrationCandidateDecision(
                id=_id("scadec"),
                package_revision_id=created.id,
                candidate_id=old_decision.candidate_id,
                candidate_type=old_decision.candidate_type,
                source=old_decision.source,
                source_job_id=old_decision.source_job_id,
                candidate_snapshot_json=old_decision.candidate_snapshot_json,
                decision=old_decision.decision,
                annotation_id=None,
            )
        )
    db.flush()
    return _package_summary(db, created)


def ensure_editable(package: ScoringCalibrationPackage) -> None:
    if package.status == AnnotationPackageStatus.locked.value:
        raise ScoringCalibrationError("locked 标注包只读，请先创建新的 revision", code="package_locked")


def create_annotation(db: Session, package: ScoringCalibrationPackage, request: AnnotationUpsertRequest) -> dict:
    ensure_editable(package)
    annotation = ScoringCalibrationAnnotation(
        id=_id("scaann"),
        package_revision_id=package.id,
        source=AnnotationSource.manual.value,
        candidate_id=request.candidate_id,
        event_ms=request.event_ms,
        evidence_start_ms=request.evidence_start_ms,
        evidence_end_ms=request.evidence_end_ms,
        video_id=request.video_id,
        rally_segment_id=request.rally_segment_id,
        player_id=request.player_id,
        stage=request.stage.value if request.stage else None,
        opportunity_status=request.opportunity_status.value if request.opportunity_status else None,
        outcome=request.outcome.value if request.outcome else None,
        landing_status=request.landing_status.value if request.landing_status else None,
        landing_zone=request.landing_zone.value if request.landing_zone else None,
        confidence=request.confidence,
        note=request.note,
        decision=request.decision.value,
    )
    db.add(annotation)
    db.flush()
    return _package_summary(db, package)


def update_annotation(db: Session, package: ScoringCalibrationPackage, annotation_id: str, request: AnnotationUpdateRequest) -> dict:
    ensure_editable(package)
    annotation = db.get(ScoringCalibrationAnnotation, annotation_id)
    if annotation is None or annotation.package_revision_id != package.id or annotation.revoked:
        raise ScoringCalibrationError("标注不存在", code="annotation_not_found")
    values = request.model_dump(exclude_unset=True)
    for key, value in values.items():
        if hasattr(annotation, key):
            setattr(annotation, key, value.value if hasattr(value, "value") else value)
    db.flush()
    return _package_summary(db, package)


def revoke_annotation(db: Session, package: ScoringCalibrationPackage, annotation_id: str) -> dict:
    ensure_editable(package)
    annotation = db.get(ScoringCalibrationAnnotation, annotation_id)
    if annotation is None or annotation.package_revision_id != package.id:
        raise ScoringCalibrationError("标注不存在", code="annotation_not_found")
    annotation.revoked = True
    db.flush()
    return _package_summary(db, package)


def decide_candidate(db: Session, package: ScoringCalibrationPackage, candidate_id: str, request: CandidateDecisionRequest) -> dict:
    ensure_editable(package)
    candidates = {candidate.candidate_id: candidate for candidate in _load_algorithm_candidates(package.capture_take_id, package.source_job_id, db=db)}
    candidate = candidates.get(candidate_id)
    if candidate is None:
        raise ScoringCalibrationError("算法候选不存在或已失效", code="candidate_not_found")
    row = (
        db.query(ScoringCalibrationCandidateDecision)
        .filter(
            ScoringCalibrationCandidateDecision.package_revision_id == package.id,
            ScoringCalibrationCandidateDecision.candidate_id == candidate_id,
        )
        .first()
    )
    if row is None:
        row = ScoringCalibrationCandidateDecision(
            id=_id("scadec"),
            package_revision_id=package.id,
            candidate_id=candidate_id,
            candidate_type=candidate.candidate_type,
            source=candidate.source,
            source_job_id=candidate.source_job_id,
            candidate_snapshot_json=json.dumps(candidate.payload, ensure_ascii=False),
        )
        db.add(row)
    row.decision = request.decision.value
    row.annotation_id = request.annotation_id
    db.flush()
    return _package_summary(db, package)


def validate_package(db: Session, package: ScoringCalibrationPackage) -> list[ValidationIssue]:
    take = db.get(CaptureTake, package.capture_take_id)
    duration_ms = take.duration_ms if take else None
    annotations = _package_annotations(db, package)
    issues: list[ValidationIssue] = []
    if take is None or not _video_ids(db, take):
        issues.append(ValidationIssue(code="capture_take_video_missing", message="CaptureTake 没有可播放视频"))
    for annotation in annotations:
        record = _annotation_record(annotation)
        if annotation.evidence_start_ms < 0 or annotation.evidence_end_ms < annotation.evidence_start_ms:
            issues.append(ValidationIssue(code="invalid_evidence_window", message="证据时间窗无效", annotation_id=annotation.id))
        if duration_ms is not None and annotation.evidence_end_ms > duration_ms:
            issues.append(ValidationIssue(code="evidence_out_of_range", message="证据时间窗超出视频范围", annotation_id=annotation.id))
        if annotation.event_ms < annotation.evidence_start_ms or annotation.event_ms > annotation.evidence_end_ms:
            issues.append(ValidationIssue(code="event_outside_evidence", message="事件时间必须位于证据时间窗内", annotation_id=annotation.id))
        missing = [
            name
            for name in ("stage", "opportunity_status", "outcome", "landing_status", "landing_zone")
            if getattr(annotation, name) is None
        ]
        if missing:
            issues.append(ValidationIssue(code="missing_required_fields", message=f"缺少必填标注字段: {', '.join(missing)}", annotation_id=annotation.id))
        issues.extend(annotation_semantic_issues(record))
        if annotation.decision == AnnotationDecision.unreviewed.value:
            issues.append(ValidationIssue(code="unreviewed_annotation", message="仍有标注未完成人工确认", annotation_id=annotation.id))
    serve_by_rally: dict[str, list[ScoringCalibrationAnnotation]] = {}
    for annotation in annotations:
        if annotation.stage == "serve" and annotation.rally_segment_id:
            serve_by_rally.setdefault(annotation.rally_segment_id, []).append(annotation)
    for rally_id, serves in serve_by_rally.items():
        serves.sort(key=lambda item: item.event_ms)
        for previous, current in zip(serves, serves[1:]):
            if current.event_ms - previous.event_ms <= 100:
                issues.append(ValidationIssue(code="duplicate_serve", message=f"同一回合存在疑似重复发球: {rally_id}", annotation_id=current.id))
    # Unobservable/unknown are valid warnings once the required explicit values exist.
    for annotation in annotations:
        if annotation.opportunity_status == "unobservable" or annotation.outcome == "unknown":
            issues.append(ValidationIssue(code="unobservable_fact", message="该条目包含不可观察或未知事实，不会自动视为失败", annotation_id=annotation.id, severity="warning"))
    return issues


def lock_package(db: Session, package: ScoringCalibrationPackage) -> dict:
    ensure_editable(package)
    issues = validate_package(db, package)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        package.validation_json = json.dumps([issue.model_dump(mode="json") for issue in issues], ensure_ascii=False)
        package.quality_summary_json = json.dumps(
            _quality(_package_annotations(db, package), _load_algorithm_candidates(package.capture_take_id, package.source_job_id, db=db), issues).model_dump(mode="json"),
            ensure_ascii=False,
        )
        db.flush()
        raise ScoringCalibrationValidationError(issues)
    annotations = _package_annotations(db, package)
    candidates = _load_algorithm_candidates(package.capture_take_id, package.source_job_id, db=db)
    quality = _quality(annotations, candidates, issues)
    package.status = AnnotationPackageStatus.locked.value
    package.locked_at = _utc_now()
    package.validation_json = json.dumps([issue.model_dump(mode="json") for issue in issues], ensure_ascii=False)
    package.quality_summary_json = json.dumps(quality.model_dump(mode="json"), ensure_ascii=False)
    artifact = {
        "schema_version": package.schema_version,
        "package_id": package.package_id,
        "revision": package.revision,
        "capture_take_id": package.capture_take_id,
        "status": package.status,
        "provenance": _json_loads(package.source_snapshot_json, {}),
        "annotations": [_annotation_record(annotation).model_dump(mode="json") for annotation in annotations],
        "quality": quality.model_dump(mode="json"),
        "validation_issues": [issue.model_dump(mode="json") for issue in issues],
    }
    package.artifact_json = json.dumps(artifact, ensure_ascii=False, indent=2, default=str)
    db.flush()
    return _package_summary(db, package)


def mark_reviewed(db: Session, package: ScoringCalibrationPackage) -> dict:
    ensure_editable(package)
    issues = validate_package(db, package)
    if any(issue.severity == "error" for issue in issues):
        package.validation_json = json.dumps([issue.model_dump(mode="json") for issue in issues], ensure_ascii=False)
        db.flush()
        raise ScoringCalibrationValidationError(issues)
    package.status = AnnotationPackageStatus.reviewed.value
    package.validation_json = json.dumps([issue.model_dump(mode="json") for issue in issues], ensure_ascii=False)
    package.quality_summary_json = json.dumps(
        _quality(_package_annotations(db, package), _load_algorithm_candidates(package.capture_take_id, package.source_job_id, db=db), issues).model_dump(mode="json"),
        ensure_ascii=False,
    )
    db.flush()
    return _package_summary(db, package)


def get_gold_set(db: Session, package: ScoringCalibrationPackage) -> GoldSetResponse:
    if package.status != AnnotationPackageStatus.locked.value:
        raise ScoringCalibrationError("只有 locked 标注包可以作为 Gold Set 使用", code="gold_set_not_ready")
    summary = _package_summary(db, package, include_candidates=False)
    return GoldSetResponse(
        schema_version=package.schema_version,
        package_id=package.package_id,
        revision=package.revision,
        capture_take_id=package.capture_take_id,
        status=package.status,
        provenance=_json_loads(package.source_snapshot_json, {}),
        annotations=summary["annotations"],
        quality=summary["quality"],
    )


def gold_set_status(db: Session, capture_take_id: str) -> dict:
    package = (
        db.query(ScoringCalibrationPackage)
        .filter(
            ScoringCalibrationPackage.capture_take_id == capture_take_id,
            ScoringCalibrationPackage.status == AnnotationPackageStatus.locked.value,
        )
        .order_by(ScoringCalibrationPackage.revision.desc())
        .first()
    )
    if package is None:
        return {
            "capture_take_id": capture_take_id,
            "status": "not_ready",
            "reason": "尚无可用校准真值，请先完成并锁定评分校准标注包",
        }
    return {
        "capture_take_id": capture_take_id,
        "status": "available",
        "package_id": package.package_id,
        "revision": package.revision,
        "schema_version": package.schema_version,
        "quality": _json_loads(package.quality_summary_json, {}),
    }
