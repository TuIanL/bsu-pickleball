"""分析任务删除的磁盘清理测试 —— delete_analysis_job 对 capture job 的完整产物目录清理。

覆盖：
- capture job：`take_dir/analysis/<job_id>/` 整个目录（含 analysis_overlay.mp4、position_visualizations/、
  fused_* 等清单外产物）在删除后消失；
- `take_dir` 下录制资产（视频、timeline/sync_calibration.json）保留；
- 非 capture job：`<outputs_dir>/<job_id>` 输出目录删除，行为不变；
- `_is_safe_artifact_root` 路径安全校验（格式不符时拒绝整树删除）。
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata
from app.services.storage_service import StorageService


def make_temp_storage(tmp_path) -> StorageService:
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
        "matchTitle": "测试比赛",
        "venue": "测试球场",
        "matchDate": "2026-08-08",
        "matchFormat": "doubles",
        "cameraAngle": "baseline",
        "athleteLabel": "球采集",
        "level": "大众进阶",
    }
    fields.update(overrides)
    return AnalysisUploadMetadata(**fields)


def _create_completed_job(mock_analysis, metadata) -> object:
    """创建一个 completed 状态的 demo 分析任务（可被删除）。"""
    job = mock_analysis.create_analysis_job(AnalysisJobCreate(metadata=metadata))
    assert job.status == "completed"
    return job


def _write_recording_assets(take_dir) -> None:
    """写入录制资产（必须保留）。"""
    (take_dir / "174_merged.mp4").write_bytes(b"fake-video")
    timeline = take_dir / "timeline"
    timeline.mkdir(parents=True, exist_ok=True)
    (timeline / "sync_calibration.json").write_text('{"schema_version": 1}', encoding="utf-8")


def _write_job_artifacts(artifact_root, job_id: str) -> None:
    """写入 job 产物（删除后必须消失）。"""
    (artifact_root / "tracking_overlay.json").write_text('{"frames": []}', encoding="utf-8")
    (artifact_root / "analysis_overlay.mp4").write_bytes(b"fake-overlay")
    (artifact_root / "ball_trajectory.json").write_text("[]", encoding="utf-8")
    (artifact_root / "fused_manifest.json").write_text("{}", encoding="utf-8")
    viz = artifact_root / "position_visualizations" / "structured"
    viz.mkdir(parents=True, exist_ok=True)
    (viz / "data.json").write_text("{}", encoding="utf-8")
    # 保留一个「未被删除清单覆盖」的文件名，确保整树删除真正生效
    (artifact_root / f"{job_id}_leftover.bin").write_bytes(b"leftover")


def test_delete_capture_job_removes_full_artifact_dir_preserves_recording(monkeypatch, tmp_path):
    from app.services import mock_analysis

    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    mock_analysis._sync_orchestration_storage()

    take_dir = tmp_path / "take"
    job = _create_completed_job(mock_analysis, make_metadata(capture_take_id="CT_001"))
    storage.register_capture_job(job.id, take_dir)
    artifact_root = take_dir / "analysis" / job.id
    _write_recording_assets(take_dir)
    _write_job_artifacts(artifact_root, job.id)
    assert artifact_root.exists()

    result = mock_analysis.delete_analysis_job(job.id)
    assert result.status == "deleted"

    # job 记录与产物目录全部清除
    assert mock_analysis.get_mock_job(job.id) is None
    assert not artifact_root.exists()
    # 录制资产保留
    assert (take_dir / "174_merged.mp4").exists()
    assert (take_dir / "timeline" / "sync_calibration.json").exists()
    assert take_dir.exists()


def test_delete_non_capture_job_removes_outputs_dir(monkeypatch, tmp_path):
    from app.services import mock_analysis

    storage = make_temp_storage(tmp_path)
    monkeypatch.setattr("app.services.mock_analysis._STORAGE", storage)
    mock_analysis._sync_orchestration_storage()

    job = _create_completed_job(mock_analysis, make_metadata())
    # 非 capture job：产物在 outputs_dir/<job_id>
    outputs_root = storage.outputs_dir / job.id
    outputs_root.mkdir(parents=True, exist_ok=True)
    (outputs_root / "projection_debug.jsonl").write_text("line\n", encoding="utf-8")
    assert outputs_root.exists()

    result = mock_analysis.delete_analysis_job(job.id)
    assert result.status == "deleted"
    assert not outputs_root.exists()
    assert mock_analysis.get_mock_job(job.id) is None


def test_is_safe_artifact_root_rejects_unsafe_paths(tmp_path):
    from app.services import mock_analysis

    storage = make_temp_storage(tmp_path)
    outputs_dir = storage.outputs_dir

    # 合法：outputs_dir/<job_id>
    assert mock_analysis._is_safe_artifact_root(outputs_dir / "job-abcdef0123", "job-abcdef0123", outputs_dir)
    # 合法：<take>/analysis/<job_id>（含非 hex 的 job 后缀，仍属合法产物目录）
    assert mock_analysis._is_safe_artifact_root(tmp_path / "take" / "analysis" / "job-abcdef0123", "job-abcdef0123", outputs_dir)
    assert mock_analysis._is_safe_artifact_root(tmp_path / "take" / "analysis" / "job-delete-completed", "job-delete-completed", outputs_dir)

    # 非法：不以 job- 前缀开头
    assert not mock_analysis._is_safe_artifact_root(outputs_dir / "not-a-job", "not-a-job", outputs_dir)
    assert not mock_analysis._is_safe_artifact_root(tmp_path / "take" / "analysis" / "not-a-job", "not-a-job", outputs_dir)
    # 非法：None / 空
    assert not mock_analysis._is_safe_artifact_root(None, "job-abcdef0123", outputs_dir)
    # 非法：根路径不是 job 目录（例如 take 本身 / analysis 目录本身）
    assert not mock_analysis._is_safe_artifact_root(tmp_path / "take", "job-abcdef0123", outputs_dir)
    assert not mock_analysis._is_safe_artifact_root(tmp_path / "take" / "analysis", "job-abcdef0123", outputs_dir)
