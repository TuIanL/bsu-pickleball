from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.capture_take import CaptureMode as TakeCaptureMode
from app.models.capture_take import CaptureTake, CaptureTakeStatus, SourceSessionType
from app.models.field_session import (
    CameraSetup,
    FieldSession,
    FieldSessionStatus,
    MatchFormat,
)
from app.models.field_session import (
    CaptureMode as FieldCaptureMode,
)
from app.schemas.video import VideoMetadata
from app.services.job_orchestration import JobStore
from app.services.multiview_coordinator import (
    MultiViewAnalysisCoordinator,
    MultiviewPreflightError,
    PreflightResult,
)
from app.services.storage_service import StorageService
from app.services.video_service import VIDEOS

client = TestClient(app)


def _write_timing_sidecar(media: Path, *, frame_count: int = 101) -> None:
    media.with_name(f"{media.name}.pts.jsonl").write_text(
        "".join(
            f'{json.dumps({"frame_index": index, "pts_seconds": float(index)})}\n'
            for index in range(frame_count)
        ),
        encoding="utf-8",
    )


def _register_video(video_id: str, media: Path) -> None:
    media.write_bytes((video_id.encode("utf-8") + b"-media") * 3)
    _write_timing_sidecar(media)
    metadata = VideoMetadata(
        id=video_id,
        original_filename=f"{video_id}.mp4",
        content_type="video/mp4",
        size_bytes=media.stat().st_size,
        path=str(media),
        source="recording",
        uploaded_at=datetime.now(UTC),
    )
    VIDEOS[video_id] = metadata


