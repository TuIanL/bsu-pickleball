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
