from fastapi.testclient import TestClient

from app.main import app


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
