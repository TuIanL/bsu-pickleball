# visual-analysis-workspace Delta

## MODIFIED Requirements

### Requirement: Right-side analysis status rail

The visual analysis workspace SHALL provide a right-side rail beside the primary video area for completed job results, whose primary content is the segment panel (per `analysis-view-segment-panel`); the previous task-status and overlay-availability information SHALL collapse into an on-demand info popover instead of occupying the rail, while report entry actions stay persistently reachable.

#### Scenario: User opens a completed result on desktop

- **WHEN** a completed job-specific visual analysis page renders on a desktop viewport
- **THEN** the page shows the video viewport as the primary content and a right-side rail whose primary content is the segment panel
- **AND** task status, match metadata, and overlay availability SHALL be available through an info popover
- **AND** report tab actions SHALL remain persistently reachable without opening the popover

#### Scenario: User opens a completed result on a narrow viewport

- **WHEN** a completed job-specific visual analysis page renders on a narrow viewport
- **THEN** the segment rail stacks below or near the video without overlapping the video controls or report actions

#### Scenario: Overlay data is partially available

- **WHEN** a completed job has only some overlay artifacts available
- **THEN** the info popover labels available, unavailable, skipped, or failed video layers without presenting unavailable model output as real analysis

#### Scenario: Info popover does not block primary playback

- **WHEN** the info popover is opened or closed
- **THEN** video playback state, playback position, and overlay layers SHALL remain unchanged
