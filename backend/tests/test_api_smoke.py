from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisJobCreate
from app.schemas.pose import PoseKeypoint, PoseOverlayFrame, PoseSubject
from app.schemas.tracking import Detection
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.mock_analysis import JOBS, REPORTS, RESULTS, create_analysis_job
from app.services.storage_service import StorageService
from app.services.video_service import VIDEOS
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector
from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metadata_only_analysis_job_still_completes():
    payload = {
        "metadata": {
            "fileName": "demo.mp4",
            "fileSize": 1234,
            "matchTitle": "MVP Test Match",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        }
    }

    response = client.post("/api/analysis/jobs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["metadata"]["matchTitle"] == "MVP Test Match"


def test_manual_calibration_endpoint_creates_and_reads_result():
    payload = {
        "video_id": "video-api-test",
        "image_points": {
            "top_left": [0, 0],
            "top_right": [100, 0],
            "bottom_right": [100, 200],
            "bottom_left": [0, 200],
        },
    }

    create_response = client.post("/calibration/manual", json=payload)

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["calibration_id"].startswith("calib-")
    assert created["court_coordinate_system"] == {"unit": "feet", "width": 20.0, "length": 44.0}
    assert created["quality"]["status"] == "ok"
    assert len(created["homography"]) == 3
    assert len(created["inverse_homography"]) == 3

    read_response = client.get(f"/calibration/{created['calibration_id']}")

    assert read_response.status_code == 200
    read_body = read_response.json()
    assert read_body["calibration_id"] == created["calibration_id"]
    assert read_body["video_id"] == "video-api-test"
    assert len(read_body["keypoints"]) == 4


def test_manual_calibration_endpoint_rejects_bad_geometry():
    payload = {
        "image_points": {
            "top_left": [0, 0],
            "top_right": [1, 1],
            "bottom_right": [2, 2],
            "bottom_left": [3, 3],
        },
    }

    response = client.post("/calibration/manual", json=payload)

    assert response.status_code == 400


def test_video_upload_persists_metadata_after_cache_miss():
    response = client.post(
        "/api/videos/upload",
        files={"file": ("smoke.mp4", b"not-a-real-video", "video/mp4")},
    )

    assert response.status_code == 200
    video = response.json()["video"]
    assert video["id"].startswith("video-")
    assert video["original_filename"] == "smoke.mp4"

    VIDEOS.pop(video["id"], None)

    read_response = client.get(f"/api/videos/{video['id']}")

    assert read_response.status_code == 200
    assert read_response.json()["id"] == video["id"]

    stream_response = client.get(f"/api/videos/{video['id']}/stream")

    assert stream_response.status_code == 200
    assert stream_response.content == b"not-a-real-video"


def test_pipeline_backed_job_lifecycle_and_raw_result():
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("limited.mp4", b"not-a-real-video", "video/mp4")},
    )
    video_id = upload_response.json()["video"]["id"]
    deferred = DeferredTasks()
    payload = AnalysisJobCreate(
        videoId=video_id,
        metadata={
            "fileName": "limited.mp4",
            "fileSize": 16,
            "matchTitle": "Lifecycle Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
        frameStride=5,
    )

    job = create_analysis_job(payload, background_tasks=deferred)

    assert job.status == "queued"
    not_ready = client.get(f"/api/analysis/jobs/{job.id}/result")
    assert not_ready.status_code == 200
    assert not_ready.json()["status"] == "queued"

    deferred.run_all()

    completed = client.get(f"/api/analysis/jobs/{job.id}")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["analysisMode"] == "limited"

    result = client.get(f"/api/analysis/jobs/{job.id}/result")
    assert result.status_code == 200
    result_body = result.json()
    assert result_body["job_id"] == job.id
    assert result_body["status"] == "completed"
    assert result_body["video_id"] == video_id
    assert any(stage["id"] == "projection" for stage in result_body["stages"])

    JOBS.pop(job.id, None)
    REPORTS.pop(job.id, None)
    RESULTS.pop(job.id, None)

    assert client.get(f"/api/analysis/jobs/{job.id}").json()["id"] == job.id
    assert client.get(f"/api/analysis/jobs/{job.id}/report").json()["jobId"] == job.id
    assert client.get(f"/api/analysis/jobs/{job.id}/result").json()["job_id"] == job.id


def test_pipeline_generates_tracking_and_pose_overlay_artifacts(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=StaticPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-overlay-test",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.source_video_url == f"/api/videos/{video_id}/stream"
    assert result.artifacts.tracking_overlay_url == "/api/analysis/jobs/job-overlay-test/artifacts/tracking-overlay"
    assert result.artifacts.pose_overlay_url == "/api/analysis/jobs/job-overlay-test/artifacts/pose-overlay"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_status == "available"
    assert any(stage.id == "pose" and stage.status == "done" for stage in result.stages)

    storage = StorageService()
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-overlay-test"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-overlay-test"))
    assert tracking_overlay["frames"][0]["detections"][0]["track_id"] == "1"
    assert pose_overlay["frames"][0]["subjects"][0]["keypoints"][0]["name"] == "nose"


