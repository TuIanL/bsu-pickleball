## ADDED Requirements

### Requirement: User-facing automatic calibration diagnostics
The system SHALL expose actionable automatic court-line calibration diagnostics in the upload workflow for available, unavailable, rejected, and failed attempts.

#### Scenario: Automatic calibration is available
- **WHEN** automatic court-line calibration returns an available suggestion
- **THEN** the upload workflow displays the confidence, selected frame reference, keypoint fill status, preview when available, and calibration quality diagnostics when returned

#### Scenario: Automatic calibration model is unavailable
- **WHEN** automatic court-line calibration returns unavailable because the model path is unset, missing, or cannot be loaded
- **THEN** the upload workflow displays that model availability diagnosis, including configured model path when returned, and keeps manual four-corner calibration available

#### Scenario: Automatic calibration geometry is rejected
- **WHEN** automatic court-line calibration returns rejected because the mask or fitted geometry fails validation
- **THEN** the upload workflow displays the backend rejection detail, mask confidence, mask area ratio, line count, selected frame reference, and preview when available

#### Scenario: Automatic calibration request fails
- **WHEN** the automatic calibration request fails with an HTTP or network error
- **THEN** the upload workflow displays the request failure status and backend detail when available while preserving the selected video, metadata, and manual calibration controls

#### Scenario: Older automatic calibration response lacks diagnostics
- **WHEN** the frontend receives an automatic calibration response without optional diagnostic fields
- **THEN** the upload workflow remains stable and displays a concise unavailable diagnostic without crashing
