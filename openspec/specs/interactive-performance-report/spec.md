# interactive-performance-report Specification

## Purpose
TBD - created by archiving change build-digital-interaction-platform. Update Purpose after archive.
## Requirements
### Requirement: Report-first entry experience

The system SHALL provide a product demo experience where users can enter a pickleball post-session analysis report through the layered overview, visual analysis workspace, and focused report detail pages rather than relying on one long report-first scrolling page.

#### Scenario: User opens the site on desktop

- **WHEN** the user loads the website on a desktop viewport
- **THEN** the first viewport presents the platform name, product value, current demo match context, and clear entry points into visual analysis and report detail workflows

#### Scenario: User opens the site on mobile

- **WHEN** the user loads the website on a mobile viewport
- **THEN** the overview, visual analysis entry, and report entry controls remain visible in a vertically stacked layout without text overlap or horizontal scrolling

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

### Requirement: Responsive report layout

The system SHALL keep report panels, controls, text, navigation, and visualizations legible across desktop and mobile viewport sizes.

#### Scenario: Layout adapts to narrow screens

- **WHEN** the viewport width is narrow
- **THEN** report pages and visual analysis modules stack into stable blocks with constrained visualization aspect ratios and no incoherent overlap

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

### Requirement: Algorithm-derived ball facts in reports
The system SHALL allow completed real-job reports to display ball trajectory and bounce candidate facts when those facts are backed by generated pipeline artifacts.

#### Scenario: Ball trajectory facts are available
- **WHEN** a completed uploaded-video job has ball trajectory or cleaned ball trajectory artifacts
- **THEN** report modules MAY show trajectory availability, sample coverage, candidate quality, or synchronized visual references derived from those artifacts
- **AND** the report SHALL distinguish those fields as algorithm-derived uploaded-video results

#### Scenario: Bounce candidate facts are available
- **WHEN** a completed uploaded-video job has `bounce_events.json`
- **THEN** report modules MAY show candidate bounce counts, timestamps, confidence, and review links
- **AND** the report MUST label them as candidates unless a later capability provides confirmed event semantics

#### Scenario: Ball facts are unavailable
- **WHEN** a real-job report module would use ball facts but the corresponding artifacts are skipped, unavailable, partial, failed, or absent
- **THEN** the report SHALL omit that module or mark it unavailable with the relevant stage reason
- **AND** the report MUST NOT fill the module with sample landing, shot, or ball-route data

### Requirement: Unsupported match semantics remain unavailable
The system SHALL keep shot classification, rally segmentation, scoring, landing-statistics, and tactical conclusions unavailable for real jobs until dedicated capabilities implement them.

#### Scenario: Report asks for shot or rally semantics
- **WHEN** a real-job report surface requires shot type, rally boundary, rally winner, score, fault, landing distribution, or tactical recommendation
- **THEN** the report SHALL use unavailable, limited, or sample-only state as appropriate
- **AND** the report MUST NOT infer those semantics solely from ball trajectory or bounce candidate artifacts

