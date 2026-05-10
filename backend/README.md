# Pickleball Vision Backend MVP

This FastAPI backend is the MVP algorithm foundation for fixed-camera pickleball video analysis. It keeps the existing mock report contract for the frontend while adding video upload, manual court calibration, standard court geometry, footpoint projection, movement metrics, and a model-free `AnalysisPipeline`.

## Tech Stack

- Python 3.10+
- FastAPI and Pydantic
- NumPy, Pandas, OpenCV
- Ultralytics YOLO for person-box overlays in real uploaded-video jobs
- pytest for unit tests

## Install

```bash
cd backend
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

For editable package installs:

```bash
pip install -e ".[dev]"
```

## Run

```bash
uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. The frontend can use:

```bash
VITE_ANALYSIS_API_URL=http://localhost:8000 npm run dev
```

YOLO person detection is enabled by default for calibrated uploaded videos. To force the
model-free degraded path, start the backend with:

```bash
PICKLEBALL_ENABLE_MODEL_INFERENCE=false uvicorn app.main:app --reload
```

RTMPose skeleton overlays remain optional until local MMPose/RTMPose assets are configured:

```bash
PICKLEBALL_ENABLE_POSE_INFERENCE=true \
PICKLEBALL_RTMPOSE_CONFIG_PATH=/path/to/rtmpose_config.py \
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH=/path/to/rtmpose_checkpoint.pth \
uvicorn app.main:app --reload
```

## API Surface

- `GET /health`
- `POST /api/videos/upload`
- `GET /api/videos/{video_id}`
- `POST /api/calibrations`
- `GET /api/calibrations/{calibration_id}`
- `POST /api/calibrations/project`
- `POST /api/analysis/jobs`
- `GET /api/analysis/jobs/{job_id}`
- `GET /api/analysis/jobs/{job_id}/result`
- `GET /api/analysis/jobs/{job_id}/report`

## Example Requests

Upload a video:

```bash
curl -F "file=@sample.mp4" http://localhost:8000/api/videos/upload
```

Create a manual calibration:

```bash
curl -X POST http://localhost:8000/api/calibrations \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "video-example",
    "keypoints": [
      {"name": "near_left", "image": {"x": 100, "y": 900}, "court": {"x": 0, "y": 0}},
      {"name": "near_right", "image": {"x": 900, "y": 900}, "court": {"x": 20, "y": 0}},
      {"name": "far_right", "image": {"x": 760, "y": 120}, "court": {"x": 20, "y": 44}},
      {"name": "far_left", "image": {"x": 240, "y": 120}, "court": {"x": 0, "y": 44}}
    ]
  }'
```

Create a metadata-only demo job:

```bash
curl -X POST http://localhost:8000/api/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "metadata": {
      "fileName": "demo.mp4",
      "fileSize": 1234,
      "matchTitle": "MVP Test Match",
      "venue": "Test Court",
      "matchDate": "2026-05-07",
      "matchFormat": "doubles",
      "cameraAngle": "elevated",
      "athleteLabel": "Player A",
      "level": "MVP"
    }
  }'
```

Create a pipeline-backed job by including `videoId` and optional `calibrationId`:

```bash
curl -X POST http://localhost:8000/api/analysis/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "videoId": "video-example",
    "calibrationId": "calib-example",
    "metadata": {
      "fileName": "demo.mp4",
      "fileSize": 1234,
      "matchTitle": "Pipeline MVP Match",
      "venue": "Test Court",
      "matchDate": "2026-05-07",
      "matchFormat": "doubles",
      "cameraAngle": "elevated",
      "athleteLabel": "Player A",
      "level": "MVP"
    }
  }'
```

## Algorithm Modules

- `app/vision/courtvision_calibration_engine/`: standard court geometry, homography, manual calibration, overlay boundary
- `app/vision/player_tracking_engine/`: person detector interface, simple tracker, footpoint estimator, player projector
- `app/vision/pickleball_performance_engine/`: distance, speed, kitchen dwell, doubles spacing, heatmap metrics
- `app/services/analysis_pipeline.py`: MVP orchestration and JSON result generation

The MVP intentionally avoids automatic ball detection, hit events, rally segmentation, and tactical semantics. YOLO and tracker integrations can replace the current interfaces later.

## Storage

Runtime artifacts live under `backend/data/`:

- `uploads/`: uploaded videos
- `outputs/`: JSON results and future visualized videos
- `calibrations/`: manual calibration JSON files
- `tmp/`: temporary frames and intermediate files

These generated files are ignored by git. Model weights should live in the repo-level `models/` directory and are also ignored.

## Test

```bash
cd backend
pytest
```

The core tests cover standard court geometry, homography, footpoint projection, movement metrics, and API smoke behavior. They do not require YOLO weights, CUDA, uploaded sample videos, or OpenCV runtime usage.
