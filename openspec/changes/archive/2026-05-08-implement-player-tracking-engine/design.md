## Context

The backend already has a Python FastAPI foundation, CourtVision Calibration Engine homography utilities, tracking schemas, and Player Tracking Engine placeholder modules. The current pipeline can upload videos and store calibration results, but `AnalysisPipeline` still produces deterministic mock projected tracks instead of reading frames, detecting people, tracking identities, estimating footpoints, and projecting those footpoints into standard court coordinates.

This change sits between CourtVision calibration and the Pickleball Performance Engine:

```text
uploaded video
  -> frame reader
  -> PersonDetector
  -> MultiObjectTracker
  -> FootpointEstimator
  -> PlayerProjector + calibration homography
  -> TrackingResult JSON
  -> projected track points for metrics
```

The implementation must keep lightweight backend imports working without model weights, CUDA, or Ultralytics installed. Model-backed detection should be optional at runtime, while tests should use deterministic unit inputs rather than requiring YOLO inference.

## Goals / Non-Goals

**Goals:**

- Provide a concrete Player Tracking Engine MVP for fixed-camera pickleball video.
- Normalize detection, track, footpoint, projected position, and tracking-result schemas so downstream metrics can consume them predictably.
- Use bbox bottom-center as the MVP footpoint and explicitly avoid bbox center as the player position.
- Use CourtVision's image-to-court homography for projecting image footpoints into canonical feet coordinates.
- Filter likely spectators, referees, or off-court detections through configurable court-coordinate tolerance bounds.
- Keep interfaces replaceable so IOU tracking can later be swapped for ByteTrack or BoT-SORT without changing pipeline or metrics contracts.
- Integrate video reading, frame stride, FPS/timestamp metadata, progress logging, and `tracking_result.json` artifact output into `AnalysisPipeline`.

**Non-Goals:**

- Do not implement pose estimation, ankle averaging, segmentation masks, player team assignment, or doubles partner classification in this change.
- Do not implement automatic court calibration or automatic camera motion compensation.
- Do not require GPU acceleration or make Ultralytics import mandatory for the backend API to start.
- Do not implement full re-identification after long occlusion; MVP ID stability is based on IOU continuity and short lost-track retention.
- Do not generate an annotated overlay video unless a later visualization change scopes it.

## Decisions

### Keep YOLO optional and load it lazily

`PersonDetector` should expose a concrete class that defaults to `yolov8n.pt` or a configurable model path, filters class id `0`/`person`, and returns normalized `Detection` records. The Ultralytics import and model load should happen inside detector initialization or first inference, not at module import time, so lightweight tests and API smoke checks do not require model dependencies.

Alternative considered: make `ultralytics` a hard backend dependency. That simplifies detector code but breaks the existing lightweight verification contract and makes environments without model assets fail too early.

### Prefer auto device selection with CPU fallback

The detector should choose CUDA when available and otherwise use CPU. The choice can be implemented defensively by checking PyTorch availability if present and falling back to `"cpu"` without importing heavy GPU dependencies at module import time.

Alternative considered: require callers to pass a device. That is useful for tuning, but the MVP should work out of the box on local developer machines.

### Use an IOU tracker as the first concrete tracker

`MultiObjectTracker` should be a class with a stable `update(detections)` interface returning `Track` records. The MVP can associate detections to existing active tracks by highest IOU above a threshold, create new IDs for unmatched detections, increment lost counters for unmatched tracks, and prune tracks after `max_lost` frames.

Alternative considered: integrate ByteTrack or BoT-SORT immediately. Those are stronger in crowded footage but add dependency and configuration risk. The IOU tracker establishes the contract and keeps the first implementation testable.

### Model footpoint estimation as a class with explicit strategies

`FootpointEstimator` should default to `bbox_bottom_center` and return both `[foot_x, foot_y]` and `method`. The module may keep the current function as a compatibility wrapper, but the public class should make future `pose_ankle_average` and `segmentation_mask_bottom` strategies obvious.

Alternative considered: compute footpoints inside the tracker or projector. Keeping it separate makes it testable and prevents accidental use of bbox center in future call sites.

### Project after tracking and filter in court coordinates

`PlayerProjector` should accept tracks, homography, frame index, timestamp, and footpoint metadata, call CourtVision `image_to_court`, and return `PlayerFramePosition` records. Filtering should happen after projection using tolerant court bounds such as x in `[-2, 22]` and y in `[-2, 46]`, while still allowing invalid/off-court points to be marked or excluded according to a clear option.

Alternative considered: filter in image coordinates before projection. That is camera-dependent and cannot reliably distinguish spectators from valid players near the frame edge.

### Persist tracking output separately from the aggregate pipeline result

`AnalysisPipeline` should continue writing its existing job result JSON, but also write a dedicated `tracking_result.json` artifact for the frame-level tracking stream. The pipeline can convert valid `PlayerFramePosition` rows into the existing projected track point shape used by metrics, preserving frontend/report compatibility while adding richer tracking metadata for later analysis.

Alternative considered: only embed tracking inside `AnalysisPipelineResult`. Dedicated artifacts make it easier to inspect, cache, and reuse tracking independently of metric/report generation.

### Preserve deterministic fallback behavior

When no video or no calibration is provided, the pipeline should keep the existing mock/empty path rather than crashing. When a video and calibration are present but YOLO is unavailable, the pipeline should fail with a clear message or use an explicitly configured empty detector; implementation should avoid silently pretending model output is real.

Alternative considered: always run an empty detector if YOLO is unavailable. That keeps jobs green, but can hide environment problems during real analysis runs.

## Risks / Trade-offs

- YOLO weights may be unavailable or slow to download -> load lazily, surface clear runtime errors, and keep tests independent of YOLO inference.
- IOU tracking can swap IDs during crossings or occlusion -> expose thresholds and `max_lost`, document MVP limits, and keep the interface ready for ByteTrack/BoT-SORT.
- Bottom-center bbox footpoints can be biased by loose boxes -> make the method explicit and keep future pose/segmentation strategies in the interface.
- Homography projection quality depends on calibration accuracy -> reuse CourtVision validation and keep projected output bounded/filtered.
- Frame-by-frame processing can be slow -> add `frame_stride`, log progress, and preserve FPS/timestamp metadata so sparse tracks remain meaningful.
- Court-coordinate filtering can drop valid players just outside the line -> use tolerant bounds and make the tolerance configurable.

## Migration Plan

- Add schemas and engine classes while preserving existing imports where practical.
- Update tests to use the new class APIs and keep compatibility wrappers if existing metrics tests import old helpers.
- Integrate the new tracking pipeline behind `AnalysisPipeline` using dependency injection defaults.
- Preserve the current mock pipeline path for jobs without calibration or video, then promote real tracking when both inputs are available.
- Add tracking artifact paths to result artifacts without removing existing fields.

## Open Questions

- Should out-of-bounds projected points be excluded from `TrackingResult.positions`, or included with an `valid=false` flag? Tests can accept either, but the implementation should choose one consistently.
- Should `track_id` be integer-only in new tracking output while legacy projected metric points keep string IDs for compatibility, or should the pipeline convert integers to strings only at the metrics boundary?
