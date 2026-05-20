## ADDED Requirements

### Requirement: Right-side analysis status rail
The visual analysis workspace SHALL provide a vertical status rail beside the primary video area for completed job results.

#### Scenario: User opens a completed result on desktop
- **WHEN** a completed job-specific visual analysis page renders on a desktop viewport
- **THEN** the page shows the video viewport as the primary content and a right-side rail with task status, match metadata, overlay availability, and report tab actions

#### Scenario: User opens a completed result on a narrow viewport
- **WHEN** a completed job-specific visual analysis page renders on a narrow viewport
- **THEN** the status rail stacks below or near the video without overlapping the video controls or report actions

#### Scenario: Overlay data is partially available
- **WHEN** a completed job has only some overlay artifacts available
- **THEN** the status rail labels available, unavailable, skipped, or failed video layers without presenting unavailable model output as real analysis

## MODIFIED Requirements

### Requirement: Video-first analysis workspace
The system SHALL provide a dedicated visual analysis page centered on a job-aware pickleball video player, with completed job routes using a clean video-and-status layout and demo routes preserving simulated visuals.

#### Scenario: User opens the visual analysis demo page
- **WHEN** the user navigates to `/vision` without a job context
- **THEN** the system may render the local demo analysis experience with a large video-style analysis card, sample context, and clear demo/source indication

#### Scenario: User views the simulated video layer
- **WHEN** the video analysis card is visible without a real job context
- **THEN** the system shows a pickleball court mockup with court lines, kitchen zones, player markers or boxes, shot trajectories, landing or heat indicators, and AI labels

#### Scenario: User views a completed real-job video layer
- **WHEN** the video analysis card is visible for a completed uploaded-video job with a source video URL
- **THEN** the system plays the uploaded source video in the primary visual area and places job status, overlay status, and report navigation in the adjacent status rail rather than surrounding the video with full report dashboards

### Requirement: Highlights and coach notes
The system SHALL keep highlights and coach-like insights available as lower-level analysis content without cluttering the primary completed-result video viewport.

#### Scenario: User opens completed visual analysis
- **WHEN** a completed job-specific visual analysis page is visible
- **THEN** the primary viewport area focuses on the video and status rail instead of rendering full coach-note and highlight cards around the video

#### Scenario: User reviews coach notes or highlights
- **WHEN** the user opens a lower-level report tab, report detail page, or equivalent secondary result view
- **THEN** the system displays readable highlights or AI coach notes covering strengths, risks, major errors, and training recommendations with distinct status treatments

### Requirement: Rally timeline and shot filtering
The system SHALL keep video timeline review close to the video player while moving detailed shot exploration into lower-level analysis views.

#### Scenario: User reviews timeline markers
- **WHEN** timeline markers are available for the current video result or demo
- **THEN** the player exposes concise marker labels or tooltips without forcing full shot-explorer content into the primary completed-result viewport

#### Scenario: User selects a shot filter chip
- **WHEN** the user opens a lower-level shot exploration or rally report view and clicks a shot filter such as All, Serve, Return, Third Shot, Dink, Drive, Reset, Volley, Smash, or Error
- **THEN** the selected chip visibly changes state and the displayed shot list or shot summary reflects that local selection

### Requirement: Video workspace report actions
The system SHALL present compact lower-level report actions from the visual analysis workspace.

#### Scenario: User views report actions
- **WHEN** the user reviews a completed job-specific video analysis workspace
- **THEN** the status rail or adjacent secondary navigation shows tab-like actions for landing analysis report, movement analysis report, rally tactics report, and motion diagnosis report

#### Scenario: User selects a report action
- **WHEN** the user clicks one of the report actions from a completed job-specific result
- **THEN** the system navigates to the matching job-specific `/analysis/:jobId/reports/:type` report detail page or equivalent lower-level tab state

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job video and status data from backend report payloads, available MVP pipeline algorithm results, and video overlay artifacts in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, source video, overlay statuses, timeline markers, and status rail render from that job's report payload, algorithm-derived fields, and available detection, pose, or ball overlays

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, supported MVP metrics, detection boxes, or pose keypoints
- **THEN** the workspace shows limited or unavailable states in the status rail and lower-level analysis views instead of filling modules with unrelated demo shot or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data
