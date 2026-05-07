## Why

The current backend is useful for product demos, but it still returns immediate mock analysis and does not yet accept real video files, calibration data, or algorithm-stage outputs. We need an MVP backend algorithm foundation now so uploaded fixed-camera pickleball videos can move through a clear, testable pipeline before adding fully automatic ball/event recognition.

## What Changes

- Add a Python vision MVP that reads uploaded videos, stores local artifacts, and exposes video upload, calibration, and analysis task APIs.
- Introduce explicit module boundaries for CourtVision Calibration Engine, Player Tracking Engine, Pickleball Performance Engine, and Analysis Pipeline.
- Define Pydantic schemas for video metadata, manual calibration points, tracking observations, projected player tracks, and performance metrics.
- Implement standard pickleball court geometry in a 20 ft by 44 ft coordinate system, including net, kitchen lines, and service zones.
- Provide initial homography, footpoint projection, and metrics interfaces with lightweight MVP behavior and unit tests.
- Keep the existing frontend-facing analysis job contract compatible while allowing analysis jobs to reference uploaded videos and return mock or partial pipeline results.
- Document installation, local storage conventions, running the FastAPI service, and running pytest.

## Capabilities

### New Capabilities
- `pickleball-algorithm-backend-mvp`: Covers the backend algorithm package structure, video upload, manual court calibration, MVP analysis pipeline, standard court geometry, player tracking interfaces, projected movement metrics, output JSON, and visualized output artifact contracts.

### Modified Capabilities
- `python-vision-backend-foundation`: Extend the backend foundation requirements from reserved adapter boundaries to concrete MVP modules, schemas, storage services, and lightweight tests.
- `video-analysis-job-flow`: Extend analysis job behavior so jobs can be created from uploaded video references and expose status/results produced by the MVP backend pipeline.

## Impact

- Affected code: `backend/app/main.py`, `backend/app/api/`, `backend/app/core/`, `backend/app/schemas/`, `backend/app/services/`, `backend/app/vision/`, `backend/tests/`, and backend documentation.
- APIs: Adds or refines `/health`, video upload, calibration, and analysis job endpoints while preserving existing `/api/analysis/jobs` compatibility for the frontend.
- Dependencies: Adds OpenCV, NumPy, Pandas, pytest, and optional Ultralytics/YOLO tracking dependencies behind interfaces so smoke tests can run without model weights or CUDA.
- Storage: Uses local upload, output, calibration, and temporary artifact directories with generated media excluded from version control.
