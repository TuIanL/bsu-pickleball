from app.schemas.analysis import AnalysisJobSummary, AnalysisStage
from app.services.analysis_progress import (
    aggregate_progress,
    build_stage_snapshot,
    merge_stage_event,
    normalize_stage_snapshot,
    stage_ids,
    validate_stage_snapshot,
)
from app.services.job_orchestration import normalize_job


def test_mode_graphs_keep_report_after_multiview_work():
    assert stage_ids("late_fusion_v1") == (
        "multiview-input-check",
        "multiview-view-a",
        "multiview-view-b",
        "multiview-fusion",
        "multiview-metrics",
        "multiview-visualization",
        "multiview-report",
    )
    assert stage_ids("joint_tracking_v2") == (
        "multiview-input-check",
        "multiview-joint",
        "multiview-ball-analysis",
        "multiview-metrics",
        "multiview-visualization",
        "multiview-report",
    )


def test_joint_active_stage_does_not_activate_report():
    stages = build_stage_snapshot("joint_tracking_v2", "multiview-input-check")
    stages = merge_stage_event(
        stages,
        AnalysisStage(
            id="multiview-joint",
            label="双摄协同跟踪",
            status="active",
            detail="已处理 95%",
            progress=95,
        ),
        "joint_tracking_v2",
    )
    by_id = {stage.id: stage for stage in stages}
    assert by_id["multiview-joint"].status == "active"
    assert by_id["multiview-joint"].progress == 95
    assert by_id["multiview-report"].status == "pending"
    validate_stage_snapshot(stages, "joint_tracking_v2")


def test_weighted_progress_is_monotonic_and_terminal_success_is_100():
    stages = build_stage_snapshot("joint_tracking_v2", "multiview-input-check")
    first = aggregate_progress(stages, "joint_tracking_v2", previous_progress=0)
    stages = merge_stage_event(
        stages,
        AnalysisStage(
            id="multiview-joint",
            label="双摄协同跟踪",
            status="active",
            detail="处理中",
            progress=95,
        ),
        "joint_tracking_v2",
    )
    second = aggregate_progress(stages, "joint_tracking_v2", previous_progress=first)
    assert second > first
    assert aggregate_progress(stages, "joint_tracking_v2", previous_progress=second - 1, terminal_status="succeeded") == 100
    assert aggregate_progress(stages, "joint_tracking_v2", previous_progress=second + 10) == second + 10


def test_late_fusion_aggregates_child_view_progress_without_fusion_credit():
    stages = build_stage_snapshot("late_fusion_v1", "multiview-input-check")
    stages = merge_stage_event(
        stages,
        AnalysisStage(
            id="multiview-view-a",
            label="A 机位视觉分析",
            status="active",
            detail="A",
            progress=80,
        ),
        "late_fusion_v1",
    )
    progress = aggregate_progress(
        stages,
        "late_fusion_v1",
        view_progress={"cam_1": {"status": "running", "progress": 80}, "cam_2": {"status": "queued", "progress": 10}},
    )
    assert progress < 50
    assert next(stage for stage in stages if stage.id == "multiview-fusion").status == "pending"


def test_unknown_internal_pipeline_stage_is_not_exposed_in_top_level_snapshot():
    stages = build_stage_snapshot("single_view", "video-read")
    normalized = normalize_stage_snapshot(
        stages
        + [
            AnalysisStage(
                id="ball-trajectory",
                label="球轨迹",
                status="done",
                detail="内部诊断",
                progress=100,
            )
        ],
        "single_view",
    )
    assert "ball-trajectory" not in {stage.id for stage in normalized}
    assert len(normalized) == 12


def test_legacy_joint_job_is_read_as_joint_graph_without_empty_view_runs():
    job = AnalysisJobSummary(
        id="job-legacy-joint",
        status="processing",
        canonicalStatus="running",
        stage="multiview-joint",
        progress=30,
        createdAt="2026-08-23T00:00:00Z",
        updatedAt="2026-08-23T00:00:00Z",
        metadata={
            "fileName": "joint.mp4",
            "matchTitle": "Legacy joint",
            "venue": "Test court",
            "matchDate": "2026-08-23",
            "matchFormat": "doubles",
            "cameraAngle": "baseline",
            "athleteLabel": "Test",
            "level": "MVP",
        },
        executionMode="joint_tracking_v2",
        analysisKind="multiview",
        viewRuns={},
        stages=[
            AnalysisStage(id="video-read", label="读取视频", status="done", detail="done", progress=100),
            AnalysisStage(id="multiview-joint", label="双摄协同跟踪", status="active", detail="running", progress=95),
            AnalysisStage(id="report", label="报告生成", status="pending", detail="pending", progress=0),
        ],
    )
    normalized = normalize_job(job)
    assert [stage.id for stage in normalized.stages] == list(stage_ids("joint_tracking_v2"))
    assert normalized.stages[1].status == "active"
    assert normalized.stages[-1].status == "pending"
    assert normalized.viewRuns is None
