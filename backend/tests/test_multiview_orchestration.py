"""多视角编排（multiview orchestration）测试 —— P0.5 接线契约。

覆盖：
- AnalysisJob 编排字段缺省兼容（历史 job 读取）；
- `is_runnable()` / `claim_next()`：waiting_sources Parent 不可 claim，fusion_ready 可 claim；
- Coordinator 创建 public Parent + 2 dedicated internal child（不跨 Parent 复用）；
- 编排推进（child terminal → fusion_ready / fallback_ready / failed）与启动对账；
- 取消/删除级联语义；
- MultiView preflight 各失败分支（不静默退化）；
- `select_trajectory_source()` 含 unavailable；
- Composer 重算 fused 指标 + 发布 Parent 命名空间 + manifest 唯一出口。
"""

from __future__ import annotations

import json

import pytest

from app.schemas.analysis import (
    AnalysisJobCreate,
    AnalysisJobSummary,
    AnalysisUploadMetadata,
    MultiViewCreateRequest,
    MultiViewViewPayload,
    build_match_context,
)
from app.schemas.metrics import PerformanceMetrics
from app.services.job_orchestration import JobStore
from app.services.storage_service import StorageService
from app.services.video_service import video_service
from app.vision.multiview.consumers import select_trajectory_source


def make_temp_storage(tmp_path) -> StorageService:
    from app.core.config import Settings

    settings = Settings(
        uploads_dir=tmp_path / "uploads",
        outputs_dir=tmp_path / "outputs",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    return StorageService(settings)


def make_metadata(**overrides) -> AnalysisUploadMetadata:
    fields = {
        "fileName": "dual.mp4",
        "matchTitle": "世园比赛",
        "venue": "世园国际匹克球中心",
        "matchDate": "2026-08-07",
        "matchFormat": "doubles",
        "cameraAngle": "baseline",
        "athleteLabel": "球采集",
        "level": "大众进阶",
    }
    fields.update(overrides)
    return AnalysisUploadMetadata(**fields)


def make_multiview_payload(
    capture_take_id: str = "CT_001",
    *,
    execution_mode: str = "late_fusion_v1",
    scene_mode: str = "approximate",
    scene_revision: int | None = None,
) -> AnalysisJobCreate:
    return AnalysisJobCreate(
        metadata=make_metadata(capture_take_id=capture_take_id),
        analysisKind="multiview",
        multiview=MultiViewCreateRequest(
            referenceViewId="cam_1",
            views=[
                MultiViewViewPayload(viewId="cam_1", videoId="v1", calibrationId="cal1", courtOrientation="identity"),
                MultiViewViewPayload(
                    viewId="cam_2", videoId="v2", calibrationId="cal2", courtOrientation="rotate_180"
                ),
            ],
            executionMode=execution_mode,
            sceneCalibrationMode=scene_mode,
            sceneCalibrationRevision=scene_revision,
        ),
    )


# ---- Task 1.6: 编排字段缺省兼容 -------------------------------------------------

def test_analysis_job_summary_defaults_for_legacy_jobs():
    payload = {
        "id": "job-old",
        "status": "completed",
        "canonicalStatus": "succeeded",
        "displayStatus": "completed",
        "stage": "report",
        "progress": 100,
        "createdAt": "2026-08-01T00:00:00Z",
        "updatedAt": "2026-08-01T00:00:00Z",
        "metadata": make_metadata().model_dump(),
        "stages": [],
        "reportId": "PV-JOB-OLD",
        "analysisMode": "real",
    }
    job = AnalysisJobSummary.model_validate(payload)
    assert job.analysisKind == "single_view"
    assert job.visibility == "public"
    assert job.orchestrationStatus == "none"
    assert job.parentJobId is None
    assert job.analysisScope is None
    assert job.fusionRunId is None
    assert job.sourceJobs == []


# ---- Task 2.3: is_runnable / claim_next -----------------------------------------

def test_waiting_sources_parent_is_not_claimable(tmp_path):
    store = JobStore(make_temp_storage(tmp_path))
    parent = store.create_job(
        AnalysisJobCreate(metadata=make_metadata(capture_take_id="CT_1"), analysisKind="multiview")
    )
    assert parent.orchestrationStatus == "waiting_sources"
    # 队列里只有 waiting_sources Parent → 不可 claim（不占用 Worker）
    assert store.claim_next("worker-1") is None


def test_fusion_ready_parent_is_claimable(tmp_path):
    store = JobStore(make_temp_storage(tmp_path))
    parent = store.create_job(
        AnalysisJobCreate(metadata=make_metadata(capture_take_id="CT_1"), analysisKind="multiview")
    )
    store.update(parent.id, orchestrationStatus="fusion_ready")
    claimed = store.claim_next("worker-1")
    assert claimed is not None and claimed.id == parent.id


def test_single_view_queued_is_claimable(tmp_path):
    store = JobStore(make_temp_storage(tmp_path))
    store.create_job(AnalysisJobCreate(metadata=make_metadata(), videoId="v1", calibrationId="cal1"))
    claimed = store.claim_next("worker-1")
    assert claimed is not None and claimed.analysisKind == "single_view"


# ---- Task 4.4 / 5.4: Coordinator 创建 + 推进 ------------------------------------

def _coordinator_with_patches(monkeypatch, tmp_path):
    from app.services import mock_analysis
    import app.services.multiview_coordinator as mc

    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    mock_analysis._sync_orchestration_storage()
    # 绕过 DB/视频/标定依赖
    monkeypatch.setattr(mc, "preflight_multiview", lambda payload, **kw: mc.PreflightResult(ok=True, issues=[]))
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(tmp_path / "take"))
    return mock_analysis, mc


