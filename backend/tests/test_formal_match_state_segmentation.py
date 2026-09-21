from __future__ import annotations

import hashlib
import json

import pytest

from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
from app.models.capture_take import CaptureMode, CaptureTake, CaptureTakeStatus, SourceSessionType
from app.models.field_session import CaptureMode as FieldCaptureMode, FieldSession, FieldSessionStatus, MatchFormat
from app.models.match_state_segmentation import MatchStateSegmentationRun, MatchStateSegmentationRunStatus
from app.core.config import Settings
from app.services.formal_segmentation_service import persist_segmentation_result
from app.services.job_orchestration import JobStore
from app.services.multiview_coordinator import MultiViewAnalysisCoordinator
from app.services.storage_service import StorageService
from app.vision.match_state import (
    MatchStateSegmentationRuntime,
    MatchStateSynchronizedSampler,
    SegmentationInput,
    build_segmentation_artifact,
    decode_state_timeline_result,
)
from app.vision.match_state.package import ModelPackageCache, ModelPackageError, load_production_package
from app.services.frame_timing_provider import FrameTimingProvider


def _write_package(root):
    weights = root / "model.pt"
    weights.write_bytes(b"formal-test-weights")
    manifest = {
        "schema_version": "match_state_model_package.v1",
        "package_id": "formal-test-package",
        "model_name": "formal-test-model",
        "model_version": "v1",
        "task": "match_state_temporal_segmentation",
        "classes": ["rally_active", "non_play", "unknown"],
        "input_contract": {"modalities": ["rgb"], "sampling_fps": 2.0},
        "thresholds": {
            "minimum_confidence": 0.65,
            "minimum_coverage": 0.75,
            "minimum_duration_ms": 500,
            "hysteresis": 0.1,
        },
        "profiles": ["match_default"],
        "artifacts": {
            "weights": "model.pt",
            "checksums": {
                "model.pt": {"sha256": hashlib.sha256(weights.read_bytes()).hexdigest()}
            },
        },
    }
    (root / "model_package.json").write_text(json.dumps(manifest), encoding="utf-8")


def _probability_samples():
    return tuple(
        {
            "center_ms": center,
            "state_probabilities": {"rally_active": active, "non_play": 1 - active, "unknown": 0.0},
            "coverage": 1.0,
        }
        for center, active in ((0, 0.9), (500, 0.8), (1000, 0.4), (1500, 0.3))
    )


def test_formal_decoder_matches_candidate_decoder_and_runtime_artifact(tmp_path):
    samples = _probability_samples()
    formal = decode_state_timeline_result(samples)
    from scripts.match_state_timeline import decode_state_timeline as candidate_decoder

    candidate = candidate_decoder(list(samples))
    assert formal == candidate

    package_dir = tmp_path / "package"
    package_dir.mkdir()
    _write_package(package_dir)
    result = MatchStateSegmentationRuntime().run(
        SegmentationInput(
            capture_take_id="take-formal",
            planning_job_id="job-formal",
            samples=samples,
            input_fingerprint="input-1",
            sync_calibration_revision=3,
            timing_authority="source_pts",
        ),
        package_dir=str(package_dir),
    )
    assert result.status == "succeeded"
    assert result.artifact is not None
    assert result.artifact.window_plan.windows[0]["start_ms"] == 0
    assert result.artifact.state_timeline[0]["state"] == "rally_active"


def test_sampler_applies_sync_rate_and_rejects_missing_revision():
    reference = FrameTimingProvider.nominal(frame_count=50, fps=10.0)
    secondary = FrameTimingProvider.nominal(frame_count=50, fps=10.0)
    sampler = MatchStateSynchronizedSampler(
        reference,
        secondary,
        sync_calibration_revision=7,
        secondary_offset_ms=100,
        secondary_rate=1.1,
        max_gap_ms=60,
    )
    samples = sampler.sample(start_ms=0, end_ms=3000, stride_ms=1000)
    assert samples[0].secondary_frame == 1
    assert samples[1].secondary_frame == 12
    assert samples[2].secondary_frame == 23
    assert all(item.sync_calibration_revision == 7 for item in samples)
    with pytest.raises(ValueError, match="revision"):
        MatchStateSynchronizedSampler(reference, secondary, sync_calibration_revision=None)


