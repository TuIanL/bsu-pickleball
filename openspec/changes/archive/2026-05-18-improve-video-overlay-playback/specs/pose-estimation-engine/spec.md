## MODIFIED Requirements

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
- **WHEN** RTMPose returns keypoints below the configured confidence threshold
- **THEN** those keypoints are either marked low-confidence or excluded according to the normalized pose schema

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
