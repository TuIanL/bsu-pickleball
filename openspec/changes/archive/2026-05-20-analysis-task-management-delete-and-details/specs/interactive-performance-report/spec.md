## MODIFIED Requirements

### Requirement: Core metric summary
The system SHALL display a concise summary of pickleball performance metrics using structured analysis data, with demo routes using local demo data and completed real job routes using algorithm-derived movement and player-tracking metrics where available.

#### Scenario: Metrics are rendered from demo data
- **WHEN** the report demo or a report detail page without job context is displayed
- **THEN** the system may show sample performance metrics such as overall score, serve or return quality, movement efficiency, rally stability, landing accuracy, unforced errors, or court control while clearly distinguishing them as demo data

#### Scenario: Metrics are rendered from real pipeline output
- **WHEN** a completed uploaded-video job has MVP pipeline metrics
- **THEN** the system shows available algorithm-derived metrics such as movement distance, speed summaries, kitchen dwell, doubles spacing, heatmap coverage, processed frame counts, or person detection counts

#### Scenario: A requested metric is unavailable
- **WHEN** a real-job report module would require ball tracking, landing detection, hit events, shot classification, rally segmentation, or pose diagnosis that the current pipeline does not produce
- **THEN** the system omits that metric or marks it as unavailable instead of presenting fabricated uploaded-video results

### Requirement: Court visualization
The system SHALL visualize pickleball court analysis for current real jobs through player movement paths, projected positions, standard court context, and algorithm-derived heatmaps, while demo routes may retain clearly labeled sample landing or shot visuals.

#### Scenario: User views demo court analysis
- **WHEN** a sample court visualization module is visible without job context
- **THEN** the system may show a pickleball court with sample landing distribution, return routes, movement trajectory, or video-overlay events based on demo data

#### Scenario: User views real movement court analysis
- **WHEN** a completed real analysis job includes projected tracks or heatmap data
- **THEN** the system renders court movement paths, player coverage, or heat distribution from backend algorithm output without adding ball landing or shot-route claims

#### Scenario: User views the analysis details court plan
- **WHEN** a completed job's analysis details page is visible
- **THEN** the system renders the standard 2D pickleball court plan as the base visualization for future player movement projection

### Requirement: Algorithm-derived feedback copy
The system SHALL translate available MVP algorithm metrics into concise coaching feedback for real uploaded-video jobs while avoiding unsupported ball, landing, shot, or rally claims.

#### Scenario: Movement feedback is available
- **WHEN** the pipeline result includes movement distance, speed, spacing, zone dwell, or heatmap metrics
- **THEN** the report surfaces generate readable feedback that cites those metrics as evidence

#### Scenario: Tactical feedback is not supported by the MVP result
- **WHEN** the report page would otherwise show shot-pattern, rally, landing, ball-trajectory, or motion-diagnosis claims that require unsupported algorithms
- **THEN** the system either hides those claims for the real job or labels them as not available in the current analysis

#### Scenario: Report source is mixed during transition
- **WHEN** a real job report temporarily combines algorithm-derived movement metrics with retained sample-only sections
- **THEN** the system clearly distinguishes which sections are generated from the uploaded video and which sections are sample placeholders

## REMOVED Requirements

### Requirement: Rally analysis
**Reason**: Rally segmentation and shot-pattern analysis depend on ball capture and event recognition that are intentionally removed from the active scope.
**Migration**: Real-job flows SHALL omit rally-level tactical conclusions. Demo-only rally examples may remain only when explicitly labeled as sample content.
