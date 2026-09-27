from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import HTTPException

from app.api import routes_coding_actions, routes_segment_editing
from app.models.capture_segment import CaptureSegment, EditStatus, SegmentSource, SegmentStatus, SegmentType
from app.models.match_state_segmentation import MatchStateSegmentationRun, MatchStateSegmentationRunStatus
from app.models.segment_edit_operation import EditOperationType, SegmentEditOperation
from app.schemas.field_session import FieldSessionCreate
from app.schemas.segment_boundary_review import BoundaryReviewDecision, BoundaryReviewRequest
from app.schemas.segment_creation import RallyCreateRequest
from app.schemas.match_state_candidate import MatchStateCandidateDecisionRequest
from app.schemas.segment_ordinal import RallyOrdinalUpdateRequest
from app.services import capture_segment_service, match_state_candidate_service, segment_edit_service
from app.services.capture_take_service import create_capture_take
from app.services.field_session_service import create_field_session


def _take_and_rally(db):
    field_session = create_field_session(
        db,
        FieldSessionCreate(
            title="边界复核测试",
            venue="court",
            court_name="1",
            capture_mode="match",
            match_format="doubles",
            camera_setup="dual",
        ),
    )
    take = create_capture_take(
        db,
        field_session_id=field_session.id,
        capture_mode="dual",
        source_session_type="sync_recording",
        source_session_id="sync_boundary_review_test",
    )
    take.duration_ms = 20_000
    rally = capture_segment_service.create_segment(
        db,
        capture_take_id=take.id,
        segment_type="rally",
        ordinal=1,
        start_ms=2_000,
        label="第1分",
    )
    capture_segment_service.close_segment(db, rally, end_ms=8_000, status="closed")
    db.commit()
    return take, rally


def test_boundary_review_records_confirm_correct_and_exclude(isolated_database):
    db = isolated_database()
    take, rally = _take_and_rally(db)

    confirmed = routes_segment_editing.review_boundary(
        rally.id,
        BoundaryReviewRequest(decision="confirmed", expected_version=0),
        db,
    )
    assert confirmed["boundary_review_status"] == "confirmed"
    assert confirmed["effective_start_ms"] == 2_000
    assert confirmed["effective_end_ms"] == 8_000

    corrected = routes_segment_editing.review_boundary(
        rally.id,
        BoundaryReviewRequest(
            decision="corrected",
            expected_version=1,
            start_ms=2_250,
            end_ms=7_750,
            note="逐帧确认",
        ),
        db,
    )
    assert corrected["boundary_review_status"] == "corrected"
    assert corrected["boundary_review_note"] == "逐帧确认"
    assert corrected["effective_start_ms"] == 2_250
    assert corrected["effective_end_ms"] == 7_750

    excluded = routes_segment_editing.review_boundary(
        rally.id,
        BoundaryReviewRequest(decision="excluded", expected_version=2, note="不是有效回合"),
        db,
    )
    assert excluded["boundary_review_status"] == "excluded"
    assert excluded["edit_status"] == "archived"

    summary = routes_segment_editing.get_boundary_review(take.id, db)
    assert summary["total_count"] == 1
    assert summary["excluded_count"] == 1
    assert summary["pending_count"] == 0
    db.close()


def test_restored_exclusion_returns_to_pending(isolated_database):
    db = isolated_database()
    take, rally = _take_and_rally(db)
    legacy_archived = capture_segment_service.create_segment(
        db,
        capture_take_id=take.id,
        segment_type="rally",
        ordinal=2,
        start_ms=9_000,
        label="旧归档片段",
    )
    capture_segment_service.close_segment(db, legacy_archived, end_ms=12_000, status="closed")
    segment_edit_service.archive_segment(db, legacy_archived)
    segment_edit_service.review_rally_boundary(
        db,
        rally,
        decision=BoundaryReviewDecision.excluded,
        expected_version=0,
        note="暂时排除",
        take_duration_ms=take.duration_ms,
    )
    segment_edit_service.restore_segment(db, rally)
    db.commit()

    summary = routes_segment_editing.get_boundary_review(take.id, db)
    assert summary["total_count"] == 1
    assert summary["pending_count"] == 1
    assert summary["segments"][0]["boundary_review_status"] == "pending"
    assert rally.edit_status == EditStatus.active
    db.close()