def test_coordinator_creates_parent_and_dedicated_children(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())

    assert parent.analysisKind == "multiview"
    assert parent.orchestrationStatus == "waiting_sources"
    assert parent.referenceViewId == "cam_1"
    assert len(parent.sourceJobs) == 2
    assert parent.analysisMode == "real"

    for ref in parent.sourceJobs:
        child = mock_analysis._JOB_STORE.get(ref.jobId)
        assert child is not None
        assert child.visibility == "internal"
        assert child.parentJobId == parent.id
        assert child.analysisScope == "full"
        assert child.analysisKind == "single_view"
        assert child.analysisMode == "real"
        assert ref.courtOrientation in {"identity", "rotate_180"}

    # waiting_sources Parent + 两个 queued child → claim_next 应领取 child，而不是 Parent
    claimed = mock_analysis._JOB_STORE.claim_next("worker-1")
    assert claimed is not None and claimed.visibility == "internal"


def test_coordinator_parent_inherits_reference_child_video_id(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())

    # reference view = cam_1 → Parent 的 videoId/calibrationId 应等于 cam_1 child 的
    ref_child = mock_analysis._JOB_STORE.get(
        next(ref.jobId for ref in parent.sourceJobs if ref.cameraSlot == "cam_1")
    )
    assert ref_child is not None
    assert parent.videoId == ref_child.videoId
    assert parent.calibrationId == ref_child.calibrationId
    # cam_1 child 用的是 payload 里第一个 view 的 video/calibration
    assert parent.videoId == "v1"
    assert parent.calibrationId == "cal1"


