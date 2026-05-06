## ADDED Requirements

### Requirement: Personalized diagnosis

The system SHALL translate analysis outputs into personalized pickleball improvement diagnoses that users can understand.

#### Scenario: User views diagnosis panel

- **WHEN** the report includes diagnosis data
- **THEN** the system displays specific issues such as delayed backswing, center-of-gravity drift, recovery delay, or unstable backhand placement with severity and evidence

### Requirement: Actionable improvement suggestions

The system SHALL provide concrete improvement suggestions linked to each diagnosis.

#### Scenario: User reads an improvement suggestion

- **WHEN** a diagnosis is displayed
- **THEN** the system shows a specific training suggestion, expected outcome, and priority level for that diagnosis

### Requirement: Learning-practice-evaluation loop

The system SHALL present a closed loop from report finding to learning content, practice task, and future evaluation target.

#### Scenario: User follows the training loop

- **WHEN** the user views a recommended training item
- **THEN** the system shows the related report issue, learning content placeholder, practice task, and measurable next-session target

### Requirement: Teaching content placeholders

The system SHALL include credible placeholders for teaching videos and motion comparison without implying that real video or 3D assets are already connected.

#### Scenario: Teaching module is rendered

- **WHEN** the teaching section is displayed
- **THEN** the system presents video and motion comparison modules as product-ready placeholders tied to report diagnoses

### Requirement: Progress narrative

The system SHALL show how repeated reports can track improvement over time.

#### Scenario: User views progress context

- **WHEN** the training feedback section is visible
- **THEN** the system displays at least one previous-current-next comparison or goal indicator that explains how the platform supports continuous improvement