def test_runtime_classifies_model_and_input_failures(tmp_path):
    source = SegmentationInput(
        capture_take_id="take-failure",
        planning_job_id="job-failure",
        samples=({"center_ms": 0, "coverage": 1.0},),
        input_fingerprint="input-1",
        sync_calibration_revision=1,
        timing_authority="source_pts",
    )
    missing_package = MatchStateSegmentationRuntime().run(source, package_dir=str(tmp_path / "missing"))
    assert missing_package.status == "model_unavailable"
    no_sync = MatchStateSegmentationRuntime().run(
        source.__class__(**{**source.__dict__, "sync_calibration_revision": None}),
        package_dir=str(tmp_path / "missing"),
    )
    assert no_sync.status == "sync_unavailable"


def test_runtime_classifies_low_evidence_and_valid_empty_plan(tmp_path):
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    _write_package(package_dir)
    low_evidence = MatchStateSegmentationRuntime().run(
        SegmentationInput(
            capture_take_id="take-low",
            planning_job_id="job-low",
            samples=_probability_samples(),
            input_fingerprint="input-low",
            sync_calibration_revision=1,
            timing_authority="source_pts",
            coverage=0.5,
        ),
        package_dir=str(package_dir),
    )
    assert low_evidence.status == "low_evidence"

    empty = MatchStateSegmentationRuntime().run(
        SegmentationInput(
            capture_take_id="take-empty",
            planning_job_id="job-empty",
            samples=tuple(
                {
                    "center_ms": center,
                    "state_probabilities": {"rally_active": 0.1, "non_play": 0.9, "unknown": 0.0},
                    "coverage": 1.0,
                }
                for center in (0, 500, 1000)
            ),
            input_fingerprint="input-empty",
            sync_calibration_revision=1,
            timing_authority="source_pts",
        ),
        package_dir=str(package_dir),
    )
    assert empty.status == "valid_no_rallies"
    assert empty.artifact is not None
    assert empty.artifact.window_plan.windows == ()


def test_model_package_checksum_and_cache_are_stable(tmp_path):
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    _write_package(package_dir)
    package = load_production_package(package_dir)
    calls = []
    cache = ModelPackageCache(loader=lambda _package, device: calls.append(device) or object())
    first = cache.get(package, "cpu")
    second = cache.get(package, "cpu")
    assert first is second
    assert calls == ["cpu"]

    (package_dir / "model.pt").write_bytes(b"tampered")
    with pytest.raises(ModelPackageError, match="SHA-256"):
        load_production_package(package_dir)


def _create_take(db, tmp_path, take_id="take-publish"):
    db.add(
        FieldSession(
            id="field-publish",
            title="publish",
            capture_mode=FieldCaptureMode.match,
            match_format=MatchFormat.doubles,
            status=FieldSessionStatus.completed,
        )
    )
    db.add(
        CaptureTake(
            id=take_id,
            field_session_id="field-publish",
            capture_mode=CaptureMode.dual,
            source_session_type=SourceSessionType.sync_recording,
            source_session_id=f"source-{take_id}",
            session_dir=str(tmp_path / "take"),
            status=CaptureTakeStatus.completed,
        )
    )
    db.flush()


def test_publish_supersedes_only_previous_algorithm_and_keeps_manual(isolated_database, tmp_path):
    db = isolated_database()
    _create_take(db, tmp_path)
    db.add(
        MatchStateSegmentationRun(
            id="run-old",
            capture_take_id="take-publish",
            planning_job_id="job-old",
            status=MatchStateSegmentationRunStatus.succeeded,
            profile="match_default",
        )
    )
    db.add_all(
        [
            CaptureSegment(
                id="manual-1",
                capture_take_id="take-publish",
                segment_type=SegmentType.rally,
                ordinal=1,
                label="人工标记",
                start_ms=10,
                end_ms=100,
                status=SegmentStatus.closed,
                source=SegmentSource.manual,
                edit_status=EditStatus.active,
            ),
            CaptureSegment(
                id="auto-old",
                capture_take_id="take-publish",
                segment_type=SegmentType.rally,
                ordinal=1,
                label="旧自动",
                start_ms=0,
                end_ms=500,
                status=SegmentStatus.inferred,
                source=SegmentSource.algorithm,
                edit_status=EditStatus.active,
                segmentation_run_id="run-old",
            ),
        ]
    )
    db.commit()
    storage = StorageService()
    StorageService.register_capture_job("job-new", tmp_path / "take")
    artifact = build_segmentation_artifact(
        planning_job_id="job-new",
        capture_take_id="take-publish",
        run_id="run-new",
        status="succeeded",
        model={"package_id": "pkg", "model_version": "v1", "profile": "match_default"},
        input_provenance={"input_fingerprint": "input", "sync_calibration_revision": 1},
        decoder={},
        state_summary={"unknown_rate": 0.0},
        segments=({"segment_id": "auto-new", "ordinal": 1, "start_ms": 600, "end_ms": 1200},),
    )
    persist_segmentation_result(db, artifact=artifact, storage=storage)
    db.commit()
    db.expire_all()
    assert db.get(CaptureSegment, "manual-1").edit_status == EditStatus.active
    assert db.get(CaptureSegment, "auto-old").edit_status == EditStatus.superseded
    assert db.get(CaptureSegment, "auto-new").source == SegmentSource.algorithm
    assert db.get(CaptureSegment, "auto-new").status == SegmentStatus.inferred
    assert db.get(MatchStateSegmentationRun, "run-new").window_plan_hash == artifact.window_plan.plan_hash
    assert storage.formal_segmentation_artifact_path("job-new", "take-publish", create_root=False).is_file()


