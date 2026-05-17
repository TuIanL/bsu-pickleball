## Context

The backend already has a CourtVision Calibration Engine that stores manual four-corner calibration, computes an image-to-court homography, projects player footpoints into standard pickleball court coordinates, and renders calibration previews. Real uploaded-video analysis currently runs full player tracking only when a valid calibration is supplied; without calibration it degrades to limited analysis.

The user has a COCO segmentation dataset of roughly four thousand labeled court-line images. That dataset should feed a local training workflow, but large datasets, training outputs, and model weights must remain outside version control. The runtime application should consume a trained model artifact and produce a reviewable semi-automatic calibration result rather than training during a user request.

## Goals / Non-Goals

**Goals:**

- Establish a local dataset convention for COCO segmentation court-line data and ignored training artifacts.
- Provide a repeatable backend workflow to validate the COCO dataset, convert or configure it for segmentation training, and train/export a court-line segmentation model.
- Add a runtime adapter that runs court-line segmentation on a representative frame and returns mask/line confidence diagnostics.
- Convert predicted court-line masks into ordered court keypoints that can be passed to the existing homography calibration path.
- Add a semi-automatic calibration API and frontend handoff that lets the user accept, preview, or manually correct the detected court before starting analysis.
- Preserve manual calibration and limited-analysis behavior when the model is unavailable or the automatic result is low confidence.

**Non-Goals:**

- Training models inside the web request/response path.
- Replacing YOLO person detection, RTMPose, tracking, or movement metric logic.
- Solving all camera angles, occlusions, rolling shutter, or multi-court scenes in the first implementation.
- Detecting balls, hit events, rally boundaries, or tactical semantics.
- Committing datasets, trained weights, or generated training runs to Git.

## Decisions

### Use segmentation first, geometry second

The trained model should predict court-line or court-region masks from image frames. The backend should then use deterministic OpenCV-style post-processing to clean masks, fit line candidates, find intersections, order outer corners, and score the result against standard pickleball court geometry.

Alternatives considered:

- Direct corner/keypoint regression: easier runtime output, but it wastes the existing COCO segmentation labels unless a conversion/labeling step is added.
- Classical line detection only: simple to prototype, but brittle under shadows, painted courts, low contrast, and player occlusion.
- Use the raw mask as calibration: visually useful, but downstream metrics require a homography, so corners or point correspondences are still needed.

### Keep the first model as a one-class court-line segmenter

The first training path should support a single `court_line` class even if the dataset later grows richer labels. If the dataset already distinguishes sidelines, baselines, kitchen lines, or center lines, the conversion/validation scripts can preserve that metadata, but the runtime should not require class-specific labels for MVP calibration.

Alternatives considered:

- Require detailed line classes from day one: can improve post-processing, but raises dataset normalization cost and may block progress if labels are inconsistent.
- Segment the entire playable court region instead of lines: useful for outer corners, but less directly aligned with the existing edge-line annotations.

### Store datasets and runs outside tracked source

Use a root-level `datasets/court-line-coco/` convention for local development and update ignore rules so datasets and training runs do not enter Git. Trained model weights should continue to live under `models/` using the existing ignored model-weight convention.

Alternatives considered:

- Put datasets under `backend/data/`: that directory is runtime-oriented for uploads, outputs, calibrations, and temporary files, not training corpora.
- Put datasets under `models/`: model weights and datasets have different lifecycle, size, and documentation needs.
- Require an external absolute path only: safe for Git, but harder for scripts and onboarding unless a project-relative convention also exists.

### Add a semi-automatic calibration result, not silent auto-accept

The API should return predicted keypoints, confidence, quality diagnostics, and preview artifact references. The frontend should let the user accept the suggestion or correct points manually. Backend analysis jobs should only consume a stored calibration ID after the suggestion has passed validation and been accepted or explicitly submitted.

Alternatives considered:

- Auto-start analysis after detection: faster, but dangerous when the court is partially visible or a neighboring court is detected.
- Frontend-only correction without storing diagnostics: simpler UI, but loses the evidence needed to debug model quality and training regressions.

### Keep training scripts decoupled from runtime dependencies

Training helpers can rely on optional heavy ML dependencies and local GPU/CPU configuration. The FastAPI runtime should degrade cleanly when the court-line model path is unset, missing, or cannot be loaded.

Alternatives considered:

- Make training dependencies required for all backend installs: simpler documentation, but slows lightweight development and breaks machines that only need the API foundation.
- Use a remote training service: unnecessary for the current local prototype and adds deployment/security complexity.

## Risks / Trade-offs

- Thin white/yellow court lines may be under-segmented at low input resolution. Mitigation: document higher training/inference image sizes and use mask dilation/closing before line fitting.
- Occluded corners or partial courts can produce plausible but wrong quadrilaterals. Mitigation: require confidence thresholds, geometry sanity checks, preview review, and manual correction fallback.
- Random frame-level dataset splitting can overstate validation quality if near-duplicate frames from the same video are split across train and validation. Mitigation: document source-aware splits and add dataset inspection summaries.
- A one-class line model may not distinguish outer boundary from kitchen/center lines in cluttered scenes. Mitigation: use standard pickleball geometry constraints and allow future multi-class labels without changing the API contract.
- Training outputs can grow quickly and pollute the repository. Mitigation: ignore `datasets/` and local training runs, and document model artifact placement explicitly.

## Migration Plan

- Introduce dataset/model path conventions and ignore rules before any dataset is copied into the workspace.
- Add training and validation scripts as optional developer workflows that do not affect existing manual calibration.
- Add the runtime inference adapter behind configuration so manual calibration remains the default fallback when no model is available.
- Add the semi-automatic calibration API and frontend entry point as an enhancement to the existing calibration step.
- Roll back by disabling the court-line model configuration; manual calibration and limited-analysis flows remain available.

## Open Questions

- Does the COCO dataset label only court lines, or does it also include court regions and line sub-classes?
- Are annotations stored as polygon segmentation, RLE segmentation, or a mixture?
- Are images grouped by source video/court so train/validation/test splits can avoid near-duplicate leakage?
- Which deployment target matters first for inference speed: CPU-only local laptop, Apple Silicon acceleration, or CUDA GPU?
