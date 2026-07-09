# skeleton-overlay-gap-handling Specification

## Purpose
Define how the frontend pose overlay playback handles gaps in the skeleton data stream, preventing visual freezing when pose frames are absent for extended durations. TBD - created by syncing change fix-skeleton-stutter.

## Requirements
### Requirement: Long gap detection threshold
The frontend overlay player SHALL define a configurable threshold (in frames or seconds) for detecting extended gaps in the pose overlay data stream.

#### Scenario: Gap threshold exceeded
- **WHEN** the playback reaches a timestamp where the nearest pose frame is farther than the configured threshold
- **THEN** the overlay SHALL fade out or hide the skeleton instead of continuing to display the last known pose

#### Scenario: Gap threshold not exceeded
- **WHEN** the next pose frame is within the configured threshold
- **THEN** the existing `findFrameWindow` + `resolvePoseFrame` interpolation SHALL be used as before

### Requirement: Fade-out transition
When a skeleton is hidden due to gap threshold, the transition SHALL be gradual (fade-out) rather than instantaneous, to avoid visual jitter.

#### Scenario: Fade-out on long gap
- **WHEN** the gap threshold is exceeded at timestamp T
- **THEN** the skeleton opacity SHALL linearly decrease to 0 over a configurable transition duration (default 0.3 seconds)

#### Scenario: Fade-in on gap exit
- **WHEN** playback re-enters a region with available pose frames after a gap
- **THEN** the skeleton opacity SHALL linearly increase from 0 to 1 over the same transition duration