def _create_dual_take(isolated_database, tmp_path: Path, *, take_id: str = "take-sync-api") -> tuple[str, Path, str]:
    now = datetime.now(UTC)
    session_dir = tmp_path / take_id
    (session_dir / "metadata").mkdir(parents=True)
    (session_dir / "timeline").mkdir()
    _register_video("video-sync-a", tmp_path / "camera-a.mp4")
    _register_video("video-sync-b", tmp_path / "camera-b.mp4")
    (session_dir / "metadata" / "recording_session.json").write_text(
        json.dumps(
            {
                "registered_video_ids": {"cam_1": "video-sync-a", "cam_2": "video-sync-b"},
                "camera_slots": {
                    "cam_1": {"camera_id": "camera-a"},
                    "cam_2": {"camera_id": "camera-b"},
                },
            }
        ),
        encoding="utf-8",
    )
    db = isolated_database()
    field_session = FieldSession(
        id=f"field-{take_id}",
        title="同步测试",
        venue="测试场",
        court_name="测试场 1",
        capture_mode=FieldCaptureMode.match,
        match_format=MatchFormat.doubles,
        camera_setup=CameraSetup.dual,
        status=FieldSessionStatus.planned,
    )
    take = CaptureTake(
        id=take_id,
        field_session_id=field_session.id,
        capture_mode=TakeCaptureMode.dual,
        source_session_type=SourceSessionType.sync_recording,
        source_session_id=f"sync-{take_id}",
        session_dir=str(session_dir),
        status=CaptureTakeStatus.completed,
        started_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add_all([field_session, take])
    db.commit()
    db.close()
    return take_id, session_dir, f"sync-{take_id}"


def _anchors() -> list[dict[str, object]]:
    return [
        {
            "id": "anchor-1",
            "label": "start",
            "note": "",
            "frame_by_camera": {"camera-a": 0, "camera-b": 0},
            "pts_by_camera": {"camera-a": 0.0, "camera-b": 0.1},
        },
        {
            "id": "anchor-2",
            "label": "middle",
            "note": "",
            "frame_by_camera": {"camera-a": 50, "camera-b": 50},
            "pts_by_camera": {"camera-a": 50.0, "camera-b": 50.1},
        },
        {
            "id": "anchor-3",
            "label": "end",
            "note": "",
            "frame_by_camera": {"camera-a": 100, "camera-b": 100},
            "pts_by_camera": {"camera-a": 100.0, "camera-b": 100.1},
        },
    ]


def _draft_payload(revision: int = 0, *, anchors: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "reference_camera": "camera-a",
        "cameras": ["camera-a", "camera-b"],
        "anchors": anchors if anchors is not None else _anchors(),
        "expected_revision": revision,
    }


def _multiview_payload(take_id: str) -> dict[str, object]:
    return {
        "metadata": {
            "fileName": f"{take_id}.mp4",
            "fileSize": 100,
            "matchTitle": "同步测试",
            "venue": "测试场",
            "matchDate": "2026-08-13",
            "matchFormat": "doubles",
            "cameraAngle": "baseline",
            "athleteLabel": "测试",
            "level": "MVP",
            "capture_take_id": take_id,
        },
        "analysisKind": "multiview",
        "multiview": {
            "referenceViewId": "cam_1",
            "executionMode": "joint_tracking_v2",
            "views": [
                {
                    "viewId": "cam_1",
                    "cameraId": "camera-a",
                    "videoId": "video-sync-a",
                    "calibrationId": "cal-a",
                    "courtOrientation": "identity",
                },
                {
                    "viewId": "cam_2",
                    "cameraId": "camera-b",
                    "videoId": "video-sync-b",
                    "calibrationId": "cal-b",
                    "courtOrientation": "rotate_180",
                },
            ],
        },
    }


def test_sync_anchor_http_lifecycle_and_export_does_not_mutate_status(isolated_database, tmp_path):
    take_id, _session_dir, _source_session_id = _create_dual_take(isolated_database, tmp_path)

    status_response = client.get(f"/api/capture-takes/{take_id}/sync-anchors/status?require_manual=true")
    assert status_response.status_code == 200
    assert status_response.json()["state"] == "required"

    draft_response = client.put(
        f"/api/capture-takes/{take_id}/sync-anchors/draft",
        json=_draft_payload(),
    )
    assert draft_response.status_code == 200
    assert draft_response.json()["revision"] == 1
    assert draft_response.json()["status"]["state"] == "draft"

    restored = client.get(f"/api/capture-takes/{take_id}/sync-anchors/draft")
    assert restored.status_code == 200
    assert restored.json()["draft"]["anchors"][1]["label"] == "middle"

    conflict = client.put(
        f"/api/capture-takes/{take_id}/sync-anchors/draft",
        json=_draft_payload(0),
    )
    assert conflict.status_code == 409
    assert conflict.json() == {
        "code": "revision_conflict",
        "message": "sync anchor revision conflict; current_revision=1",
        "current_revision": 1,
        "issues": [],
    }

    confirmed = client.post(
        f"/api/capture-takes/{take_id}/sync-anchors/confirm",
        json=_draft_payload(1),
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"]["state"] == "confirmed"
    assert confirmed.json()["status"]["revision"] == 1

    before_export = client.get(f"/api/capture-takes/{take_id}/sync-anchors/status")
    exported = client.get(f"/api/capture-takes/{take_id}/sync-anchors/export")
    after_export = client.get(f"/api/capture-takes/{take_id}/sync-anchors/status")
    assert exported.status_code == 200
    assert exported.json()["reference_camera"] == "camera-a"
    assert len(exported.json()["anchors"]) == 3
    assert after_export.json()["state"] == before_export.json()["state"] == "confirmed"
    assert after_export.json()["revision"] == before_export.json()["revision"] == 1


def test_sync_anchor_http_confirm_returns_structured_validation_issues(isolated_database, tmp_path):
    take_id, _session_dir, _source_session_id = _create_dual_take(
        isolated_database, tmp_path, take_id="take-sync-invalid"
    )
    response = client.post(
        f"/api/capture-takes/{take_id}/sync-anchors/confirm",
        json=_draft_payload(0, anchors=_anchors()[:2]),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_failed"
    assert body["issues"]
    assert "anchor_validation" in {issue["code"] for issue in body["issues"]}
    assert client.get(f"/api/capture-takes/{take_id}/sync-anchors/status").json()["state"] == "required"


def test_multiview_http_preflight_blocks_before_parent_or_children(isolated_database, tmp_path):
    take_id, _session_dir, source_session_id = _create_dual_take(
        isolated_database, tmp_path, take_id="take-sync-preflight"
    )
    response = client.post("/api/analysis/jobs", json=_multiview_payload(take_id))

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "multiview_preflight_failed"
    assert any("manual_anchors_required" in issue for issue in body["issues"])
    assert body["diagnostics"]["sync_anchor_status"]["state"] == "required"
    jobs = client.get(f"/api/analysis/jobs?recording_session_id={source_session_id}").json()
    assert all(job["metadata"].get("capture_take_id") != take_id for job in jobs)


def test_confirmed_revision_is_reused_by_two_analysis_parents_and_invalidated_on_media_replace(
    isolated_database,
    tmp_path,
    monkeypatch,
):
    take_id, session_dir, _source_session_id = _create_dual_take(isolated_database, tmp_path, take_id="take-sync-reuse")
    assert client.put(
        f"/api/capture-takes/{take_id}/sync-anchors/draft",
        json=_draft_payload(),
    ).status_code == 200
    assert client.post(
        f"/api/capture-takes/{take_id}/sync-anchors/confirm",
        json=_draft_payload(1),
    ).status_code == 200

    from app.services import multiview_coordinator as coordinator_module

    monkeypatch.setattr(
        coordinator_module,
        "preflight_multiview",
        lambda payload, **kwargs: PreflightResult(ok=True),
    )
    storage = StorageService()
    store = JobStore(storage)
    coordinator = MultiViewAnalysisCoordinator(store, storage=storage)
    payload = _multiview_payload(take_id)
    from app.schemas.analysis import AnalysisJobCreate

    late_payload = payload | {
        "multiview": {**payload["multiview"], "executionMode": "late_fusion_v1"},
    }
    joint_payload = payload | {
        "multiview": {**payload["multiview"], "executionMode": "joint_tracking_v2"},
    }
    first = coordinator.create_multiview_job(AnalysisJobCreate.model_validate(late_payload))
    second = coordinator.create_multiview_job(AnalysisJobCreate.model_validate(joint_payload))
    assert first.syncCalibrationRevision == second.syncCalibrationRevision == 1
    assert len(first.sourceJobs) == 2
    assert second.executionMode == "joint_tracking_v2"
    assert second.sourceJobs == []

    replacement = tmp_path / "camera-a-replacement.mp4"
    _register_video("video-sync-a", replacement)
    invalidated = client.get(f"/api/capture-takes/{take_id}/sync-anchors/status")
    assert invalidated.status_code == 200
    assert invalidated.json()["state"] == "invalidated"
    assert invalidated.json()["revision"] == 1

    jobs_before_failed_create = len(store.list())
    with pytest.raises(MultiviewPreflightError):
        coordinator.create_multiview_job(AnalysisJobCreate.model_validate(payload))
    assert len(store.list()) == jobs_before_failed_create
    history = session_dir / "timeline" / "sync_anchor_history" / "revision-1"
    assert (history / "sync_anchor_confirmation.json").exists()


def test_cli_output_matches_shared_calibration_service(tmp_path):
    payload = {
        "reference_camera": "camera-a",
        "cameras": ["camera-a", "camera-b"],
        "anchors": [
            {"camera-a": 0.0, "camera-b": 0.1},
            {"camera-a": 50.0, "camera-b": 50.1},
            {"camera-a": 100.0, "camera-b": 100.1},
        ],
    }
    input_path = tmp_path / "anchors.json"
    output_path = tmp_path / "calibration.json"
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/calibrate_dual_camera_sync.py", str(input_path), "--output", str(output_path)],
        cwd=Path(__file__).parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    from app.services.dual_camera_sync import build_dual_camera_sync_calibration

    assert json.loads(output_path.read_text(encoding="utf-8")) == build_dual_camera_sync_calibration(payload)
