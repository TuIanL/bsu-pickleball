# pose-estimation-engine Specification

## Purpose
TBD - created by archiving change add-yolo-rtmpose-video-overlays. Update Purpose after archive.
## Requirements
### Requirement: RTMPose model configuration
The backend SHALL provide a pose estimation engine that can load a configured RTMPose runtime, model config, and checkpoint or exported model for real uploaded-video analysis jobs, and SHALL run it for eligible real jobs when pose inference is enabled and the assets are available.

#### Scenario: RTMPose assets are configured
- **WHEN** pose inference is enabled and the configured RTMPose runtime, model config, and checkpoint or exported model are available
- **THEN** the backend initializes the pose estimator lazily and makes it available to the analysis pipeline without changing demo-job behavior

#### Scenario: RTMPose assets are missing
- **WHEN** pose inference is enabled but the configured RTMPose assets cannot be found or loaded
- **THEN** the pose stage reports a clear skipped or failed state and no skeleton overlay is advertised as available

#### Scenario: Pose modules are imported in lightweight mode
- **WHEN** backend modules are imported with pose inference disabled
- **THEN** imports succeed without requiring RTMPose model files, GPU availability, or heavy pose runtime initialization

#### Scenario: Pose inference is intentionally disabled
- **WHEN** a real video job completes while pose inference is disabled by configuration
- **THEN** the backend reports that RTMPose is disabled and does not present the missing skeleton layer as a detection or filtering failure

### Requirement: Frame-level pose estimation
The backend SHALL run RTMPose on court-relevant tracked player boxes from processed video frames and emit normalized frame-level pose results.

#### Scenario: Tracked player boxes are available
- **WHEN** a processed video frame has one or more tracked player boxes that remain eligible after court-relevance filtering
- **THEN** the pose engine estimates keypoints for each eligible tracked subject and associates each pose result with `frame_index`, `timestamp_seconds`, and `track_id`

#### Scenario: Tracked person is outside match bounds
- **WHEN** a processed video frame has a tracked person whose projected footpoint is outside the configured match-relevant court bounds
- **THEN** the pose engine does not run or persist a renderable pose subject for that person

#### Scenario: No player boxes are available
- **WHEN** a processed video frame has no usable court-relevant player boxes
- **THEN** the pose engine skips that frame without fabricating skeleton keypoints

#### Scenario: Low-confidence keypoints are returned
- **WHEN** RTMPose returns keypoints whose confidence values are near the configured thresholds
- **THEN** keypoint visibility SHALL use hysteresis: keypoints transition from invisible to visible when confidence >= enter_threshold (default 0.30), and from visible to invisible only when confidence drops below exit_threshold (default 0.20)
- **AND** keypoints already marked visible SHALL retain visibility through brief confidence dips between exit_threshold and enter_threshold, eliminating flicker
- **AND** keypoints with confidence below exit_threshold SHALL be marked invisible immediately regardless of prior state
- **AND** both enter_threshold and exit_threshold SHALL be independently configurable via environment variables

#### Scenario: Distant players produce stable skeletons
- **WHEN** a distant player's bounding box is detected with PersonDetector confidence as low as 0.15
- **THEN** the detection SHALL be forwarded to pose estimation (PersonDetector.conf_threshold lowered from 0.25 to 0.15)
- **AND** the pose engine SHALL apply hysteresis to keypoint visibility for that player, reducing skeleton flicker caused by marginally low keypoint confidence at long range
- **AND** low-confidence detections SHALL still be subject to court-relevance and ROI filtering downstream

### Requirement: Pose result serialization
The backend SHALL persist pose results as JSON that the frontend can render as skeleton overlays over the source video, and persisted renderable pose subjects SHALL match the court-relevant subject set used by detection overlays.

#### Scenario: Pose results are persisted
- **WHEN** pose estimation completes for a real analysis job
- **THEN** the backend writes a pose artifact containing job/video identifiers, source frame dimensions, processed frame metadata, normalized keypoints, subject identifiers, keypoint schema, and skeleton connection metadata for court-relevant subjects

#### Scenario: Frontend requests pose overlay data
- **WHEN** a completed job has a persisted pose artifact
- **THEN** the artifact can be retrieved through a backend API or URL referenced by the raw pipeline result

#### Scenario: Pose artifact is unavailable
- **WHEN** pose estimation was skipped, failed, or produced no results
- **THEN** the system exposes an explicit unavailable state instead of returning an empty object that looks like successful skeleton analysis

### Requirement: Skeleton overlay semantics
The backend SHALL describe enough pose metadata for clients to render human skeletons consistently.

#### Scenario: Skeleton metadata is returned
- **WHEN** a pose artifact is returned to the frontend
- **THEN** it includes a stable keypoint schema name and the ordered skeleton edges needed to connect joints

#### Scenario: Unsupported keypoint schema is configured
- **WHEN** the configured pose model emits a keypoint schema the application does not recognize
- **THEN** the backend reports the pose stage as failed or skipped with a clear unsupported-schema detail