def test_publish_failure_can_roll_back_without_touching_previous_run(isolated_database, tmp_path, monkeypatch):
    db = isolated_database()
    _create_take(db, tmp_path, take_id="take-rollback")
    db.add(
        MatchStateSegmentationRun(
            id="run-rollback-old",
            capture_take_id="take-rollback",
            planning_job_id="job-old",
            status=MatchStateSegmentationRunStatus.succeeded,
            profile="match_default",
        )
    )
    db.add(
        CaptureSegment(
            id="auto-rollback-old",
            capture_take_id="take-rollback",
            segment_type=SegmentType.rally,
            ordinal=1,
            label="旧自动",
            start_ms=0,
            end_ms=500,
            status=SegmentStatus.inferred,
            source=SegmentSource.algorithm,
            edit_status=EditStatus.active,
            segmentation_run_id="run-rollback-old",
        )
    )
    db.commit()
    storage = StorageService()
    StorageService.register_capture_job("job-rollback-new", tmp_path / "take")
    artifact = build_segmentation_artifact(
        planning_job_id="job-rollback-new",
        capture_take_id="take-rollback",
        run_id="run-rollback-new",
        status="succeeded",
        model={"package_id": "pkg", "model_version": "v1", "profile": "match_default"},
        input_provenance={"input_fingerprint": "input", "sync_calibration_revision": 1},
        decoder={},
        state_summary={"unknown_rate": 0.0},
        segments=({"segment_id": "auto-rollback-new", "ordinal": 1, "start_ms": 600, "end_ms": 1200},),
    )
    monkeypatch.setattr(storage, "write_json_atomic", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        persist_segmentation_result(db, artifact=artifact, storage=storage)
    db.rollback()
    assert db.get(MatchStateSegmentationRun, "run-rollback-new") is None
    assert db.get(MatchStateSegmentationRun, "run-rollback-old").status == MatchStateSegmentationRunStatus.succeeded
    assert db.get(CaptureSegment, "auto-rollback-old").edit_status == EditStatus.active


def test_legacy_job_and_manual_segment_remain_readable_after_schema_extension(isolated_database, tmp_path):
    db = isolated_database()
    _create_take(db, tmp_path, take_id="take-legacy")
    db.add(
        CaptureSegment(
            id="manual-legacy",
            capture_take_id="take-legacy",
            segment_type=SegmentType.rally,
            ordinal=1,
            label="现场标记",
            start_ms=100,
            end_ms=900,
            status=SegmentStatus.closed,
            source=SegmentSource.manual,
            edit_status=EditStatus.active,
        )
    )
    db.commit()
    db.expire_all()
    segment = db.get(CaptureSegment, "manual-legacy")
    assert segment is not None
    assert segment.segmentation_run_id is None

    from app.schemas.analysis import AnalysisJobSummary

    legacy_payload = {
        "id": "legacy-job",
        "status": "completed",
        "canonicalStatus": "succeeded",
        "displayStatus": "completed",
        "stage": "report",
        "progress": 100,
        "createdAt": "2026-09-09T00:00:00+00:00",
        "updatedAt": "2026-09-09T00:00:00+00:00",
        "metadata": {
            "fileName": "legacy.mp4",
            "matchTitle": "legacy",
            "venue": "court",
            "matchDate": "2026-09-09",
            "matchFormat": "singles",
            "cameraAngle": "baseline",
            "athleteLabel": "athlete",
            "level": "test",
        },
        "stages": [],
    }
    legacy_job = AnalysisJobSummary.model_validate(legacy_payload)
    assert legacy_job.analysisKind == "single_view"
    assert legacy_job.visibility == "public"
    assert legacy_job.orchestrationStatus == "none"
    assert legacy_job.jobRole == "analysis"
    assert legacy_job.segmentationRequired is False


def _formal_payload():
    from app.schemas.analysis import (
        AnalysisJobCreate,
        AnalysisUploadMetadata,
        MultiViewCreateRequest,
        MultiViewViewPayload,
    )

    metadata = AnalysisUploadMetadata(
        fileName="dual.mp4",
        matchTitle="formal",
        venue="court",
        matchDate="2026-09-09",
        matchFormat="doubles",
        cameraAngle="baseline",
        athleteLabel="athletes",
        level="test",
        capture_take_id="CT_FORMAL",
    )
    return AnalysisJobCreate(
        metadata=metadata,
        analysisKind="multiview",
        segmentationRequired=True,
        multiview=MultiViewCreateRequest(
            referenceViewId="cam_1",
            views=[
                MultiViewViewPayload(
                    viewId="cam_1", videoId="v1", calibrationId="cal1", courtOrientation="identity"
                ),
                MultiViewViewPayload(
                    viewId="cam_2", videoId="v2", calibrationId="cal2", courtOrientation="rotate_180"
                ),
            ],
            executionMode="late_fusion_v1",
        ),
    )


def _patched_coordinator(monkeypatch, tmp_path):
    import app.services.multiview_coordinator as mc

    # 每个编排用例使用独立的持久化目录；签名去重现在是有意跨调用
    # 生效的，不能让不同测试共享默认 jobs 目录而互相复用 Parent。
    storage = StorageService(
        Settings(
            uploads_dir=tmp_path / "uploads",
            outputs_dir=tmp_path / "outputs",
            calibrations_dir=tmp_path / "calibrations",
            tmp_dir=tmp_path / "tmp",
        )
    )
    monkeypatch.setattr(mc, "preflight_multiview", lambda payload, **kwargs: mc.PreflightResult(ok=True))
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda _take_id: str(tmp_path / "take"))
    (tmp_path / "take").mkdir()
    return MultiViewAnalysisCoordinator(JobStore(storage), storage=storage)


