## ADDED Requirements

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
