## MODIFIED Requirements

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job data from backend report payloads and available MVP pipeline algorithm results in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, timeline markers, overlay labels, highlights, coach notes, shot explorer, and report actions render from that job's report payload and algorithm-derived fields where available

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, or supported MVP metrics
- **THEN** the workspace shows a limited-analysis state for unavailable modules instead of filling those modules with unrelated demo shot or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data

### Requirement: Result-source clarity
The system SHALL distinguish demo analysis, limited real analysis, and algorithm-derived job analysis without disrupting the visual hierarchy.

#### Scenario: User views demo analysis
- **WHEN** the visual analysis workspace is rendering local demo data
- **THEN** the system provides a subtle demo/sample indication in the page context or metadata

#### Scenario: User views algorithm-derived job analysis
- **WHEN** the visual analysis workspace is rendering a completed uploaded-video job with pipeline output
- **THEN** the system shows job, match, uploaded video, calibration, and generated result metadata associated with the analysis

#### Scenario: User views limited job analysis
- **WHEN** the visual analysis workspace is rendering a completed job that lacks enough algorithm output for a module
- **THEN** the system labels the affected module as unavailable or limited and explains the missing prerequisite such as calibration or detections

## ADDED Requirements

### Requirement: Algorithm-backed movement visualization
The system SHALL visualize available player movement and court coverage data from backend pipeline results in the visual analysis workspace.

#### Scenario: Projected tracks are available
- **WHEN** a completed real analysis job includes projected player tracks
- **THEN** the workspace renders movement paths, player positions, or heat distribution from those tracks rather than static demo coordinates

#### Scenario: Movement metrics are available
- **WHEN** a completed real analysis job includes distance, speed, kitchen dwell, doubles spacing, or heatmap metrics
- **THEN** the workspace presents movement-focused feedback derived from those metrics with readable labels and values

#### Scenario: No detections are produced
- **WHEN** the backend pipeline completes but produces no usable player detections or projected positions
- **THEN** the workspace shows an analysis-completed-but-no-tracks state with guidance to check camera angle, calibration, model setup, or video quality