def test_formal_late_fusion_waits_for_segmentation_and_is_idempotent(monkeypatch, tmp_path):
    coordinator = _patched_coordinator(monkeypatch, tmp_path)
    parent = coordinator.create_multiview_job(_formal_payload())
    assert parent.orchestrationStatus == "waiting_segmentation"
    prerequisite = coordinator.store.get(parent.segmentationPrerequisiteJobId)
    coordinator.store.update(
        prerequisite.id,
        canonicalStatus="succeeded",
        status="completed",
        segmentationStatus="valid_no_rallies",
    )
    coordinator.store.update(
        parent.id,
        segmentationStatus="valid_no_rallies",
        segmentationRunId="seg-valid-empty",
        windowPlanHash="plan-empty",
    )
    coordinator.on_job_terminal(coordinator.store.get(prerequisite.id))
    updated = coordinator.store.get(parent.id)
    assert updated.orchestrationStatus == "waiting_sources"
    assert len(updated.sourceJobs) == 2
    assert all(ref.jobId for ref in updated.sourceJobs)
    coordinator.on_job_terminal(coordinator.store.get(prerequisite.id))
    assert len(coordinator.store.get(parent.id).sourceJobs) == 2


def test_formal_segmentation_failure_fails_parent_without_children(monkeypatch, tmp_path):
    coordinator = _patched_coordinator(monkeypatch, tmp_path)
    parent = coordinator.create_multiview_job(_formal_payload())
    prerequisite = coordinator.store.get(parent.segmentationPrerequisiteJobId)
    coordinator.store.update(
        prerequisite.id,
        canonicalStatus="failed",
        status="failed",
        errorCode="model_unavailable",
        publicErrorMessage="模型包不可用",
    )
    coordinator.on_job_terminal(coordinator.store.get(prerequisite.id))
    updated = coordinator.store.get(parent.id)
    assert updated.canonicalStatus == "failed"
    assert updated.segmentationPrerequisiteJobId == prerequisite.id
    assert updated.sourceJobs == []


def test_formal_segmentation_cancel_cascades_to_prerequisite_without_children(monkeypatch, tmp_path):
    coordinator = _patched_coordinator(monkeypatch, tmp_path)
    parent = coordinator.create_multiview_job(_formal_payload())
    prerequisite = coordinator.store.get(parent.segmentationPrerequisiteJobId)
    canceled, outcome = coordinator.store.cancel(parent.id)
    assert outcome == "canceled"
    coordinator.cancel_cascade(canceled)
    assert coordinator.store.get(prerequisite.id).canonicalStatus == "canceled"
    assert coordinator.store.get(parent.id).sourceJobs == []
