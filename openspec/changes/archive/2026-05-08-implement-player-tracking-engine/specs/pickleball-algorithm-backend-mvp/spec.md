## MODIFIED Requirements

### Requirement: Player tracking and footpoint projection interfaces
The backend SHALL define replaceable interfaces and MVP implementations for person detection, multi-object tracking, footpoint estimation, and projection from image coordinates into court coordinates.

#### Scenario: Detection output is normalized
- **WHEN** a detector returns person detections for a video frame
- **THEN** the backend normalizes each detection into `bbox`, `confidence`, and `class_name` fields with only `person` detections included in the result

#### Scenario: YOLO-backed person detection runs
- **WHEN** Ultralytics YOLO is available and the detector receives a decoded video frame
- **THEN** the backend can run the configured `yolov8n.pt` or `yolov8s.pt` model, apply a confidence threshold, and emit normalized person detections

#### Scenario: Lightweight imports run without model dependencies
- **WHEN** a developer imports Player Tracking Engine modules without YOLO weights, CUDA, or tracker model assets installed
- **THEN** the imports succeed and optional model-backed execution fails only when invoked with a clear error

#### Scenario: Footpoint is estimated from a person box
- **WHEN** a person bounding box is passed to the footpoint estimator
- **THEN** the estimator returns the bottom-center footpoint `(x1 + x2) / 2, y2` and identifies the method as `bbox_bottom_center`

#### Scenario: Tracks are associated across frames
- **WHEN** consecutive frames contain overlapping detections for the same player
- **THEN** the multi-object tracker keeps the same integer `track_id` for that player when IOU association succeeds

#### Scenario: Track points are projected to court coordinates
- **WHEN** tracked image footpoints are passed through a valid calibration
- **THEN** the backend returns per-player projected track points with frame index, timestamp, track identifier, bbox, image footpoint, court coordinate, confidence, and validity/filtering behavior

#### Scenario: Off-court detections are filtered
- **WHEN** a detected person projects outside the tolerated standard court coordinate bounds
- **THEN** the backend excludes that person from valid movement trajectories or marks the position invalid so metrics can ignore it