def test_near_duplicate_annotation_version_is_suppressed(isolated_database):
    db = isolated_database()
    take, rally = _take_and_rally(db)
    imported_duplicate = capture_segment_service.create_segment(
        db,
        capture_take_id=take.id,
        segment_type="rally",
        ordinal=1,
        start_ms=2_006,
        label="导入版本第1分",
        source="vidat_import",
    )
    capture_segment_service.close_segment(db, imported_duplicate, end_ms=8_007, status="closed")
    db.commit()

    summary = routes_segment_editing.get_boundary_review(take.id, db)
    assert summary["total_count"] == 1
    assert summary["suppressed_duplicate_count"] == 1
    assert summary["suppressed_duplicate_segment_ids"] == [imported_duplicate.id]
    assert summary["segments"][0]["id"] == rally.id
    db.close()


def test_create_manual_rally_inserts_by_time_and_audits(isolated_database):
    db = isolated_database()
    take, rally = _take_and_rally(db)

    created = routes_segment_editing.create_rally_segment(
        take.id,
        RallyCreateRequest(start_ms=9_000, end_ms=12_000),
        db,
    )
    assert created["segment_type"] == "rally"
    assert created["source"] == "manual"
    assert created["status"] == "closed"
    assert created["ordinal"] == 2
    assert created["effective_start_ms"] == 9_000
    assert created["effective_end_ms"] == 12_000
    assert created["created_by_operation_id"]

    operation = db.query(SegmentEditOperation).filter(
        SegmentEditOperation.id == created["created_by_operation_id"],
    ).one()
    assert operation.operation_type == EditOperationType.create
    assert rally.ordinal == 1

    inserted_before = routes_segment_editing.create_rally_segment(
        take.id,
        RallyCreateRequest(start_ms=1_000, end_ms=1_800),
        db,
    )
    assert inserted_before["ordinal"] == 1
    assert rally.ordinal == 2
    assert rally.label == "第2分"

    try:
        routes_segment_editing.create_rally_segment(
            take.id,
            RallyCreateRequest(start_ms=1_500, end_ms=2_500),
            db,
        )
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "重叠" in str(exc.detail)
    else:
        raise AssertionError("重叠的新增回合应该被拒绝")

    summary = routes_segment_editing.get_boundary_review(take.id, db)
    assert summary["total_count"] == 3
    assert summary["pending_count"] == 3
    db.close()


def test_formal_segmentation_summary_exposes_only_published_algorithm_run(isolated_database):
    db = isolated_database()
    take, _ = _take_and_rally(db)
    run = MatchStateSegmentationRun(
        id="seg-summary",
        capture_take_id=take.id,
        planning_job_id="job-summary",
        status=MatchStateSegmentationRunStatus.succeeded,
        profile="match_default",
        model_package_id="match-state",
        model_package_version="v2026.09",
        window_plan_hash="plan-summary",
        segment_count=1,
    )
    db.add(run)
    db.flush()
    db.add(
        CaptureSegment(
            id="auto-summary",
            capture_take_id=take.id,
            segment_type=SegmentType.rally,
            ordinal=1,
            label="第1分",
            start_ms=1000,
            end_ms=2000,
            status=SegmentStatus.inferred,
            source=SegmentSource.algorithm,
            edit_status=EditStatus.active,
            segmentation_run_id=run.id,
        )
    )
    db.commit()

    summary = routes_segment_editing.get_formal_segmentation_summary(take.id, db)
    assert summary["status"] == "succeeded"
    assert summary["model_version"] == "v2026.09"
    assert summary["segment_count"] == 1
    assert summary["window_plan_hash"] == "plan-summary"
    db.close()


