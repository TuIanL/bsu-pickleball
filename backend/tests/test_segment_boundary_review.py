from __future__ import annotations

import json

from fastapi import HTTPException

from app.api import routes_segment_editing
from app.models.capture_segment import EditStatus
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
