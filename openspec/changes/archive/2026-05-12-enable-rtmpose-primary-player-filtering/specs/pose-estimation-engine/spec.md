## MODIFIED Requirements

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
The backend SHALL run RTMPose on selected primary-player tracked boxes from processed video frames and emit normalized frame-level pose results.

#### Scenario: Primary-player boxes are available
- **WHEN** a processed video frame has one or more tracked player boxes selected by primary-player filtering
- **THEN** the pose engine estimates keypoints for each selected subject and associates each pose result with `frame_index`, `timestamp_seconds`, and `track_id`

#### Scenario: Tracked player is outside court lines
- **WHEN** a tracked match player is selected as a primary-player subject while their projected footpoint is outside the standard court lines
- **THEN** the pose engine still receives that player box and may generate a renderable skeleton for the subject

#### Scenario: No primary-player boxes are available
- **WHEN** a processed video frame has no usable primary-player boxes
- **THEN** the pose engine skips that frame without fabricating skeleton keypoints

#### Scenario: Low-confidence keypoints are returned
- **WHEN** RTMPose returns keypoints below the configured confidence threshold
- **THEN** those keypoints are either marked low-confidence or excluded according to the normalized pose schema

### Requirement: Pose result serialization
The backend SHALL persist pose results as JSON that the frontend can render as skeleton overlays over the source video, and persisted renderable pose subjects SHALL match the selected primary-player subject set used by detection overlays.

#### Scenario: Pose results are persisted
- **WHEN** pose estimation completes for a real analysis job
- **THEN** the backend writes a pose artifact containing job/video identifiers, source frame dimensions, processed frame metadata, normalized keypoints, subject identifiers, keypoint schema, and skeleton connection metadata for selected primary-player subjects

#### Scenario: Frontend requests pose overlay data
- **WHEN** a completed job has a persisted pose artifact
- **THEN** the artifact can be retrieved through a backend API or URL referenced by the raw pipeline result

#### Scenario: Pose artifact is unavailable
- **WHEN** pose estimation was skipped, failed, or produced no results
- **THEN** the system exposes an explicit unavailable state instead of returning an empty object that looks like successful skeleton analysis