def test_joint_parent_persists_scene_reference_on_parent_and_joint_inputs(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(
        make_multiview_payload(
            execution_mode="joint_tracking_v2",
            scene_mode="metric",
            scene_revision=2,
        )
    )

    assert parent.sceneCalibrationMode == "metric"
    assert parent.sceneCalibrationRevision == 2
    assert parent.sceneCalibrationStatus == "ready"
    assert {item["sceneCalibrationRevision"] for item in parent.jointViewInputs} == {2}
    assert {item["sceneCalibrationMode"] for item in parent.jointViewInputs} == {"metric"}


def test_get_mock_job_resolves_parent_video_source_from_reference_child(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    ref_child = mock_analysis._JOB_STORE.get(
        next(ref.jobId for ref in parent.sourceJobs if ref.cameraSlot == "cam_1")
    )

    # 模拟历史 Parent：videoId 缺失（如后端重启且 result 未落盘）
    stripped = parent.model_copy(update={"videoId": None, "calibrationId": None})
    mock_analysis._JOB_STORE.save(stripped)

    resolved = mock_analysis.get_mock_job(parent.id)
    assert resolved.videoId == ref_child.videoId == "v1"
    assert resolved.calibrationId == ref_child.calibrationId == "cal1"
    # 清理：get_mock_job 会把 job 写进模块级 JOBS，避免污染后续测试
    mock_analysis.JOBS.pop(parent.id, None)


def test_coordinator_advances_to_fusion_ready_and_reconciles(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())

    # 两个 child 都 succeeded → Parent → fusion_ready
    for ref in parent.sourceJobs:
        child = mock_analysis._JOB_STORE.get(ref.jobId)
        mock_analysis._JOB_STORE.mark_succeeded(child, stages=child.stages)

    advanced = mock_analysis._get_coordinator().reconcile_all()
    refreshed = mock_analysis._JOB_STORE.get(parent.id)
    assert refreshed.orchestrationStatus == "fusion_ready"
    assert refreshed.canonicalStatus == "queued"
    assert refreshed.viewRuns is not None
    assert refreshed.viewRuns["cam_1"].status == "succeeded"
    assert advanced >= 1


def test_coordinator_advances_to_fallback_and_failed(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    child_a = mock_analysis._JOB_STORE.get(parent.sourceJobs[0].jobId)
    child_b = mock_analysis._JOB_STORE.get(parent.sourceJobs[1].jobId)

    # A succeeded + B failed → fallback_ready
    mock_analysis._JOB_STORE.mark_succeeded(child_a, stages=child_a.stages)
    mock_analysis._JOB_STORE.mark_failed(child_b, stages=child_b.stages, message="cam2 failed")
    mock_analysis._get_coordinator().reconcile_all()
    assert mock_analysis._JOB_STORE.get(parent.id).orchestrationStatus == "fallback_ready"

    # 双路失败 → Parent failed
    parent2 = coord.create_multiview_job(make_multiview_payload())
    for ref in parent2.sourceJobs:
        child = mock_analysis._JOB_STORE.get(ref.jobId)
        mock_analysis._JOB_STORE.mark_failed(child, stages=child.stages, message="failed")
    mock_analysis._get_coordinator().reconcile_all()
    assert mock_analysis._JOB_STORE.get(parent2.id).canonicalStatus == "failed"

    # 一路成功 + 一路 Worker 失联仍可确定性降级；双路失联则 Parent 也失联。
    parent3 = coord.create_multiview_job(make_multiview_payload())
    child_a = mock_analysis._JOB_STORE.get(parent3.sourceJobs[0].jobId)
    child_b = mock_analysis._JOB_STORE.get(parent3.sourceJobs[1].jobId)
    mock_analysis._JOB_STORE.mark_succeeded(child_a, stages=child_a.stages)
    mock_analysis._JOB_STORE.mark_interrupted(child_b)
    mock_analysis._get_coordinator().reconcile_all()
    assert mock_analysis._JOB_STORE.get(parent3.id).orchestrationStatus == "fallback_ready"

    parent4 = coord.create_multiview_job(make_multiview_payload())
    for ref in parent4.sourceJobs:
        child = mock_analysis._JOB_STORE.get(ref.jobId)
        mock_analysis._JOB_STORE.mark_interrupted(child)
    mock_analysis._get_coordinator().reconcile_all()
    interrupted_parent = mock_analysis._JOB_STORE.get(parent4.id)
    assert interrupted_parent.canonicalStatus == "interrupted"
    assert interrupted_parent.interruptionCode == "worker_lost"


# ---- Task 6.6: 取消/删除级联 -----------------------------------------------------

def test_cancel_parent_cascades_to_owned_children(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    child_ids = coord.owned_child_ids(parent)

    mock_analysis._JOB_STORE.cancel(parent.id)
    # waiting_sources Parent 取消 → 级联取消 owned 非终态 child
    coord.cancel_cascade(mock_analysis._JOB_STORE.get(parent.id))

    for child_id in child_ids:
        child = mock_analysis._JOB_STORE.get(child_id)
        assert child.canonicalStatus == "canceled"


# ---- Task 6.5 / 6.6: Child 外部保护 + 删除级联 -----------------------------------

def test_internal_child_direct_cancel_is_blocked(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    child_id = coord.owned_child_ids(parent)[0]

    with pytest.raises(ValueError, match="cannot be canceled directly"):
        mock_analysis.cancel_analysis_job(child_id)


def test_internal_child_direct_delete_is_blocked(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    child_id = coord.owned_child_ids(parent)[0]

    result = mock_analysis.delete_analysis_job(child_id)
    assert result.status == "blocked"
    assert "internal source job" in result.detail


def test_delete_parent_cascades_to_terminal_children(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload())
    child_ids = coord.owned_child_ids(parent)

    # 子任务置为终态（succeeded），Parent 才能删除
    for child_id in child_ids:
        child = mock_analysis._JOB_STORE.get(child_id)
        mock_analysis._JOB_STORE.mark_succeeded(child, stages=child.stages)
    # Parent 非终态 → 删除 blocked（先取消）；置终态后 → 级联删除
    assert mock_analysis.delete_analysis_job(parent.id).status == "blocked"
    mock_analysis._JOB_STORE.mark_succeeded(parent, stages=parent.stages)

    result = mock_analysis.delete_analysis_job(parent.id)
    assert result.status == "deleted"

    for child_id in child_ids:
        assert mock_analysis.get_mock_job(child_id) is None
    assert mock_analysis.get_mock_job(parent.id) is None


# ---- 录制级删除：delete_analysis_by_recording_session ---------------------------------

def test_delete_by_recording_session_cascades_parent_and_children(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload(capture_take_id="CT_001"))
    child_ids = coord.owned_child_ids(parent)
    for child_id in child_ids:
        child = mock_analysis._JOB_STORE.get(child_id)
        mock_analysis._JOB_STORE.mark_succeeded(child, stages=child.stages)
    mock_analysis._JOB_STORE.mark_succeeded(parent, stages=parent.stages)

    results = mock_analysis.delete_analysis_by_recording_session(
        "sync_test", session_capture_take_id="CT_001"
    )
    # 只返回 public Parent（internal child 经 cascade 删除，不单独返回）
    assert [r.job_id for r in results] == [parent.id]
    assert results[0].status == "deleted"
    assert mock_analysis.get_mock_job(parent.id) is None
    for child_id in child_ids:
        assert mock_analysis.get_mock_job(child_id) is None


def test_delete_by_recording_session_active_parent_blocked(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    parent = coord.create_multiview_job(make_multiview_payload(capture_take_id="CT_001"))
    # parent 仍为 queued/waiting_sources → 活跃，删除被阻断
    results = mock_analysis.delete_analysis_by_recording_session(
        "sync_test", session_capture_take_id="CT_001"
    )
    assert results[0].job_id == parent.id
    assert results[0].status == "blocked"
    assert mock_analysis.get_mock_job(parent.id) is not None


def test_delete_by_recording_session_matches_single_view_job(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)

    # 从录制创建的失败单摄任务（video 不存在 → failed，终态可删），归属 recording_session_id
    job = mock_analysis.create_analysis_job(
        AnalysisJobCreate(
            metadata=make_metadata(capture_take_id="CT_001", recording_session_id="sync_test"),
            videoId="v_unknown",
            calibrationId="cal1",
        )
    )
    assert job.status == "failed"
    results = mock_analysis.delete_analysis_by_recording_session("sync_test")
    assert [r.job_id for r in results] == [job.id]
    assert results[0].status == "deleted"
    assert mock_analysis.get_mock_job(job.id) is None


def test_delete_by_recording_session_no_match_returns_empty(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)

    parent = mock_analysis.create_analysis_job(
        AnalysisJobCreate(metadata=make_metadata(capture_take_id="CT_OTHER"))
    )
    results = mock_analysis.delete_analysis_by_recording_session("sync_other")
    assert results == []
    assert mock_analysis.get_mock_job(parent.id) is not None


# ---- Task 7.4: Preflight ---------------------------------------------------------

def test_preflight_requires_multiview_payload():
    from app.services.multiview_coordinator import preflight_multiview

    result = preflight_multiview(AnalysisJobCreate(metadata=make_metadata()))
    assert not result.ok
    assert any("multiview" in issue for issue in result.issues)


def test_preflight_requires_capture_take_id():
    from app.services.multiview_coordinator import preflight_multiview

    payload = make_multiview_payload()
    payload.metadata = make_metadata()  # 去掉 capture_take_id
    result = preflight_multiview(payload)
    assert not result.ok
    assert any("capture_take_id" in issue for issue in result.issues)


def test_preflight_requires_at_least_two_views():
    from app.services.multiview_coordinator import preflight_multiview

    payload = make_multiview_payload()
    payload.multiview.views = payload.multiview.views[:1]
    result = preflight_multiview(payload)
    assert not result.ok
    assert any("two views" in issue for issue in result.issues)


def test_preflight_missing_sync_is_not_silent(monkeypatch, tmp_path):
    from app.services.multiview_coordinator import preflight_multiview
    import app.services.multiview_coordinator as mc

    take_dir = tmp_path / "take"
    take_dir.mkdir()
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(video_service, "get_video", lambda vid: object())
    from app.services.calibration_service import CalibrationService

    monkeypatch.setattr(CalibrationService, "get_calibration", lambda self, cid: object())

    result = preflight_multiview(make_multiview_payload())
    # sync_calibration.json 缺失 → 明确失败，绝不静默
    assert not result.ok
    assert any("sync_calibration" in issue for issue in result.issues)
    # 错误信息带诊断细节：期望路径 + 生成命令，便于精准定位
    sync_issue = next(issue for issue in result.issues if "sync_calibration" in issue)
    assert f"take_dir={take_dir}" in sync_issue
    assert "generate_dual_camera_sync.py" in sync_issue
    assert "timeline 内容" in sync_issue


def test_preflight_all_ready(monkeypatch, tmp_path):
    from app.services.multiview_coordinator import preflight_multiview
    import app.services.multiview_coordinator as mc

    take_dir = tmp_path / "take"
    (take_dir / "timeline").mkdir(parents=True)
    (take_dir / "timeline" / "sync_calibration.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(video_service, "get_video", lambda vid: object())
    from app.services.calibration_service import CalibrationService

    monkeypatch.setattr(CalibrationService, "get_calibration", lambda self, cid: object())

    result = preflight_multiview(make_multiview_payload())
    assert result.ok
    assert result.issues == []


def test_preflight_reuses_existing_canonical_frame_for_display_only_retry(monkeypatch, tmp_path):
    """普通重试不应把默认展示/输入朝向重新定义成 canonical conflict。"""
    from app.services.multiview_coordinator import preflight_multiview
    import app.services.multiview_coordinator as mc
    from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition, write_canonical_court_frame

    take_dir = tmp_path / "take"
    (take_dir / "timeline").mkdir(parents=True)
    (take_dir / "timeline" / "sync_calibration.json").write_text("{}", encoding="utf-8")
    write_canonical_court_frame(
        take_dir,
        CanonicalCourtFrameDefinition.create(
            "CT_001",
            "north_baseline",
            "south_baseline",
            orientation_by_view={"cam_1": "rotate_180", "cam_2": "identity"},
        ),
    )
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(video_service, "get_video", lambda vid: object())
    from app.services.calibration_service import CalibrationService

    monkeypatch.setattr(CalibrationService, "get_calibration", lambda self, cid: object())

    result = preflight_multiview(make_multiview_payload())
    assert result.ok
    assert not any("canonical frame conflict" in issue for issue in result.issues)


# ---- Task 9.3: select_trajectory_source -----------------------------------------

def test_select_trajectory_source_includes_unavailable():
    assert select_trajectory_source(fused_available=True, single_view_available=False) == "fused"
    assert select_trajectory_source(fused_available=False, single_view_available=True) == "single_view"
    # 双路失败：不再假装存在单视角轨迹
    assert select_trajectory_source(fused_available=False, single_view_available=False) == "unavailable"


# ---- Task 10.3 / 11.4: Composer --------------------------------------------------

def _synthetic_fused_artifact() -> dict[str, object]:
    samples = []
    for player, x, y in (("P1", 5.0, 10.0), ("P1", 6.0, 12.0), ("P2", 14.0, 30.0)):
        samples.append(
            {
                "global_player_id": player,
                "timestamp_seconds": 1.0,
                "take_timestamp_ms": 1000.0,
                "reference_frame_index": 30,
                "x_ft": x,
                "y_ft": y,
                "fusion_status": "dual_observed",
                "fusion_confidence": 0.9,
                "contributing_views": ["cam_1", "cam_2"],
                "selected_view": None,
                "view_observations": {},
                "association_confidence": 0.9,
                "sync_quality": "good",
                "court_frame_version": "canonical_court_frame.v1",
                "measurement_source": "observed",
                "metric_eligible": True,
            }
        )
    return {
        "schema_version": "fused_player_trajectory.v1",
        "run_id": "mvf_test",
        "capture_take_id": "CT_001",
        "reference_view_id": "cam_1",
        "secondary_view_id": "cam_2",
        "sync_quality": "good",
        "court_frame_version": "canonical_court_frame.v1",
        "players": ["P1", "P2"],
        "samples": samples,
    }


def test_composer_inherits_url_status_from_reference_child(tmp_path):
    """Composer 继承 reference child 产物时，必须补齐 url/status/detail，而不只是 *_json_path。"""
    from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult
    from app.services.multiview_result_composer import MultiViewResultComposer

    storage = make_temp_storage(tmp_path)
    composer = MultiViewResultComposer(storage)
    take_dir = tmp_path / "take"
    storage.register_capture_job("job-child", take_dir)
    storage.register_capture_job("job-parent", take_dir)

    # child 已生成的部分产物文件
    child_root = take_dir / "analysis" / "job-child"
    child_root.mkdir(parents=True, exist_ok=True)
    (child_root / "tracking_overlay.json").write_text('{"frames": []}', encoding="utf-8")
    (child_root / "pose_overlay.json").write_text('{"frames": []}', encoding="utf-8")
    (child_root / "position_visualizations" / "structured").mkdir(parents=True)
    (child_root / "position_visualizations" / "structured" / "data.json").write_text("{}", encoding="utf-8")

    # child 已落盘的 AnalysisPipelineResult（含 url/status/detail）
    child_artifacts = AnalysisArtifacts(
        tracking_overlay_url="/api/analysis/jobs/job-child/artifacts/tracking-overlay",
        tracking_overlay_status="available",
        tracking_overlay_detail="已生成 100 帧",
        pose_overlay_url="/api/analysis/jobs/job-child/artifacts/pose-overlay",
        pose_overlay_status="available",
        position_visualizations_status="available",
        position_visualizations_detail="热力图+散点图",
    )
    child_result = AnalysisPipelineResult(
        job_id="job-child",
        status="completed",
        generated_at="2026-08-08T00:00:00Z",
        stages=[],
        tracks=[],
        metrics=composer.recompute_metrics(_synthetic_fused_artifact(), build_match_context("doubles")),
        artifacts=child_artifacts,
        message="ok",
    )
    storage.write_json(storage.output_json_path("job-child"), child_result.model_dump(mode="json"))

    # child job summary（供 composer 读取 id/metadata）
    child = JobStore(storage).create_job(
        AnalysisJobCreate(metadata=make_metadata(capture_take_id="CT_001")), job_id="job-child"
    )

    artifacts = AnalysisArtifacts()
    composer._inherit_reference_artifacts("job-parent", child, artifacts)

    # URL 指向 Parent 命名空间，status/detail 继承自 child
    assert artifacts.tracking_overlay_url == "/api/analysis/jobs/job-parent/artifacts/tracking-overlay"
    assert artifacts.tracking_overlay_status == "available"
    assert artifacts.tracking_overlay_detail == "已生成 100 帧"
    assert artifacts.pose_overlay_url == "/api/analysis/jobs/job-parent/artifacts/pose-overlay"
    assert artifacts.pose_overlay_status == "available"
    assert artifacts.position_visualizations_status == "available"
    assert artifacts.position_visualizations_detail == "热力图+散点图"
    # 文件已复制到 Parent 命名空间
    assert (take_dir / "analysis" / "job-parent" / "tracking_overlay.json").exists()
    assert (take_dir / "analysis" / "job-parent" / "pose_overlay.json").exists()


def test_composer_recomputes_metrics_from_fused(tmp_path):
    from app.services.multiview_result_composer import MultiViewResultComposer

    composer = MultiViewResultComposer(make_temp_storage(tmp_path))
    metrics = composer.recompute_metrics(_synthetic_fused_artifact(), build_match_context("doubles"))
    assert isinstance(metrics, PerformanceMetrics)
    assert len(metrics.distances) >= 1  # P1 两点间产生距离
    assert len(metrics.kitchen_dwell) >= 1


def test_composer_publishes_fused_artifacts_with_manifest(tmp_path):
    from app.services.multiview_result_composer import MultiViewResultComposer

    storage = make_temp_storage(tmp_path)
    composer = MultiViewResultComposer(storage)
    fused = _synthetic_fused_artifact()
    diagnostics = {"schema_version": "fused_diagnostics.v1", "run_id": "mvf_test", "fusion_status_counts": {"dual_observed": 3}}
    manifest = composer.publish_fused_artifacts(
        "job-parent-1",
        fused,
        diagnostics,
        {"mode": "multiview_fused", "source_job_id": "job-parent-1", "source_view": "cam_1", "reason": "ok"},
    )

    assert storage.fused_trajectory_json_path("job-parent-1").exists()
    assert storage.fusion_diagnostics_json_path("job-parent-1").exists()
    manifest_path = storage.fusion_manifest_json_path("job-parent-1")
    assert manifest_path.exists()

    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = loaded["artifacts"]
    # manifest 是唯一出口：URL 全部指向 Parent，不指向 fusion run / child
    assert artifacts["playerTrajectory"]["url"].startswith("/api/analysis/jobs/job-parent-1/")
    assert artifacts["fusionDiagnostics"]["url"].startswith("/api/analysis/jobs/job-parent-1/")
    assert "mvf_" not in artifacts["playerTrajectory"]["url"]
    assert loaded["analysis_source"]["mode"] == "multiview_fused"


# ---- Task 8.4: fusionRunId 幂等（崩溃后重启复用同一 Run） -------------------------

def _write_good_sync(take_dir, tmp_path) -> None:
    timeline = take_dir / "timeline"
    timeline.mkdir(parents=True, exist_ok=True)
    (timeline / "sync_calibration.json").write_text(
        json.dumps(
            {
                "schema_version": "dual_camera_sync_calibration.v1",
                "reference_camera": "cam_1",
                "mappings": {
                    "cam_2": {
                        "reference_camera": "cam_1",
                        "camera_id": "cam_2",
                        "offset_ms": 0,
                        "rate": 1.0,
                        "drift_ppm": 0,
                        "residual_rms_ms": 1.0,
                        "quality": "good",
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_render_trajectory(path, player_id: str = "P1", n: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = []
    for i in range(n):
        samples.append(
            {
                "frame_index": i,
                "timestamp_seconds": i * (1.0 / 30.0),
                "x_ft": 5.0 + i,
                "y_ft": 10.0 + i,
                "source": "observed",
                "confidence": 0.9,
                "player_id": player_id,
                "projection_status": "ok",
                "projection_confidence": 0.9,
                "footpoint_method": "ankle_midpoint",
                "source_track_id": f"track_{player_id}",
            }
        )
    path.write_text(
        json.dumps({"schema_version": "player-render-trajectory.v2", "samples": samples}, ensure_ascii=False),
        encoding="utf-8",
    )


def _build_parent_with_children(storage, take_dir) -> tuple[JobStore, AnalysisJobSummary, list[str]]:
    from app.schemas.analysis import SourceJobRef

    store = JobStore(storage)
    c1 = store.create_job(
        AnalysisJobCreate(metadata=make_metadata(camera_slot="cam_1"), videoId="v1", calibrationId="cal1")
    )
    c2 = store.create_job(
        AnalysisJobCreate(metadata=make_metadata(camera_slot="cam_2"), videoId="v2", calibrationId="cal2")
    )
    store.update(c1.id, parentJobId="job-parent", visibility="internal", analysisScope="full")
    store.update(c2.id, parentJobId="job-parent", visibility="internal", analysisScope="full")
    parent = store.create_job(
        AnalysisJobCreate(metadata=make_metadata(capture_take_id="CT_001"), analysisKind="multiview"),
        job_id="job-parent",
    )
    parent = store.update(
        "job-parent",
        sourceJobs=[
            SourceJobRef(cameraSlot="cam_1", jobId=c1.id, courtOrientation="identity"),
            SourceJobRef(cameraSlot="cam_2", jobId=c2.id, courtOrientation="rotate_180"),
        ],
        referenceViewId="cam_1",
        orchestrationStatus="fusion_ready",
    )
    return store, parent, [c1.id, c2.id]


def test_fusion_run_id_reused_after_interruption(monkeypatch, tmp_path):
    from app.services.analysis_executor_dispatch import MultiViewAnalysisExecutor
    from app.services.job_orchestration import CancellationToken
    from app.vision.multiview.artifact import (
        FUSED_TRAJECTORY_FILENAME,
        write_fused_artifact,
        write_fusion_diagnostics,
    )
    from app.vision.multiview.fusion_run import default_run_output_dir

    storage = make_temp_storage(tmp_path)
    take_dir = tmp_path / "take"
    (take_dir / "analysis").mkdir(parents=True)
    _write_good_sync(take_dir, tmp_path)
    storage.register_capture_job("job-parent", take_dir)

    store, parent, _ = _build_parent_with_children(storage, take_dir)
    # 模拟"融合已完成但 Parent 未 mark completed"后崩溃 → 重启：fusionRunId 已持久化 + run 产物完整
    store.update(parent.id, fusionRunId="mvf_reuse")
    parent = store.get("job-parent")  # 重新读取，确保 executor 看到已持久化的 fusionRunId
    run_dir = default_run_output_dir(take_dir / "analysis", "mvf_reuse")
    write_fused_artifact(run_dir, _synthetic_fused_artifact())
    write_fusion_diagnostics(
        run_dir, {"schema_version": "fused_diagnostics.v1", "run_id": "mvf_reuse", "fusion_status_counts": {"dual_observed": 3}}
    )

    executor = MultiViewAnalysisExecutor(store, pipeline_factory=lambda **kw: None)
    result = executor.execute(parent, CancellationToken(store, parent.id), lambda _s: None)

    assert result.status == "completed"
    # 复用同一 fusionRunId：未重新融合，run 目录 artifact 保留
    assert (run_dir / FUSED_TRAJECTORY_FILENAME).exists()
    assert len(result.tracks) == 3
    assert {t.track_id for t in result.tracks} == {"P1", "P2"}


def test_job_level_fallback_does_not_produce_real_fused_artifact(monkeypatch, tmp_path):
    from app.services.analysis_executor_dispatch import MultiViewAnalysisExecutor
    from app.services.job_orchestration import CancellationToken

    storage = make_temp_storage(tmp_path)
    take_dir = tmp_path / "take"
    (take_dir / "analysis").mkdir(parents=True)
    # 无 sync_calibration.json → sync authority unavailable → job-level fallback
    storage.register_capture_job("job-parent", take_dir)

    store, parent, (c1_id, _) = _build_parent_with_children(storage, take_dir)
    storage.register_capture_job(c1_id, take_dir)
    _write_render_trajectory(storage.player_render_trajectory_path(c1_id), player_id="P1", n=3)

    executor = MultiViewAnalysisExecutor(store, pipeline_factory=lambda **kw: None)
    result = executor.execute(parent, CancellationToken(store, parent.id), lambda _s: None)

    assert result.status == "completed"
    # 未执行融合：manifest 标注 single_view_fallback
    manifest = json.loads(storage.fusion_manifest_json_path("job-parent").read_text(encoding="utf-8"))
    assert manifest["analysis_source"]["mode"] == "single_view_fallback"
    assert "未执行多视角融合" in result.message
    # Parent 命名空间的 fused 产物是 fallback 轨迹，不含 dual_observed 样本
    fused = json.loads(storage.fused_trajectory_json_path("job-parent").read_text(encoding="utf-8"))
    statuses = {s["fusion_status"] for s in fused["samples"]}
    assert statuses == {"single_view_fallback"}


# ---- sync 映射键解析（硬件 camera id 键 vs 视图槽位键） -------------------------

def test_resolve_secondary_sync_key_handles_camera_id_keyed_file():
    from app.services.analysis_executor_dispatch import MultiViewAnalysisExecutor
    from app.services.dual_camera_sync import SyncCalibration
    from app.vision.multiview.sync import MultiViewSyncCalibration

    cal = SyncCalibration(
        reference_camera="174",
        camera_id="175",
        offset_seconds=0.0,
        rate=1.0,
        drift_ppm=0.0,
        residual_rms_seconds=0.01,
        anchor_count=2,
        quality="good",
    )
    # calibrate_dual_camera_sync.py 产物：以硬件 camera id 为键
    camera_keyed = MultiViewSyncCalibration(reference_camera="174", mappings={"174": cal, "175": cal})
    assert MultiViewAnalysisExecutor._resolve_secondary_sync_key(camera_keyed, "cam_2") == "175"

    # 槽位键文件：直接命中视图槽位
    slot_keyed = MultiViewSyncCalibration(reference_camera="cam_1", mappings={"cam_1": cal, "cam_2": cal})
    assert MultiViewAnalysisExecutor._resolve_secondary_sync_key(slot_keyed, "cam_2") == "cam_2"

    # 无 sync → 原样返回（fallback 路径不使用映射）
    assert MultiViewAnalysisExecutor._resolve_secondary_sync_key(None, "cam_2") == "cam_2"


# ---- 自动推导 degraded 同步校准（从录制时序元数据） ----------------------------

def test_derive_sync_calibration_from_segment_timing():
    from types import SimpleNamespace

    from app.services.dual_camera_sync import derive_sync_calibration_from_segment_timing

    segment = SimpleNamespace(
        segment_index=0,
        files=[
            SimpleNamespace(role="cam_1", camera_id="174", input_start_time=100.0, media_duration_sec=60.0),
            SimpleNamespace(role="cam_2", camera_id="175", input_start_time=100.25, media_duration_sec=60.0),
        ],
    )
    payload = derive_sync_calibration_from_segment_timing([segment])

    assert payload["schema_version"] == "dual_camera_sync_calibration.v1"
    assert payload["reference_camera"] == "174"
    assert payload["source"] == "auto_degraded_from_recording_timing"
    # 自动推导恒 degraded，不冒充 authoritative good
    assert payload["mappings"]["174"]["quality"] == "degraded"
    assert payload["mappings"]["175"]["quality"] == "degraded"
    # offset = input_start_1 - input_start_2 = 100 - 100.25 = -0.25s → -250ms
    assert payload["mappings"]["175"]["offset_ms"] == -250.0
    assert payload["mappings"]["175"]["rate"] == 1.0

    # 无可用时序元数据 → 明确报错（不静默写空校准）
    with pytest.raises(ValueError, match="input_start_time"):
        derive_sync_calibration_from_segment_timing(
            [SimpleNamespace(segment_index=0, files=[SimpleNamespace(role="cam_1")])]
        )


def test_ensure_sync_calibration_auto_generates_degraded(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.camera.sync_recorder_service import sync_recording_service
    import app.services.multiview_coordinator as mc

    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    take_dir = tmp_path / "take"
    (take_dir / "timeline").mkdir(parents=True)
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(coord, "_resolve_sync_session_id", lambda ctid: "sync-1")

    segment = SimpleNamespace(
        segment_index=0,
        files=[
            SimpleNamespace(role="cam_1", input_start_time=100.0, media_duration_sec=60.0),
            SimpleNamespace(role="cam_2", input_start_time=100.25, media_duration_sec=60.0),
        ],
    )
    monkeypatch.setattr(sync_recording_service, "get_session", lambda sid: SimpleNamespace(segments=[segment]))

    # 缺文件 → 自动推导写入 degraded 校准
    assert coord._ensure_sync_calibration("CT_1") is True
    sync_path = mc.sync_calibration_path(take_dir)
    assert sync_path.exists()
    payload = json.loads(sync_path.read_text(encoding="utf-8"))
    assert payload["mappings"]["cam_2"]["quality"] == "degraded"

    # 幂等：已存在 → True，不再重写
    written_once = sync_path.read_text(encoding="utf-8")
    assert coord._ensure_sync_calibration("CT_1") is True
    assert sync_path.read_text(encoding="utf-8") == written_once


def test_ensure_sync_calibration_repairs_legacy_auto_identity(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.camera.sync_recorder_service import sync_recording_service
    import app.services.multiview_coordinator as mc
    from app.services.dual_camera_sync import derive_sync_calibration_from_segment_timing

    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    take_dir = tmp_path / "take-legacy"
    (take_dir / "timeline").mkdir(parents=True)
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(coord, "_resolve_sync_session_id", lambda ctid: "sync-legacy")

    stale_segment = SimpleNamespace(
        segment_index=0,
        files=[
            SimpleNamespace(role="cam_1", input_start_time=100.0, media_duration_sec=60.0),
            SimpleNamespace(role="cam_2", input_start_time=100.25, media_duration_sec=60.0),
        ],
    )
    stale_payload = derive_sync_calibration_from_segment_timing([stale_segment])
    sync_path = mc.sync_calibration_path(take_dir)
    sync_path.write_text(json.dumps(stale_payload), encoding="utf-8")

    actual_segment = SimpleNamespace(
        segment_index=0,
        files=[
            SimpleNamespace(role="cam_1", camera_id="174", input_start_time=100.0, media_duration_sec=60.0),
            SimpleNamespace(role="cam_2", camera_id="175", input_start_time=100.25, media_duration_sec=60.0),
        ],
    )
    session = SimpleNamespace(
        camera_slots={
            "cam_1": SimpleNamespace(camera_id="174"),
            "cam_2": SimpleNamespace(camera_id="175"),
        },
        segments=[actual_segment],
    )
    monkeypatch.setattr(sync_recording_service, "get_session", lambda sid: session)

    assert coord._ensure_sync_calibration("CT_legacy") is True
    repaired = json.loads(sync_path.read_text(encoding="utf-8"))
    assert repaired["reference_camera"] == "174"
    assert set(repaired["mappings"]) == {"174", "175"}
    assert repaired["mappings"]["175"]["camera_id"] == "175"


def test_ensure_sync_calibration_returns_false_when_not_derivable(monkeypatch, tmp_path):
    from app.camera.sync_recorder_service import sync_recording_service
    import app.services.multiview_coordinator as mc

    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    take_dir = tmp_path / "take2"
    (take_dir / "timeline").mkdir(parents=True)
    monkeypatch.setattr(mc, "_check_capture_take_dir", lambda ctid: str(take_dir))
    monkeypatch.setattr(coord, "_resolve_sync_session_id", lambda ctid: "sync-1")
    # 会话存在但无可用时序元数据 → 无法推导 → False（preflight 报详细原因）
    monkeypatch.setattr(sync_recording_service, "get_session", lambda sid: SimpleNamespace(segments=[]))
    assert coord._ensure_sync_calibration("CT_2") is False
    assert not mc.sync_calibration_path(take_dir).exists()


# ---- 回归：storage 未变时 worker 也必须构建（否则 worker 线程永不启动，任务卡排队） ----

def test_worker_built_when_storage_unchanged(monkeypatch, tmp_path):
    from app.services import mock_analysis

    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    mock_analysis._sync_orchestration_storage()
    # 模拟模块级 _WORKER=None 后 storage 匹配的启动场景：必须构建出 worker
    mock_analysis._WORKER = None
    mock_analysis._sync_orchestration_storage()
    assert mock_analysis._WORKER is not None
    assert callable(mock_analysis._WORKER.start)

    # 构建出的 worker 能领取 queued 单摄 job（验证 _loop 不会因 worker 缺失而空转）
    job = mock_analysis._JOB_STORE.create_job(
        AnalysisJobCreate(metadata=make_metadata(), videoId="v1", calibrationId="cal1")
    )
    claimed = mock_analysis._JOB_STORE.claim_next("local-worker")
    assert claimed is not None and claimed.id == job.id


# ---- 分析级裁剪：secondary 经 sync 换算到自身时间轴 -----------------------------

def test_map_clip_to_view_uses_sync_offset(monkeypatch, tmp_path):
    from app.services import mock_analysis
    import app.services.multiview_coordinator as mc
    from app.services.dual_camera_sync import calibration_to_dict, calibrations_from_anchor_rows

    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()

    take_dir = tmp_path / "take"
    (take_dir / "timeline").mkdir(parents=True)
    # cam_2 媒体 = cam_1 - 0.25s（rate=1）
    anchors = [{"cam_1": 0.0, "cam_2": -0.25}, {"cam_1": 60.0, "cam_2": 59.75}]
    cals = calibrations_from_anchor_rows(anchors, reference_camera="cam_1", camera_ids=["cam_1", "cam_2"])
    payload = {
        "schema_version": "dual_camera_sync_calibration.v1",
        "reference_camera": "cam_1",
        "mappings": {cid: calibration_to_dict(cal) for cid, cal in cals.items()},
    }
    (take_dir / "timeline" / "sync_calibration.json").write_text(json.dumps(payload), encoding="utf-8")

    # reference 窗口 [1000ms, 61000ms] → cam_2 = [750ms, 60750ms]（同一物理窗口）
    start, end = coord._map_clip_to_view(str(take_dir), "cam_2", 1000, 61000)
    assert start == 750
    assert end == 60750

    # reference 视图本身不换算（offset=0 → 原样）
    assert coord._map_clip_to_view(str(take_dir), "cam_1", 1000, 61000) == (1000, 61000)

    # 无 sync 文件 → 原样返回（不因换算失败而误判窗口）
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert coord._map_clip_to_view(str(empty_dir), "cam_2", 1000, 61000) == (1000, 61000)


def test_map_clip_to_view_strict_rejects_missing_sync_authority(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()
    empty_dir = tmp_path / "strict-empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="sync mapping unavailable"):
        coord._map_clip_to_view(str(empty_dir), "cam_2", 1000, 2000, strict=True)


# ---- 回归：clip 窗口必须落盘（否则 child 拿不到窗口，等于跑全片） -----------------

def test_create_job_persists_clip(tmp_path):
    store = JobStore(make_temp_storage(tmp_path))
    job = store.create_job(
        AnalysisJobCreate(
            metadata=make_metadata(),
            videoId="v1",
            calibrationId="cal1",
            clipStartMs=1000,
            clipEndMs=60000,
        )
    )
    assert job.clipStartMs == 1000
    assert job.clipEndMs == 60000


# ---- 回归：Parent viewRuns 运行中也反映 child 实时进度 -----------------------------

def test_live_view_runs_reflects_child_progress(monkeypatch, tmp_path):
    mock_analysis, _ = _coordinator_with_patches(monkeypatch, tmp_path)
    coord = mock_analysis._get_coordinator()
    parent = coord.create_multiview_job(make_multiview_payload())

    child = mock_analysis._JOB_STORE.get(parent.sourceJobs[0].jobId)
    mock_analysis._JOB_STORE.update(
        child.id,
        canonicalStatus="running",
        status="processing",
        displayStatus="processing",
        stage="tracking",
        progress=55,
    )

    runs = coord.live_view_runs(mock_analysis._JOB_STORE.get(parent.id))
    assert runs["cam_1"].status == "running"
    assert runs["cam_1"].stage == "tracking"
    assert runs["cam_1"].progress == 55
    assert runs["cam_2"].status == "queued"

    # get_mock_job 对运行中 Parent 返回实时 viewRuns
    job = mock_analysis.get_mock_job(parent.id)
    assert job.viewRuns["cam_1"].progress == 55
