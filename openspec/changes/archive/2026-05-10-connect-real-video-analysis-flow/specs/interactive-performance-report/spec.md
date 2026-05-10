## MODIFIED Requirements

### Requirement: Core metric summary
The system SHALL display a concise summary of pickleball performance metrics using structured analysis data, with demo routes using local demo data and completed real job routes using algorithm-derived MVP metrics where available.

#### Scenario: Metrics are rendered from demo data
- **WHEN** the report demo or a report detail page without job context is displayed
- **THEN** the system shows performance metrics such as overall score, serve or return quality, third-shot success, movement efficiency, rally stability, landing accuracy, unforced errors, or court control using values from the structured demo data source

#### Scenario: Metrics are rendered from real pipeline output
- **WHEN** a completed uploaded-video job has MVP pipeline metrics
- **THEN** the system shows available algorithm-derived metrics such as movement distance, speed summaries, kitchen dwell, doubles spacing, heatmap coverage, processed frame counts, or detection counts

#### Scenario: A requested metric is unavailable
- **WHEN** a report module requires ball tracking, hit events, rally segmentation, or pose diagnosis that the MVP pipeline did not produce
- **THEN** the system marks that metric as unavailable, limited, or demo-only instead of presenting fabricated uploaded-video results

### Requirement: Court visualization
The system SHALL visualize pickleball court analysis including landing heat points, shot routes, player movement paths, and algorithm-derived heatmaps in the visual analysis workspace and report detail pages.

#### Scenario: User views demo court analysis
- **WHEN** a sample court visualization module is visible
- **THEN** the system shows a pickleball court with landing distribution, return routes, movement trajectory, or video-overlay events based on demo data

#### Scenario: User views real movement court analysis
- **WHEN** a completed real analysis job includes projected tracks or heatmap data
- **THEN** the system renders court movement paths, player coverage, or heat distribution from backend algorithm output

#### Scenario: User switches visualization mode
- **WHEN** the user selects a supported court visualization mode or opens a report type focused on landing, routes, movement, or heatmap coverage
- **THEN** the court panel updates to emphasize the selected view while preserving the same report context and source distinction

## ADDED Requirements

### Requirement: Algorithm-derived feedback copy
The system SHALL translate available MVP algorithm metrics into concise coaching feedback for real uploaded-video jobs.

#### Scenario: Movement feedback is available
- **WHEN** the pipeline result includes movement distance, speed, spacing, zone dwell, or heatmap metrics
- **THEN** the report surfaces generate readable feedback that cites those metrics as evidence

#### Scenario: Tactical feedback is not supported by the MVP result
- **WHEN** the report page would otherwise show shot-pattern, rally, landing, or motion-diagnosis claims that require unsupported algorithms
- **THEN** the system either hides those claims for the real job or labels them as not available in the current analysis

#### Scenario: Report source is mixed during transition
- **WHEN** a real job report temporarily combines algorithm-derived movement metrics with retained sample-only sections
- **THEN** the system clearly distinguishes which sections are generated from the uploaded video and which sections are sample placeholders
