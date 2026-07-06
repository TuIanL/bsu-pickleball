## MODIFIED Requirements

### Requirement: Automatic calibration suggestion handoff
The system SHALL allow the video upload calibration step to request and review an automatic court calibration suggestion before creating a real analysis job.

#### Scenario: User requests automatic calibration after upload
- **WHEN** the user has uploaded a readable video and selects automatic court calibration
- **THEN** the frontend requests an automatic calibration suggestion for the uploaded video and presents the returned status, confidence, keypoints, preview, and structured diagnostic explanation when available

#### Scenario: User accepts automatic calibration
- **WHEN** an automatic calibration suggestion passes backend validation and the user accepts it
- **THEN** the frontend stores the returned calibration identifier and creates the real analysis job with that calibration identifier

#### Scenario: User corrects automatic keypoints
- **WHEN** an automatic calibration suggestion is visible but one or more points need adjustment
- **THEN** the frontend lets the user submit corrected keypoints through the calibration handoff before creating the real analysis job

#### Scenario: Automatic calibration is unavailable or rejected
- **WHEN** the automatic calibration request fails, the model is unavailable, or the backend rejects the detected geometry
- **THEN** the workflow keeps manual calibration and limited-analysis fallback choices available without losing the uploaded video or match metadata, while preserving the returned rejection or availability diagnostics for user review
