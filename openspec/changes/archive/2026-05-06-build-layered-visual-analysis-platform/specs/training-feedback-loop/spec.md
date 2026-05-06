## ADDED Requirements

### Requirement: Dedicated training recommendations page
The system SHALL provide a dedicated training page for recommended drills and progress-oriented practice guidance.

#### Scenario: User opens training page
- **WHEN** the user navigates to `/training`
- **THEN** the system displays recommended drills, training goals, difficulty or duration context, evidence from analysis data, and actions to add or follow a training plan

#### Scenario: User follows training link from report
- **WHEN** the user selects a training recommendation from a report detail page or coach note
- **THEN** the system opens or highlights the related training recommendation in the training experience

## MODIFIED Requirements

### Requirement: Learning-practice-evaluation loop

The system SHALL present a closed loop from report finding to learning content, practice task, and future evaluation target in a dedicated training page and linked report contexts.

#### Scenario: User follows the training loop

- **WHEN** the user views a recommended training item from the training page or from a linked report finding
- **THEN** the system shows the related report issue, learning content placeholder, practice task, and measurable next-session target

### Requirement: Teaching content placeholders

The system SHALL include credible placeholders for teaching videos and motion comparison without implying that real video or 3D assets are already connected.

#### Scenario: Teaching module is rendered

- **WHEN** the teaching section or training page is displayed
- **THEN** the system presents video and motion comparison modules as product-ready placeholders tied to report diagnoses

### Requirement: Progress narrative

The system SHALL show how repeated reports can track improvement over time on the training page and any progress-oriented dashboard modules.

#### Scenario: User views progress context

- **WHEN** the training feedback page or progress module is visible
- **THEN** the system displays at least one previous-current-next comparison, trend chart, or goal indicator that explains how the platform supports continuous improvement
