# Pickleball Vision Backend MVP

This FastAPI backend is the MVP algorithm foundation for fixed-camera pickleball video analysis. It keeps the existing mock report contract for the frontend while adding video upload, manual court calibration, standard court geometry, footpoint projection, movement metrics, and a model-free `AnalysisPipeline`.

## Tech Stack

- Python 3.10+
- FastAPI and Pydantic
- NumPy, Pandas, OpenCV
- Ultralytics YOLO for person-box overlays in real uploaded-video jobs
- Optional MMPose/RTMPose runtime for skeleton overlays
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

For true RTMPose skeleton validation, use a Python 3.10+ environment and install
the optional pose runtime after the base backend dependencies. Choose the
PyTorch package that matches your machine first, then install MMCV with MIM so
the wheel matches your PyTorch/CUDA platform:

```bash
cd backend
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev,vision,pose]"
python -m pip install openmim
python -m mim install "mmcv>=2.0.1,<2.2.0"
```

On CPU-only machines set `PICKLEBALL_RTMPOSE_DEVICE=cpu`. On compatible
NVIDIA/CUDA machines use a device such as `cuda:0` after confirming PyTorch can
see CUDA:

```bash
python - <<'PY'
import torch
print(torch.__version__)
print(torch.cuda.is_available())
print(torch.version.cuda)
PY
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

Real-video overlay sampling defaults to `PICKLEBALL_OVERLAY_FRAME_STRIDE=2`, which
produces 30 overlay samples per second for 60fps footage. This is the recommended
presentation setting for smooth person boxes and skeletons. For slower machines,
use `PICKLEBALL_OVERLAY_FRAME_STRIDE=3` or `5`; for maximum fidelity use `1` and
expect substantially higher YOLO/RTMPose processing cost.

RTMPose skeleton overlays are enabled for real calibrated jobs when local
MMPose/RTMPose runtime dependencies and model assets are configured. The backend
auto-discovers the repository-local asset layout from `../models/rtmpose/`; set
`PICKLEBALL_ENABLE_POSE_INFERENCE=false` to force tracking-only analysis on
slower machines.

```bash
PICKLEBALL_RTMPOSE_CONFIG_PATH=../models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py \
PICKLEBALL_RTMPOSE_CHECKPOINT_PATH=../models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth \
PICKLEBALL_RTMPOSE_DEVICE=cpu \
TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1 \
uvicorn app.main:app --reload
```

The shorter `RTMPOSE_CONFIG_PATH`, `RTMPOSE_CHECKPOINT_PATH`, and
`RTMPOSE_DEVICE` aliases are also accepted when the project-prefixed variables
are not set.

Validate the RTMPose runtime before running a full video job:

```bash
cd backend
python scripts/validate_rtmpose.py --check-only
python scripts/validate_rtmpose.py \
  --config ../models/rtmpose/configs/body_2d_keypoint/rtmpose/body8/rtmpose-m_8xb512-700e_body8-halpe26-256x192.py \
  --checkpoint ../models/rtmpose/rtmpose-m_simcc-body7_pt-body7-halpe26_700e-256x192-4d3e73dd_20230605.pth \
  --device cpu \
  --bbox 40,24,152,232
```

With PyTorch 2.6+ and trusted OpenMMLab checkpoints, set
`TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` when validating or running pose inference
so the older checkpoint format can load.

Renderable video overlays use primary-player filtering rather than strict
court-line filtering, so athletes remain visible when they step outside the
baseline or sideline. Tune these values when a scene has extra people:

```bash
PICKLEBALL_PRIMARY_PLAYER_MIN_CONFIDENCE=0.65
PICKLEBALL_PRIMARY_PLAYER_MAX_SUBJECTS=4
PICKLEBALL_PRIMARY_PLAYER_COURT_MARGIN_FT=12
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
