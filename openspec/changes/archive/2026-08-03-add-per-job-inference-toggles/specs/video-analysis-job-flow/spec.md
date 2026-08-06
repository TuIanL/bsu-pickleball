## ADDED Requirements

### Requirement: Per-job inference toggles in job creation
The system SHALL allow users to choose, when creating an analysis job from the upload flow, whether to enable human detection (YOLO) and pose estimation (RTMPose) model inference for that job, defaulting to enabled.

#### Scenario: Upload page exposes inference toggles
- **WHEN** the user completes video upload and court calibration on the new-analysis page and is about to submit the job
- **THEN** the form SHALL show two independent toggles labeled for human detection (YOLO) and pose estimation (RTMPose), both defaulting to enabled

#### Scenario: Toggles are sent with the job request
- **WHEN** the user submits the analysis job
- **THEN** the job creation request SHALL include `enableModelInference` and `enablePoseInference` reflecting the toggle states

#### Scenario: Toggles default to enabled
- **WHEN** the user does not touch the toggles
- **THEN** both `enableModelInference` and `enablePoseInference` SHALL be submitted as enabled

#### Scenario: Toggle hint without calibration
- **WHEN** the current flow has no valid court calibration (limited or demo mode)
- **THEN** the inference toggles SHALL remain visible with a hint that they take effect only after court calibration
