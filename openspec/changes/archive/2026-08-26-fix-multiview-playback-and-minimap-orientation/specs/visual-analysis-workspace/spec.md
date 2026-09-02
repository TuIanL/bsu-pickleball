## MODIFIED Requirements

### Requirement: Smooth real-overlay playback for high-frame-rate video
The visual analysis workspace SHALL synchronize real detection and pose overlays to the currently mounted source video playback using frame-aligned timing and smooth transitions suitable for 60fps source footage. For a multiview job, the workspace SHALL convert the active source media time to canonical time using that display view's timestamp mapping before resolving all canonical overlay layers.

#### Scenario: Real video is playing
- **WHEN** a completed real-job source video is actively playing with frame-indexed overlay data
- **THEN** the workspace updates overlay rendering from video-frame timing rather than relying only on low-frequency native timeupdate events

#### Scenario: Adjacent overlay frames are available
- **WHEN** the current playback time falls between two processed overlay frames with matching track identifiers
- **THEN** the workspace renders boxes and skeleton keypoints using interpolated or equivalently smoothed positions between those frames

#### Scenario: Overlay frames cannot be safely interpolated
- **WHEN** surrounding overlay frames are missing, track identifiers do not match, or pose keypoints cannot be paired
- **THEN** the workspace falls back to the nearest valid processed overlay frame without hiding the source video

#### Scenario: User changes active multiview video while playing
- **WHEN** a user switches from one available display view to another while the source video is playing
- **THEN** the workspace SHALL bind video events and frame callbacks to the newly mounted video element
- **AND** person boxes, ball layers, and HUD data SHALL continue updating from that new element's mapped canonical time
- **AND** the workspace SHALL NOT retain overlay time updates from the unmounted source video

#### Scenario: User changes active multiview video while paused
- **WHEN** a user switches display views while the source video is paused
- **THEN** the target view SHALL seek to the equivalent canonical instant
- **AND** it SHALL remain paused after the seek

#### Scenario: Active playback survives display-view change
- **WHEN** a user switches display views while the source video is playing
- **THEN** the target view SHALL seek to the equivalent canonical instant using its source timestamp mapping
- **AND** after the target seek completes, the target video SHALL continue playback unless playback is rejected by the browser or the user paused during loading

## ADDED Requirements

### Requirement: Display-view-oriented court HUD
The visual analysis workspace SHALL orient the court HUD according to the active display view's persisted `courtOrientation`, while preserving all player identities and canonical analysis data.

#### Scenario: User views the reference orientation
- **WHEN** the active display view has `courtOrientation=identity` or no valid orientation metadata
- **THEN** the court HUD SHALL render using its existing canonical orientation

#### Scenario: User switches to an opposed camera view
- **WHEN** the user switches to a display view whose `courtOrientation=rotate_180`
- **THEN** the court HUD SHALL rotate the court, player paths, current player points, ball path, ball point, and bounce markers by 180 degrees in the display mapping
- **AND** the video-near baseline SHALL correspond to the HUD near-side baseline for that view

#### Scenario: User views a mirrored orientation
- **WHEN** the active display view declares `mirror_x` or `mirror_y`
- **THEN** the court HUD SHALL apply the declared mirror transform consistently to the court and every displayed spatial layer

#### Scenario: Orientation changes do not alter analysis identity or evidence
- **WHEN** the court HUD changes orientation because the display view changes
- **THEN** P1–P4 labels, identity colors, canonical player tracks, ball trajectory values, and bounce event values SHALL remain unchanged
- **AND** only their SVG display coordinates and court direction SHALL change
