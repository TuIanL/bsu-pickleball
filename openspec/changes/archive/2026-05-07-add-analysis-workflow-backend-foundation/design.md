## Context

The current app is a Vite + React + TypeScript front-end prototype. It renders the overview, visual analysis workspace, report pages, training page, and hardware page from local TypeScript mock data. This is appropriate for early presentation, but the next phase needs a real video-analysis flow where users upload match footage, wait for processing, and open generated analysis results.

The intended algorithm direction includes YOLO11-style object detection/tracking and RTMPose26-style human pose estimation. Those tools have different runtime requirements from the front-end demo: Python, OpenCV, PyTorch-related dependencies, model weights, uploaded video files, generated artifacts, and potentially GPU-backed workers. The foundation should therefore introduce clear backend and data boundaries before the real models are integrated.

## Goals / Non-Goals

**Goals:**

- Add a product flow for creating a video analysis job, tracking its status, and opening completed analysis outputs.
- Add a lightweight Python backend foundation that can run locally during development and return mock analysis results.
- Define stable API and schema boundaries between the React app and backend.
- Keep the first backend implementation small enough to run without YOLO11, RTMPose26, CUDA, or large model downloads.
- Reserve backend modules for future detector, pose, tracking, court-calibration, and event-analysis code.
- Preserve the current presentation-ready demo data as a fallback when no job-specific result exists.

**Non-Goals:**

- Implement real YOLO11 detection, RTMPose26 pose estimation, ball tracking, court calibration, model training, or GPU scheduling in this change.
- Build production authentication, payment, multi-tenant storage, cloud deployment, or user account management.
- Commit model weights, uploaded videos, generated analysis artifacts, or training datasets to version control.
- Replace the existing visual design with a generic admin upload dashboard.
- Guarantee final production API shapes for all future algorithms; this foundation only needs a stable first contract.

## Decisions

### Use a monorepo-style backend folder first

Create a `backend/` directory inside the current project rather than starting a separate repository. The front-end and backend are still tightly coupled around a fast-moving analysis-report contract, so keeping them together reduces coordination cost while the product flow and schema are still changing.

Alternatives considered:

- Separate backend repository: cleaner long-term service ownership, but too heavy before the API contract and algorithm pipeline stabilize.
- Keep everything in the React app: fine for mock data, but unsuitable for Python video processing, file uploads, and model runtime dependencies.

### Use FastAPI-style API boundaries

The backend should expose simple HTTP endpoints for upload, job creation, job status, and report retrieval. FastAPI fits the Python vision stack, supports typed Pydantic schemas, and gives the front-end a realistic integration target.

Alternatives considered:

- Node/Express backend: closer to the current front-end stack, but less natural for OpenCV, PyTorch, YOLO, and MMPose-related work.
- Direct Python scripts run manually: useful for experiments, but not enough for an interactive product flow.

### Model analysis as asynchronous jobs

Video analysis should be represented as a job with states such as `uploaded`, `queued`, `processing`, `failed`, and `completed`. The front-end should poll or refresh status and only open result pages once a report is available.

Alternatives considered:

- Synchronous upload-and-return-report flow: simpler for demos, but unrealistic once videos take tens of seconds or minutes to analyze.
- Full queue system immediately: useful later, but unnecessary before real model execution is added.

### Define an analysis-report contract before real algorithms

The first backend can return mock reports shaped like the current front-end data: match summary, metrics, landing points, routes, movement path, rallies, shot rows, timeline markers, video overlay labels, highlights, coach notes, diagnoses, and training recommendations. Real YOLO11/RTMPose26 output should be transformed into this report contract rather than consumed directly by React components.

Alternatives considered:

- Let each algorithm return its native output to the front end: flexible for experiments, but leaks model internals into UI components and makes model replacement painful.
- Wait to define schemas until the models work: avoids premature schema design, but blocks front-end workflow development.

### Keep algorithm code modular behind adapters

Reserve backend modules for detector, pose estimator, tracker, court calibrator, and event analyzer. YOLO11 and RTMPose26 should enter through adapter-style classes or functions so future model changes do not require API or front-end rewrites.

Alternatives considered:

- Hard-code YOLO11 and RTMPose26 calls inside API routes: faster initially, but couples HTTP behavior to model runtime details.
- Build a complex plugin registry now: more flexible than needed for a student project prototype.

### Exclude large and generated assets from git

Uploaded videos, temporary frames, generated JSON reports, model checkpoints, and training datasets should live under ignored local paths such as `storage/`, `models/`, or documented external paths. The repository should commit code, schemas, small fixtures, and documentation only.

Alternatives considered:

- Commit sample videos and model weights: convenient for one machine, but quickly bloats the repository and creates portability/licensing problems.
- Store everything outside the repo immediately: clean for large assets, but harder for new contributors unless the local folder conventions are documented.

## Risks / Trade-offs

- [Risk] Adding a backend foundation could slow front-end iteration. -> Mitigation: keep mock-data fallback and implement the first API layer with lightweight dependencies only.
- [Risk] The analysis-report contract may change after real YOLO11/RTMPose26 experiments. -> Mitigation: keep schemas explicit, version report payloads if needed, and isolate transformations in backend services.
- [Risk] Python vision dependencies can be difficult to install across machines. -> Mitigation: separate lightweight API dependencies from optional heavy model dependencies and document environment setup clearly.
- [Risk] Users may expect real analysis before algorithms are ready. -> Mitigation: label mock processing/results clearly in development while preserving realistic task states and UI flow.
- [Risk] Job status polling can become brittle if the backend is not running. -> Mitigation: provide front-end empty/error states and keep the current sample report available.
- [Risk] Model weights and uploads can accidentally enter version control. -> Mitigation: add gitignore rules and document storage conventions as part of the foundation.

## Migration Plan

1. Add front-end route and type support for analysis upload, job status, and job-specific result pages while preserving the current overview and demo report fallback.
2. Add the Python backend folder with environment metadata, API entrypoint, schemas, route modules, and mock job/report services.
3. Wire the front end to a small API client abstraction so demo data and backend responses can share the same rendering components.
4. Add ignored local folders or documented paths for uploads, generated reports, temporary processing files, and model weights.
5. Add verification steps for front-end build/lint and backend import or smoke-test commands.

Rollback is straightforward while the backend remains foundational: keep the current local demo data path active, remove backend calls from the front-end API client, and leave the `backend/` folder unused until the next iteration.

## Open Questions

- Should the upload page route be `/upload`, `/analysis/new`, or both with one redirecting to the other?
- Should job-specific visual analysis use `/vision/:jobId` or `/analysis/:jobId/vision`?
- Should report pages evolve to `/reports/:reportId/:type`, `/analysis/:jobId/reports/:type`, or support both for presentation convenience?
- Which video metadata should be required at upload time: singles/doubles, camera angle, athlete side, venue, or skill level?
- Should the first real algorithm spike prioritize player pose, ball tracking, court calibration, or shot-event detection?
