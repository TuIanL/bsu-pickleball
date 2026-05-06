# report-detail-pages Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Typed report detail pages
The system SHALL provide focused report pages for supported analysis types.

#### Scenario: User opens landing report
- **WHEN** the user opens `/reports/landing`
- **THEN** the system presents landing or placement analysis with metrics, court heat or landing visualization, and coach-readable interpretation

#### Scenario: User opens movement report
- **WHEN** the user opens `/reports/movement`
- **THEN** the system presents movement or court coverage analysis with metrics, path or balance visualization, and coach-readable interpretation

#### Scenario: User opens rally report
- **WHEN** the user opens `/reports/rally`
- **THEN** the system presents rally tactics analysis with rally-level metrics, shot pattern summaries, and tactical interpretation

#### Scenario: User opens diagnosis report
- **WHEN** the user opens `/reports/diagnosis`
- **THEN** the system presents motion diagnosis content with evidence, severity, suggested correction, and links to relevant training recommendations

### Requirement: Report metrics and interpretation
Each report detail page SHALL pair numeric metrics with explanatory coaching context.

#### Scenario: User reads a report page
- **WHEN** a report detail page is displayed
- **THEN** the system shows core metrics, trend or comparison context, and at least one explanatory insight that translates data into action

### Requirement: Report visualizations
Report detail pages SHALL include visual analysis elements appropriate to the selected report type.

#### Scenario: User views a report visualization
- **WHEN** a report detail page is displayed
- **THEN** the system shows a chart, mini court map, heat visualization, route visualization, movement path, skill rating, or equivalent visual module that matches the selected report type

### Requirement: Report-to-training bridge
Report detail pages SHALL provide a clear path from findings to recommended practice.

#### Scenario: User sees a trainable weakness
- **WHEN** a report detail page identifies a weakness or improvement area
- **THEN** the system shows a training recommendation link or action related to that finding

### Requirement: Local mock report data
Report detail pages SHALL render from structured local mock data.

#### Scenario: Developer replaces mock report data later
- **WHEN** report definitions, metrics, insights, visualizations, and training links are inspected
- **THEN** they are represented as structured data objects rather than hard-coded unrelated page fragments