def test_pipeline_filters_low_confidence_people_from_overlay_and_pose_inputs(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("filtered-overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]
    pose_estimator = RecordingPoseEstimator()

    result = AnalysisPipeline(
        detector=PlayerAndLowConfidenceSpectatorDetector(),
        pose_estimator=pose_estimator,
        frame_stride=1,
    ).run(
        job_id="job-filtered-overlay",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert len(result.tracks) == 3
    assert len(result.stages) > 0

    storage = StorageService()
    tracking_result = storage.read_json(storage.tracking_json_path("job-filtered-overlay"))
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-filtered-overlay"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-filtered-overlay"))
    overlay_track_ids = {
        detection["track_id"]
        for frame in tracking_overlay["frames"]
        for detection in frame["detections"]
    }
    pose_track_ids = {
        subject["track_id"]
        for frame in pose_overlay["frames"]
        for subject in frame["subjects"]
    }

    assert len(tracking_result["detections"]) == 6
    assert {track["track_id"] for track in tracking_result["tracks"]} == {1, 2}
    assert overlay_track_ids == {"1"}
    assert pose_track_ids == {"1"}
    assert pose_estimator.subject_track_ids == [["1"], ["1"], ["1"]]
    assert "主要球员" in (result.artifacts.tracking_overlay_detail or "")


def test_pipeline_keeps_high_confidence_line_out_players_for_overlay_and_pose(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("line-out-overlay.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]
    pose_estimator = RecordingPoseEstimator()

    result = AnalysisPipeline(
        detector=HighConfidenceLineOutDetector(),
        pose_estimator=pose_estimator,
        frame_stride=1,
    ).run(
        job_id="job-line-out-overlay",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.tracks == []

    storage = StorageService()
    tracking_result = storage.read_json(storage.tracking_json_path("job-line-out-overlay"))
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-line-out-overlay"))
    pose_overlay = storage.read_json(storage.pose_overlay_json_path("job-line-out-overlay"))
    overlay_track_ids = {
        detection["track_id"]
        for frame in tracking_overlay["frames"]
        for detection in frame["detections"]
    }
    pose_track_ids = {
        subject["track_id"]
        for frame in pose_overlay["frames"]
        for subject in frame["subjects"]
    }

    assert len(tracking_result["detections"]) == 3
    assert len(tracking_result["positions"]) == 3
    assert all(position["valid"] is False for position in tracking_result["positions"])
    assert overlay_track_ids == {"1"}
    assert pose_track_ids == {"1"}
    assert pose_estimator.subject_track_ids == [["1"], ["1"], ["1"]]


def test_pipeline_does_not_advertise_empty_pose_keypoints(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("empty-pose.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=EmptyPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-empty-pose",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "未生成骨架关节" in (result.artifacts.pose_overlay_detail or "")
    assert any(stage.id == "pose" and stage.status == "skipped" for stage in result.stages)


def test_pipeline_reports_pose_failure_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("failing-pose.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=FailingPoseEstimator(),
        frame_stride=1,
    ).run(
        job_id="job-failing-pose",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "mmpose missing" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_missing_rtmpose_assets_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("missing-assets.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=RTMPose26Adapter(
            config_path=str(tmp_path / "missing_config.py"),
            checkpoint_path=str(tmp_path / "missing_checkpoint.pth"),
        ),
        frame_stride=1,
    ).run(
        job_id="job-missing-pose-assets",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "RTMPose config not found" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_unsupported_pose_schema_without_losing_tracking_overlay(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("bad-schema.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=StaticDetector(),
        pose_estimator=RTMPose26Adapter(
            config_path=None,
            checkpoint_path=None,
            keypoint_schema="coco17",
        ),
        frame_stride=1,
    ).run(
        job_id="job-bad-pose-schema",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.status == "completed"
    assert result.artifacts.tracking_overlay_status == "available"
    assert result.artifacts.pose_overlay_url is None
    assert result.artifacts.pose_overlay_status == "unavailable"
    assert "Unsupported RTMPose keypoint schema" in (result.artifacts.pose_overlay_detail or "")


def test_pipeline_reports_unavailable_overlay_when_yolo_is_disabled(tmp_path):
    video_bytes = make_test_video_bytes(tmp_path)
    upload_response = client.post(
        "/api/videos/upload",
        files={"file": ("disabled.avi", video_bytes, "video/avi")},
    )
    assert upload_response.status_code == 200
    video_id = upload_response.json()["video"]["id"]
    calibration_response = client.post(
        "/calibration/manual",
        json={
            "video_id": video_id,
            "image_points": {
                "top_left": [0, 0],
                "top_right": [96, 0],
                "bottom_right": [96, 96],
                "bottom_left": [0, 96],
            },
        },
    )
    assert calibration_response.status_code == 200
    calibration_id = calibration_response.json()["calibration_id"]

    result = AnalysisPipeline(
        detector=EmptyPersonDetector(),
        frame_stride=1,
    ).run(
        job_id="job-overlay-disabled",
        video_id=video_id,
        calibration_id=calibration_id,
        frame_stride=1,
    )

    assert result.artifacts.tracking_overlay_status == "unavailable"
    assert "YOLO 人体检测未启用" in (result.artifacts.tracking_overlay_detail or "")
    assert any(stage.id == "detection" and stage.status == "skipped" for stage in result.stages)
    assert any(stage.id == "tracking" and stage.status == "skipped" for stage in result.stages)

    storage = StorageService()
    tracking_overlay = storage.read_json(storage.tracking_overlay_json_path("job-overlay-disabled"))
    assert tracking_overlay["status"] == "unavailable"
    assert "YOLO 人体检测未启用" in tracking_overlay["detail"]


def test_analysis_artifact_endpoint_returns_browser_safe_json():
    payload = AnalysisJobCreate(
        metadata={
            "fileName": "artifact.mp4",
            "fileSize": 16,
            "matchTitle": "Artifact Test",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
    )
    job = create_analysis_job(payload)
    storage = StorageService()
    storage.write_json(
        storage.tracking_overlay_json_path(job.id),
        {
            "job_id": job.id,
            "video_id": "video-artifact",
            "status": "no_detections",
            "detail": "test artifact",
            "source": {"width": 96, "height": 96},
            "fps": 5,
            "frame_count": 1,
            "processed_frame_count": 1,
            "frame_stride": 1,
            "frames": [],
        },
    )

    response = client.get(f"/api/analysis/jobs/{job.id}/artifacts/tracking-overlay")

    assert response.status_code == 200
    assert response.json()["detail"] == "test artifact"


def test_analysis_job_with_missing_video_fails_cleanly():
    payload = {
        "videoId": "video-does-not-exist",
        "metadata": {
            "fileName": "missing.mp4",
            "fileSize": 16,
            "matchTitle": "Missing Video",
            "venue": "Test Court",
            "matchDate": "2026-05-07",
            "matchFormat": "doubles",
            "cameraAngle": "elevated",
            "athleteLabel": "Player A",
            "level": "MVP",
        },
    }

    response = client.post("/api/analysis/jobs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["errorMessage"] == "Uploaded video not found"


class DeferredTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args, **kwargs):
        self.tasks.append((fn, args, kwargs))

    def run_all(self):
        for fn, args, kwargs in self.tasks:
            fn(*args, **kwargs)


class StaticDetector:
    def detect_frame(self, frame, frame_index):
        return [Detection(bbox=[18.0, 16.0, 48.0, 82.0], confidence=0.91)]


class PlayerAndLowConfidenceSpectatorDetector:
    def detect_frame(self, frame, frame_index):
        return [
            Detection(bbox=[18.0, 16.0, 48.0, 82.0], confidence=0.91),
            Detection(bbox=[100.0, 16.0, 130.0, 82.0], confidence=0.42),
        ]


class HighConfidenceLineOutDetector:
    def detect_frame(self, frame, frame_index):
        return [Detection(bbox=[100.0, 16.0, 130.0, 82.0], confidence=0.88)]


class StaticPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subjects[0].track_id or "1",
                    bbox=subjects[0].bbox,
                    confidence=0.9,
                    keypoints=[
                        PoseKeypoint(name="nose", x=32, y=22, confidence=0.95),
                        PoseKeypoint(name="left_shoulder", x=25, y=38, confidence=0.95),
                        PoseKeypoint(name="right_shoulder", x=40, y=38, confidence=0.95),
                    ],
                )
            ],
        )


class RecordingPoseEstimator:
    def __init__(self):
        self.subject_track_ids = []

    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        self.subject_track_ids.append([subject.track_id for subject in subjects])
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subject.track_id or "unknown",
                    bbox=subject.bbox,
                    confidence=0.9,
                    keypoints=[PoseKeypoint(name="nose", x=32, y=22, confidence=0.95)],
                )
                for subject in subjects
            ],
        )


class EmptyPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        return PoseOverlayFrame(
            frame_index=frame_index,
            timestamp_seconds=timestamp_seconds,
            subjects=[
                PoseSubject(
                    track_id=subjects[0].track_id or "1",
                    bbox=subjects[0].bbox,
                    confidence=0.9,
                    keypoints=[],
                )
            ],
        )


class FailingPoseEstimator:
    def estimate_frame(self, frame, subjects, frame_index, timestamp_seconds):
        raise RuntimeError("mmpose missing")


def make_test_video_bytes(tmp_path):
    import cv2  # type: ignore
    import numpy as np

    path = tmp_path / "overlay.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (96, 96))
    for _ in range(3):
        frame = np.zeros((96, 96, 3), dtype=np.uint8)
        frame[16:82, 18:48] = (255, 255, 255)
        writer.write(frame)
    writer.release()
    return path.read_bytes()
