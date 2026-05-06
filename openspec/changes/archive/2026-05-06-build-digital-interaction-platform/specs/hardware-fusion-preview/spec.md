## ADDED Requirements

### Requirement: Phase-two hardware preview labeling

The system SHALL clearly label TENG-IMU smart paddle features as a phase-two preview when displaying simulated hardware metrics.

#### Scenario: User views smart paddle preview

- **WHEN** the hardware fusion section is displayed
- **THEN** the system identifies the section as a future smart paddle integration preview and does not present simulated values as live hardware data

### Requirement: Sensor metric display

The system SHALL display simulated TENG and IMU metrics that align with the project plan's smart paddle concept.

#### Scenario: Simulated sensor metrics are shown

- **WHEN** the user views the hardware preview
- **THEN** the system shows sweet-zone hit rate, impact intensity, swing speed, swing path, and hit-quality score from structured demo data

### Requirement: Sweet-zone visualization

The system SHALL visualize the 3 by 3 TENG sweet-zone concept on a paddle face or grid representation.

#### Scenario: User views sweet-zone data

- **WHEN** the smart paddle preview is visible
- **THEN** the system displays a 3 by 3 contact grid with a highlighted hit location or distribution

### Requirement: Visual and sensor fusion narrative

The system SHALL explain how visual analysis and TENG-IMU data combine into a richer performance report.

#### Scenario: User reads fusion explanation

- **WHEN** the fusion preview section is visible
- **THEN** the system connects macro visual indicators such as ball route and player movement with micro paddle indicators such as contact point, force, and swing motion

### Requirement: Future data replacement path

The system SHALL keep hardware preview data separate from visual report data so future live sensor feeds can replace the simulated source.

#### Scenario: Developer inspects data structure

- **WHEN** implementation defines demo data for the hardware preview
- **THEN** hardware sensor values are represented as a separate structured data object from visual report events
