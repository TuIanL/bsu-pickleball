## Context

The repository already has a lightweight FastAPI backend in `backend/` that exposes `/health` and mock analysis job/report endpoints consumed by the React frontend. It also has early adapter boundaries under `backend/app/vision/`, but those boundaries are not yet shaped around the requested pickleball MVP: fixed-camera video upload, manual or semi-manual court calibration, homography into a 20 ft by 44 ft court coordinate system, person tracking, footpoint projection, movement metrics, JSON output, and visualized video artifacts.

This design evolves the existing `backend/` project rather than creating a disconnected `pickleball_vision_backend/` root. The implementation should preserve the frontend-facing analysis job contract while adding the clearer module names requested by the algorithm plan.

## Goals / Non-Goals

**Goals:**
- Provide a runnable FastAPI backend with health, video upload, calibration, and analysis task endpoints.
- Establish the MVP algorithm architecture:
  - CourtVision Calibration Engine
  - Player Tracking Engine
  - Pickleball Performance Engine
  - Analysis Pipeline
- Use Pydantic schemas to make video, calibration, tracking, and metric data explicit and testable.
- Implement standard pickleball court geometry and homography helpers with deterministic unit tests.
- Keep heavy model integration optional so pytest and API smoke checks can run without YOLO weights, CUDA, or sample videos.
- Return mock or partial analysis results through a real pipeline boundary so later YOLO/ByteTrack integration can replace internals without changing API routes.

**Non-Goals:**
- Fully automatic court-line recognition.
- Ball detection, shot detection, hit timing, rally segmentation, or tactical semantics.
- Production-grade asynchronous job queues, distributed storage, authentication, authorization, or database persistence.
- High-accuracy multi-camera fusion or pose-based biomechanics.

## Decisions

### Decision 1: Evolve `backend/` instead of creating a second backend root

Use `backend/app/` as the implementation root and create the requested modules under that existing package. The conceptual package name remains the pickleball vision backend, but the physical location stays aligned with the current repository.

Alternatives considered:
- Create `pickleball_vision_backend/` at the repo root. This matches the prompt literally, but it would duplicate the already-working FastAPI app and leave the existing frontend integration behind.
- Rename `backend/` to `pickleball_vision_backend/`. This creates churn across docs, commands, and frontend environment assumptions.

### Decision 2: Keep the API compatible while adding explicit video and calibration routes

Keep existing `/api/analysis/jobs` routes available and add dedicated route modules for video upload and calibration. Analysis job creation can accept either existing metadata-only payloads for demo compatibility or a new uploaded video reference for pipeline-backed jobs.

The route structure should be:
- `GET /health`
- `POST /api/videos/upload`
- `GET /api/videos/{video_id}`
- `POST /api/calibrations`
- `GET /api/calibrations/{calibration_id}`
- `POST /api/analysis/jobs`
- `GET /api/analysis/jobs/{job_id}`
- `GET /api/analysis/jobs/{job_id}/result` for algorithm JSON
- `GET /api/analysis/jobs/{job_id}/report` for the existing frontend report contract

### Decision 3: Model standard court geometry in feet

The canonical court coordinate system uses feet:
- x: `0` to `20`
- y: `0` to `44`
- net: `y = 22`
- near kitchen line: `y = 15`
- far kitchen line: `y = 29`

Court geometry helpers should produce named points, lines, and zones for net, non-volley zones, left/right service boxes, and total court bounds. This keeps homography and metrics independent from image resolution.

### Decision 4: Manual calibration first, homography as the central mapping

The MVP accepts manually clicked image points matched to canonical court points. Homography computation should require at least four non-collinear point correspondences and expose validation errors for insufficient or degenerate inputs.

Alternatives considered:
- Automatic court detection first. This is attractive long term, but it is too brittle for MVP because videos vary in lighting, line visibility, and camera angle.
- Hard-coded camera presets. This is fast for demos but fails when the venue or camera changes.

### Decision 5: Use replaceable tracking interfaces with a lightweight default

Define `PersonDetector`, `MultiObjectTracker`, `FootpointEstimator`, and `PlayerProjector` interfaces. The default MVP may return no detections or deterministic mock tracks unless optional YOLO/Ultralytics dependencies are available. This lets route and metrics tests pass before model setup.

Later YOLOv8n/YOLO11n and ByteTrack or BoT-SORT can replace these internals while keeping normalized detection and track schemas stable.

### Decision 6: Compute simple movement metrics from projected footpoints

The first metrics should be deterministic and easy to test:
- total movement distance per player
- per-frame and aggregate speed
- kitchen-zone dwell time
- simple court heatmap bins
- doubles spacing when two players on the same side are visible

Metrics should accept projected court coordinates and timestamps rather than raw video frames, keeping them decoupled from detector quality.

### Decision 7: Store local artifacts through a storage service

Use local directories under `backend/data/` or existing repo storage conventions, with configurable paths:
- uploads
- outputs
- calibrations
- temporary files

Generated videos, JSON outputs, model weights, and uploads must remain untracked. Storage metadata can stay in memory or JSON files for the MVP.

## Risks / Trade-offs

- Manual calibration can be inaccurate → validate point counts, preserve clicked points in JSON, and expose clear errors for degenerate homographies.
- Optional YOLO dependencies can make installation heavy → split lightweight API/test dependencies from optional vision extras and keep default tests model-free.
- In-memory job state disappears on restart → document this as MVP behavior and isolate persistence behind `StorageService` so file or database persistence can be added later.
- Existing frontend currently sends metadata only → keep metadata-only job creation working while adding upload-backed job creation.
- Visualized output video can be expensive → make overlay generation part of the pipeline interface but allow MVP jobs to return a placeholder or skipped artifact when no real frames are processed.

## Migration Plan

1. Add new backend modules and schemas without removing existing routes.
2. Move or wrap the current mock analysis service behind `AnalysisPipeline` so existing frontend flows still complete.
3. Add video upload and calibration APIs alongside existing analysis routes.
4. Add unit tests for geometry, homography, projection, and metrics before introducing optional model dependencies.
5. Update README with installation, running, testing, and storage guidance.

Rollback is straightforward because existing mock endpoints remain compatible; disabling the new routes or pipeline wrapper returns the backend to the prior demo-only behavior.

## Open Questions

- Should uploaded video IDs be referenced by the existing frontend upload page in this change, or should frontend multipart upload integration be handled in a follow-up?
- Should local storage live under `backend/data/` to match the requested structure, or under root `storage/` to match current repository conventions?
- Do we want synchronous MVP processing inside the request cycle, or a background task abstraction that still runs in-process for now?
