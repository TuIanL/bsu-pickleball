# Pickleball Vision Backend

This FastAPI backend is the product and research foundation for fixed-camera pickleball video analysis. It keeps the sample/demo report path available for degraded local use, but the primary flow is now durable real-video analysis: upload a match, calibrate the court, enqueue an analysis job, run the worker-backed pipeline, and preserve execution records that can support product debugging and research output.

The backend is intentionally local-first. It uses a lightweight durable job store and local worker runtime before introducing external infrastructure such as Redis, Celery, or distributed GPU scheduling.

## Tech Stack

- Python 3.10+
- FastAPI and Pydantic
- NumPy, Pandas, OpenCV
- Ultralytics YOLO for person-box overlays in real uploaded-video jobs
- Optional multi-target detector boundary for future player-focused model adapters
- Optional MMPose/RTMPose runtime for skeleton overlays
- Local job orchestration with durable JSON records, worker execution, cancellation, and idempotent job submission
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

For daily local development, start both the RTMPose-enabled backend and the
frontend with one command from the repository root:

```bash
npm run app:start
```

This starts the API at `http://localhost:8000`, the frontend at
`http://localhost:5173`, writes logs to `.runtime/logs/`, and records process
IDs under `.runtime/pids/` so the matching stop command can shut them down:

```bash
npm run app:stop
```

On macOS, you can also double-click `start-pickleball.command` and
`stop-pickleball.command` in the repository root.

The startup command enables pose inference by default and sets
`TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=1` for the trusted OpenMMLab RTMPose
checkpoint stored under `models/rtmpose/`.

For manual backend-only debugging, run:

```bash
uvicorn app.main:app --reload
```

The frontend can use:

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
product-review setting for smooth person boxes and skeletons. For slower machines,
use `PICKLEBALL_OVERLAY_FRAME_STRIDE=3` or `5`; for maximum fidelity use `1` and
expect substantially higher YOLO/RTMPose processing cost.

## Job Orchestration

Real analysis jobs are persisted before execution and then claimed by a local worker.
The public API creates, lists, reads, cancels, and deletes jobs; heavy model work runs
behind the worker boundary.

Canonical lifecycle:

```text
queued -> running -> succeeded
                 \-> failed
                 \-> canceled
```

For frontend compatibility, API summaries still expose display statuses such as
`queued`, `processing`, `completed`, `failed`, and `canceled`, plus a
`canonicalStatus` field for the strict state machine.

Each stage record can include:

- start/end timestamps and duration
- progress percentage
- stable error code
- user-facing public message
- internal diagnostic message stored for engineers, not shown directly in UI
- retry count and structured counters such as processed frames or detections

Useful runtime settings:

```bash
PICKLEBALL_ENABLE_JOB_WORKER=true
PICKLEBALL_MAX_CPU_JOBS=1
PICKLEBALL_ENABLE_GPU_JOBS=false
PICKLEBALL_MAX_GPU_JOBS=1
PICKLEBALL_JOB_STAGE_TIMEOUT_SECONDS=0
PICKLEBALL_JOB_MAX_RETRIES=1
```

Default local behavior is conservative: one heavy analysis job at a time. This
prevents one long video or model-heavy run from overwhelming the local service.

Duplicate real-analysis submissions are detected through input/config signatures
covering video reference, calibration reference, frame stride/options, analysis mode,
and model/runtime configuration. Submit `requestNewVersion: true` to intentionally
create a new version for the same input.

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

Ball and paddle detection are intentionally out of scope for the active MVP.
The current pipeline exposes source video, person/tracking overlays, optional
pose overlays, projected player tracks, and movement metrics only. Historical
ball overlay files may still be removed by task deletion, but new jobs do not
generate or expose ball overlay artifacts.

## Action Classification Dataset Export

For machine-learning action classification experiments, use the offline exporter
to turn uploaded or local match videos into target-player crop clips. This path
is separate from the product analysis job flow and is intended for dataset
building and visual QA.

Recommended first pass:

