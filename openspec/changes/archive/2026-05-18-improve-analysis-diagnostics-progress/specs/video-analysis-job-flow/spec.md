## ADDED Requirements

### Requirement: Structured analysis error diagnostics
The system SHALL preserve and display structured backend error diagnostics for real video upload, calibration, job creation, job status, and result retrieval failures.

#### Scenario: Backend returns an error payload
- **WHEN** a frontend analysis API request receives a non-success response with backend detail
- **THEN** the frontend error state includes the operation context, request path, HTTP status, and backend detail when available

#### Scenario: Backend cannot be reached
- **WHEN** a frontend analysis API request fails before receiving an HTTP response
- **THEN** the frontend error state identifies the operation that failed and communicates that the backend connection or network request failed

#### Scenario: User sees a failed analysis job
- **WHEN** the user opens a job whose status is `failed`
- **THEN** the job status page shows the failed stage, stored failure message, and any available stage detail instead of only a generic failure sentence

### Requirement: Stage-based real analysis progress
The system SHALL persist and display real intermediate progress for pipeline-backed analysis jobs using backend-reported stage state.

#### Scenario: Pipeline job starts processing
- **WHEN** a queued real analysis job begins backend processing
- **THEN** the backend updates the job to `processing` with the active stage and progress derived from the ordered analysis stages

#### Scenario: Pipeline advances between stages
- **WHEN** the backend completes or skips a meaningful pipeline stage
- **THEN** the backend persists updated stages, current active stage, updated timestamp, and a monotonic progress percentage before the final result is available

#### Scenario: Frontend polls a running job
- **WHEN** the job status page polls a processing job
- **THEN** it renders the current stage label, progress percentage, and stage list from the latest backend job summary

#### Scenario: Pipeline fails during an intermediate stage
- **WHEN** a real analysis job fails before report generation
- **THEN** the backend records the first failed stage and the frontend displays that stage as failed with the diagnostic detail
