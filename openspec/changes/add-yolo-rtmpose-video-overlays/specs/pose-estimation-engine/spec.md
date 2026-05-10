## ADDED Requirements

### Requirement: RTMPose model configuration
The backend SHALL provide a pose estimation engine that can load a configured RTMPose runtime, model config, and checkpoint or exported model for real uploaded-video analysis jobs.

#### Scenario: RTMPose assets are configured
- **WHEN** pose inference is enabled and the configured RTMPose runtime, model config, and checkpoint or exported model are available
- **THEN** the backend initializes the pose estimator lazily and makes it available to the analysis pipeline without changing demo-job behavior

#### Scenario: RTMPose assets are missing
- **WHEN** pose inference is enabled but the configured RTMPose assets cannot be found or loaded
- **THEN** the pose stage reports a clear skipped or failed state and no skeleton overlay is advertised as available

#### Scenario: Pose modules are imported in lightweight mode
- **WHEN** backend modules are imported with pose inference disabled
- **THEN** imports succeed without requiring RTMPose model files, GPU availability, or heavy pose runtime initialization

### Requirement: Frame-level pose estimation
The backend SHALL run RTMPose on tracked player boxes from processed video frames and emit normalized frame-level pose results.

#### Scenario: Tracked player boxes are available
- **WHEN** a processed video frame has one or more tracked player boxes
- **THEN** the pose engine estimates keypoints for each tracked subject and associates each pose result with `frame_index`, `timestamp_seconds`, and `track_id`

#### Scenario: No player boxes are available
- **WHEN** a processed video frame has no usable player boxes
- **THEN** the pose engine skips that frame without fabricating skeleton keypoints

#### Scenario: Low-confidence keypoints are returned
- **WHEN** RTMPose returns keypoints below the configured confidence threshold
- **THEN** those keypoints are either marked low-confidence or excluded according to the normalized pose schema

### Requirement: Pose result serialization
The backend SHALL persist pose results as JSON that the frontend can render as skeleton overlays over the source video.

#### Scenario: Pose results are persisted
- **WHEN** pose estimation completes for a real analysis job
- **THEN** the backend writes a pose artifact containing job/video identifiers, source frame dimensions, processed frame metadata, normalized keypoints, subject identifiers, keypoint schema, and skeleton connection metadata

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
