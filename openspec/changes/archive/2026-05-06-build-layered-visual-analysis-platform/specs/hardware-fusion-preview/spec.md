## ADDED Requirements

### Requirement: Dedicated hardware fusion page
The system SHALL provide a dedicated hardware page for the phase-two TENG-IMU smart paddle preview.

#### Scenario: User opens hardware page
- **WHEN** the user navigates to `/hardware`
- **THEN** the system displays the smart paddle preview, simulated sensor metrics, sweet-zone visualization, and visual-sensor fusion narrative as a focused page rather than an inline long-page section

## MODIFIED Requirements

### Requirement: Phase-two hardware preview labeling

The system SHALL clearly label TENG-IMU smart paddle features as a phase-two preview when displaying simulated hardware metrics on the hardware page or in any cross-page preview.

#### Scenario: User views smart paddle preview

- **WHEN** the hardware fusion page or hardware preview card is displayed
- **THEN** the system identifies the content as a future smart paddle integration preview and does not present simulated values as live hardware data

### Requirement: Visual and sensor fusion narrative

The system SHALL explain how visual analysis and TENG-IMU data combine into a richer performance report from the dedicated hardware page.

#### Scenario: User reads fusion explanation

- **WHEN** the hardware fusion page is visible
- **THEN** the system connects macro visual indicators such as ball route and player movement with micro paddle indicators such as contact point, force, and swing motion