def _algorithm_segment(db, take_id: str, run_id: str) -> CaptureSegment:
    segment = CaptureSegment(
        id=f"auto-{run_id}",
        capture_take_id=take_id,
        segment_type=SegmentType.rally,
        ordinal=1,
        label="第1分",
        start_ms=1000,
        end_ms=2000,
        status=SegmentStatus.inferred,
        source=SegmentSource.algorithm,
        edit_status=EditStatus.active,
        segmentation_run_id=run_id,
    )
    db.add(segment)
    db.flush()
    return segment


def test_formal_segmentation_summary_keeps_latest_published_run_over_failed_retry(isolated_database):
    """失败重试不得顶掉上一次成功发布，且失败记录本身仍可审计。"""
    db = isolated_database()
    take, _ = _take_and_rally(db)
    published = MatchStateSegmentationRun(
        id="seg-published",
        capture_take_id=take.id,
        planning_job_id="job-published",
        status=MatchStateSegmentationRunStatus.succeeded,
        profile="match_default",
        window_plan_hash="plan-published",
        finished_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    failed = MatchStateSegmentationRun(
        id="seg-failed-retry",
        capture_take_id=take.id,
        planning_job_id="job-failed-retry",
        status=MatchStateSegmentationRunStatus.inference_failed,
        profile="match_default",
        diagnostics_json=json.dumps({"detail": "模型权重缺失"}, ensure_ascii=False),
        finished_at=datetime(2026, 9, 2, tzinfo=UTC),
    )
    db.add_all([published, failed])
    db.flush()
    _algorithm_segment(db, take.id, published.id)
    db.commit()

    summary = routes_segment_editing.get_formal_segmentation_summary(take.id, db)
    assert summary["run_id"] == "seg-published"
    assert summary["status"] == "succeeded"
    assert summary["segment_count"] == 1
    # 失败重试不 supersede 已发布 run：两条记录各自保留原状态，供审计追溯。
    assert published.status is MatchStateSegmentationRunStatus.succeeded
    assert db.get(MatchStateSegmentationRun, "seg-failed-retry").status is (
        MatchStateSegmentationRunStatus.inference_failed
    )
    db.close()


def test_formal_segmentation_summary_treats_valid_no_rallies_as_published(isolated_database):
    """valid_no_rallies 属于已发布状态：摘要照常返回该 run，但分段计数为 0。"""
    db = isolated_database()
    take, _ = _take_and_rally(db)
    db.add(
        MatchStateSegmentationRun(
            id="seg-valid-empty",
            capture_take_id=take.id,
            planning_job_id="job-valid-empty",
            status=MatchStateSegmentationRunStatus.valid_no_rallies,
            profile="match_default",
            window_plan_hash="plan-valid-empty",
            finished_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
    )
    db.commit()

    summary = routes_segment_editing.get_formal_segmentation_summary(take.id, db)
    assert summary["run_id"] == "seg-valid-empty"
    assert summary["status"] == "valid_no_rallies"
    assert summary["segment_count"] == 0
    db.close()


def test_segment_list_and_edit_routes_share_one_serializer(isolated_database):
    """片段列表路由与片段编辑路由输出同一份字典契约（共享序列化模块）。"""
    db = isolated_database()
    take, rally = _take_and_rally(db)

    listed = next(item for item in routes_coding_actions.list_segments(take.id, db=db) if item["id"] == rally.id)
    edited = routes_segment_editing.patch_segment(
        rally.id,
        corrected_start_ms=2_400,
        corrected_end_ms=7_600,
        expected_version=0,
        db=db,
    )

    assert set(listed) == set(edited)
    # 本次编辑真正改动的字段之外，两侧取值必须逐字一致。
    mutated = {"corrected_start_ms", "corrected_end_ms", "corrected_at", "edit_version", "effective_start_ms", "effective_end_ms"}
    assert {k: v for k, v in listed.items() if k not in mutated} == {
        k: v for k, v in edited.items() if k not in mutated
    }
    assert listed["effective_start_ms"] == 2_000
    assert edited["effective_start_ms"] == 2_400
    assert edited["effective_end_ms"] == 7_600
    db.close()


def test_accept_model_candidate_creates_manual_rally_and_versioned_review(isolated_database, tmp_path):
    db = isolated_database()
    take, _ = _take_and_rally(db)
    artifact = {
        "schema_version": "match_state_candidate_timeline.v1",
        "capture_take_id": take.id,
        "source_session_id": take.source_session_id,
        "model": {"package_id": "pkg_test", "model_version": "fusion_v1"},
        "source_provenance": {"dataset_manifest_sha256": "a" * 64},
        "decoder": {"minimum_confidence": 0.6},
        "candidate_segments": [
            {
                "candidate_id": "candidate_0001",
                "start_ms": 9_000,
                "end_ms": 12_000,
                "confidence": 0.92,
                "status": "unreviewed",
            }
        ],
    }
    (tmp_path / f"{take.id}.timeline.json").write_text(json.dumps(artifact), encoding="utf-8")

    record, segment = match_state_candidate_service.decide_candidate(
        db,
        root=tmp_path,
        capture_take_id=take.id,
        candidate_id="candidate_0001",
        request=MatchStateCandidateDecisionRequest(decision="accepted", expected_revision=0),
        take_duration_ms=take.duration_ms,
    )
    db.commit()

    assert segment is not None
    assert segment.source.value == "manual"
    assert record["decision"] == "accepted"
    assert record["output_segment_id"] == segment.id
    match_state_candidate_service.export_review_record(tmp_path, take.id, record)
    sidecar = json.loads((tmp_path / f"{take.id}.reviews.json").read_text(encoding="utf-8"))
    assert sidecar["revision"] == 1
    assert sidecar["history"][0]["provenance"]["model"]["package_id"] == "pkg_test"
    operation = db.query(SegmentEditOperation).filter(SegmentEditOperation.id == segment.created_by_operation_id).one()
    assert "candidate_0001" in operation.payload_json
    db.close()


def test_renumber_rally_ordinals_from_anchor_and_whole_take_audits(isolated_database):
    db = isolated_database()
    take, first = _take_and_rally(db)
    second = capture_segment_service.create_segment(
        db,
        capture_take_id=take.id,
        segment_type="rally",
        ordinal=1,
        start_ms=9_000,
        label="第1分",
    )
    capture_segment_service.close_segment(db, second, end_ms=12_000, status="closed")
    third = capture_segment_service.create_segment(
        db,
        capture_take_id=take.id,
        segment_type="rally",
        ordinal=2,
        start_ms=13_000,
        label="自定义标签",
    )
    capture_segment_service.close_segment(db, third, end_ms=15_000, status="closed")
    db.commit()

    result = routes_segment_editing.update_rally_ordinals(
        take.id,
        RallyOrdinalUpdateRequest(
            mode="from_anchor",
            anchor_segment_id=second.id,
            start_ordinal=2,
        ),
        db,
    )
    assert result["operation_id"]
    assert [item["ordinal"] for item in result["segments"]] == [1, 2, 3]
    assert first.ordinal == 1
    assert second.ordinal == 2
    assert second.label == "第2分"
    assert third.ordinal == 3
    assert third.label == "自定义标签"
    assert (first.start_ms, first.end_ms) == (2_000, 8_000)
    assert (second.start_ms, second.end_ms) == (9_000, 12_000)
    assert (third.start_ms, third.end_ms) == (13_000, 15_000)

    operation = db.query(SegmentEditOperation).filter(
        SegmentEditOperation.id == result["operation_id"],
    ).one()
    assert operation.operation_type == EditOperationType.ordinal_renumber
    assert '"mode": "from_anchor"' in operation.payload_json

    # 模拟另一次错误的关键事件重编号，然后验证整段视频可从第 1 分统一恢复。
    first.ordinal = 8
    first.label = "第8分"
    db.commit()
    whole = routes_segment_editing.update_rally_ordinals(
        take.id,
        RallyOrdinalUpdateRequest(mode="whole_take", start_ordinal=1),
        db,
    )
    assert whole["operation_id"]
    assert [item["ordinal"] for item in whole["segments"]] == [1, 2, 3]
    assert first.ordinal == 1
    assert first.label == "第1分"
    assert third.label == "自定义标签"
    db.close()
