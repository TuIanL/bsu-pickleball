## ADDED Requirements

### Requirement: True-model pose artifact reporting
The system SHALL distinguish true RTMPose model output from unavailable, skipped, injected-test, or placeholder pose states in completed real analysis results.

#### Scenario: True RTMPose pose artifact is available
- **WHEN** a completed calibrated real analysis job runs with RTMPose inference enabled, supported model assets configured, and at least one frame producing valid skeleton keypoints
- **THEN** the raw pipeline result includes a done pose stage, `pose_overlay_status` of `available`, a retrievable `pose_overlay_url`, and detail text derived from generated subject/keypoint counts

#### Scenario: RTMPose runtime or assets are unavailable
- **WHEN** a completed real analysis job cannot run RTMPose because dependencies, config, checkpoint, or device setup is unavailable
- **THEN** the raw pipeline result exposes a skipped or unavailable pose stage with a clear diagnostic and omits any available pose overlay URL

#### Scenario: Detection exists without usable pose
- **WHEN** a completed real analysis job produces player boxes but RTMPose returns no usable skeleton keypoints
- **THEN** the raw pipeline result keeps tracking artifacts available and labels the pose overlay as no-pose or unavailable without failing the entire analysis
