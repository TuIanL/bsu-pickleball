from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analysis import AnalysisJobCreate
from app.services.mock_analysis import JOBS, REPORTS, RESULTS, create_analysis_job
from app.services.video_service import VIDEOS


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