```bash
cd backend
python scripts/export_action_classification_dataset.py ../data/uploads/video.mp4 \
  --output-root ../datasets/action-classification-processed \
  --label forehand \
  --target-fps 20 \
  --roi 0.02,0.30,0.98,0.98 \
  --detector-confidence 0.5 \
  --selection-strategy largest \
  --bbox-expand-scale 1.4 \
  --clip-length 16 \
  --clip-stride 16
```

The exporter writes JPEG frames under
`<output-root>/<label>/<video-stem>_clipNNNN/` and a root `manifest.json` with
source frame numbers, timestamps, ROI coordinates, selected person boxes, crop
boxes, preprocessing settings, and error diagnostics. CLAHE light enhancement is
enabled by default; add `--disable-clahe` for an unenhanced baseline, or
`--denoise` for a light `3x3` GaussianBlur experiment.

## API Surface

- `GET /health`
- `POST /api/videos/upload`
- `GET /api/videos/{video_id}`
- `POST /api/calibrations`
- `GET /api/calibrations/{calibration_id}`
- `POST /api/calibrations/project`
- `POST /api/analysis/jobs`
- `GET /api/analysis/jobs`
- `GET /api/analysis/jobs/{job_id}`
- `POST /api/analysis/jobs/{job_id}/cancel`
- `DELETE /api/analysis/jobs/{job_id}`
- `POST /api/analysis/jobs/delete`
- `GET /api/analysis/jobs/{job_id}/result`
- `GET /api/analysis/jobs/{job_id}/report`
- `GET /api/analysis/jobs/{job_id}/artifacts/tracking-overlay`
- `GET /api/analysis/jobs/{job_id}/artifacts/pose-overlay`

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

Cancel a queued or running job:

```bash
curl -X POST http://localhost:8000/api/analysis/jobs/job-example/cancel
```

## Algorithm Modules

- `app/vision/courtvision_calibration_engine/`: standard court geometry, homography, manual calibration, overlay boundary
- `app/vision/detectors/`: lightweight detector adapter boundaries, including normalized multi-target fixtures
- `app/vision/player_tracking_engine/`: person detector interface, simple tracker, footpoint estimator, player projector
- `app/vision/pickleball_performance_engine/`: distance, speed, kitchen dwell, doubles spacing, heatmap metrics
- `app/services/job_orchestration.py`: durable job store, local queue selector, worker runtime, cancellation token, idempotency signatures
- `app/services/analysis_pipeline.py`: MVP orchestration and JSON result generation

The MVP intentionally avoids ball tracking, hit events, rally segmentation, shot
classification, and tactical semantics. YOLO and tracker integrations can
replace the current interfaces later while preserving player movement metrics.

## Storage

Runtime artifacts live under `backend/data/`:

- `uploads/`: uploaded videos
- `outputs/jobs/`: durable job records with state, timestamps, signatures, and stage telemetry
- `outputs/`: JSON results, reports, overlays, and future visualized videos
- `calibrations/`: manual calibration JSON files
- `tmp/`: temporary frames and intermediate files

These generated files are ignored by git. Model weights should live in the repo-level `models/` directory and are also ignored.

## Research Records

Every completed or failed real job should be useful beyond the product UI. The
durable job record links input video/calibration references, configuration signature,
model/runtime availability, per-stage timing, error codes, and output artifacts. These
records are the basis for reproducible experiments, model comparison, court-calibration
evaluation, movement-metric validation, and later paper or report materials.

Do not claim unavailable research conclusions from current artifacts. The current
real pipeline supports player/person overlays, optional pose overlays, projected
movement tracks, and movement metrics. Ball tracking, hit events, rally segmentation,
shot classification, and tactical semantics remain out of scope until their models
and validation records exist.

## Test

```bash
cd backend
pytest
```

The core tests cover standard court geometry, homography, footpoint projection,
movement metrics, player-focused multi-target schemas, deletion cleanup, and
API smoke behavior. They do not require YOLO weights, CUDA, uploaded sample
videos, or OpenCV runtime usage.
