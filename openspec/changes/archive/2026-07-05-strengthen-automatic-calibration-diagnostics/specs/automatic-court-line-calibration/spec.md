## MODIFIED Requirements

### Requirement: Court-line segmentation inference
The system SHALL run court-line segmentation on a representative video frame when a configured runtime model is available.

#### Scenario: Model produces a court-line mask
- **WHEN** the backend receives an automatic court calibration request for a readable uploaded video or frame and the court-line model is configured
- **THEN** the backend returns segmentation-derived mask diagnostics including frame size, selected frame reference, model confidence, whether a usable court-line mask was produced, and enough structured diagnostics for downstream reference-line support scoring

#### Scenario: Model is unavailable
- **WHEN** the backend receives an automatic court calibration request but the model path is unset, missing, or cannot be loaded
- **THEN** the backend returns a stable unavailable result that instructs the frontend to keep manual calibration available

### Requirement: Mask-to-court-keypoint post-processing
The system SHALL convert a predicted court-line mask into ordered standard court keypoints when the mask passes geometry validation.

#### Scenario: Mask supports a valid court quadrilateral
- **WHEN** the predicted mask contains enough line evidence to fit court boundary candidates and derive four ordered outer court corners
- **THEN** the backend returns `top_left`, `top_right`, `bottom_right`, and `bottom_left` image points with confidence, geometry quality diagnostics, reference-line support diagnostics, and a structured confidence breakdown that explains the final automatic calibration score

#### Scenario: Mask cannot produce reliable keypoints
- **WHEN** the predicted mask is too sparse, fragmented, ambiguous, outside the frame bounds, fails standard pickleball court geometry checks, or fails the configured reference-line support threshold after keypoints are derived
- **THEN** the backend returns a rejected automatic calibration result and MUST NOT create a misleading accepted homography

### Requirement: Automatic calibration preview artifacts
The system SHALL provide visual preview artifacts that allow users and developers to inspect automatic court-line detection before analysis starts.

#### Scenario: Automatic preview is available
- **WHEN** automatic segmentation and keypoint post-processing complete for a representative frame
- **THEN** the backend exposes or records a preview artifact showing the selected frame, detected mask or fitted lines, ordered keypoints, projected court overlay, and reference-line support evidence or summary when a homography is available

#### Scenario: Preview cannot be generated
- **WHEN** OpenCV, frame access, or output storage prevents preview generation
- **THEN** the backend returns a clear diagnostic while preserving the structured automatic calibration result status

### Requirement: User-facing automatic calibration diagnostics
The system SHALL expose actionable automatic court-line calibration diagnostics in the upload workflow for available, unavailable, rejected, and failed attempts.

#### Scenario: Automatic calibration is available
- **WHEN** automatic court-line calibration returns an available suggestion
- **THEN** the upload workflow displays the final confidence, selected frame reference, keypoint fill status, preview when available, calibration quality diagnostics, and the available reference-line support explanation including component scores when returned

#### Scenario: Automatic calibration model is unavailable
- **WHEN** automatic court-line calibration returns unavailable because the model path is unset, missing, or cannot be loaded
- **THEN** the upload workflow displays that model availability diagnosis, including configured model path when returned, and keeps manual four-corner calibration available

#### Scenario: Automatic calibration geometry is rejected
- **WHEN** automatic court-line calibration returns rejected because the mask, fitted geometry, or reference-line support checks fail validation
- **THEN** the upload workflow displays the backend rejection detail, mask confidence, mask area ratio, line count, selected frame reference, preview when available, and the strongest available reason for low reference support or low combined confidence

#### Scenario: Automatic calibration request fails
- **WHEN** the automatic calibration request fails with an HTTP or network error
- **THEN** the upload workflow displays the request failure status and backend detail when available while preserving the selected video, metadata, and manual calibration controls

#### Scenario: Older automatic calibration response lacks diagnostics
- **WHEN** the frontend receives an automatic calibration response without optional diagnostic fields
- **THEN** the upload workflow remains stable and displays a concise unavailable diagnostic without crashing
