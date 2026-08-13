## MODIFIED Requirements

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates orchestration-aware analysis progress, MVP pipeline stage telemetry, model-backed detection and pose stages, cancellation state, and next actions within the task-centered workflow. The page SHALL present the analysis stages as a horizontal capsule stepper with the currently running stage highlighted, instead of a verbose vertical stage list.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, queue timing, a message that processing has not started yet, a cancellation action when allowed, and a way back to task management

#### Scenario: User opens a running job
- **WHEN** the user navigates to an analysis job that is running or displayed as processing
- **THEN** the system shows the current processing stage, a horizontal capsule stage stepper that scrolls horizontally and auto-focuses the active stage, the active stage's detail text (such as processed frame counts) on its own line, an overall percentage as secondary text, cancellation action when allowed, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User views the horizontal stage stepper
- **WHEN** the user views a non-terminal analysis job with multiple reported stages
- **THEN** the system renders the stages as a single horizontally scrollable row of capsules with connector lines, colors completed stages green, the active stage orange with a breathing emphasis, failed stages red, skipped stages gray, and pending stages light gray, and automatically scrolls the active (or failed) stage into the visible area

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, pose estimation, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a terminal job with collapsed progress
- **WHEN** the user navigates to an analysis job that is completed, failed, or canceled
- **THEN** the progress area collapses to a one-line summary (for example total completed stages and overall duration for completed jobs, or the failing/canceled stage), and result or recovery actions become the primary content of the page

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the user-facing failure reason and stable error code when available and offers a retry, return-to-upload, or return-to-task-management action

#### Scenario: User opens a canceled job
- **WHEN** the user navigates to an analysis job that was canceled
- **THEN** the system shows a stable canceled state, cancellation timing when available, and actions to start a new upload or return to task management

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, analysis details page, and task management page

#### Scenario: User views a multiview parent job
- **WHEN** the user navigates to an analysis job with `analysisKind=multiview` that exposes `viewRuns`
- **THEN** the page shows the A/B per-view progress bars inside the progress area instead of as a separate block, and the per-view progress remains a summary of the two child runs

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated person or pose overlay artifacts, stage timestamps, durations, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, stage timing, retry or skip context, or a clear skipped/failed reason
