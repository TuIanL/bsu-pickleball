## MODIFIED Requirements

### Requirement: Algorithm-derived feedback copy

The system SHALL translate available algorithm metrics and performance insights into concise coaching feedback for real uploaded-video jobs while avoiding unsupported ball, landing, shot, or rally claims; real-job reports SHALL NOT mix sample-only performance conclusions with algorithm-derived content.

#### Scenario: Movement feedback is available

- **WHEN** the pipeline result includes movement distance, speed, spacing, zone dwell, or heatmap metrics
- **THEN** the report surfaces generate readable feedback that cites those metrics as evidence

#### Scenario: Insight findings are available

- **WHEN** the job has a generated `performance_insights.json` with findings
- **THEN** the report presents findings with their evidence, priority, and linked training recommendations
- **AND** findings whose data is insufficient SHALL be presented as insufficient-evidence states rather than definitive conclusions

#### Scenario: Tactical feedback is not supported by the MVP result

- **WHEN** the report page would otherwise show shot-pattern, rally, landing, ball-trajectory, or motion-diagnosis claims that require unsupported algorithms
- **THEN** the system either hides those claims for the real job or labels them as not available in the current analysis

#### Scenario: Real-job report contains zero demo performance conclusions

- **WHEN** a real-job report is rendered through any path including degradation paths
- **THEN** the report contains no demo performance conclusions such as sample overall scores, sample movement efficiency, or sample diagnosis wording
- **AND** sample content SHALL only appear on routes explicitly labeled as demo/sample

## ADDED Requirements

### Requirement: Performance insights respect unsupported match semantics

Performance insight rules SHALL NOT infer shot classification, rally segmentation, scoring, landing statistics, or tactical conclusions from ball trajectory or bounce candidate artifacts; ball/bounce candidates MAY only appear as a separate algorithm-candidate-facts section without becoming performance findings.

#### Scenario: Insight rule consumes rally timeline windows

- **WHEN** a rule uses manually marked `rally_start` / `rally_end` timeline windows
- **THEN** the finding copy SHALL only express statements scoped to "在人工标记的有效回合窗口中"
- **AND** the finding MUST NOT infer rally outcome, error type, or tactical effect

#### Scenario: Bounce candidates are excluded from findings

- **WHEN** `bounce_events.json` contains candidate events
- **THEN** insight rules MUST NOT produce findings that describe landing control, depth, or placement concentration from those candidates
- **AND** the performance report MAY show candidate counts and confidence as candidate facts only
