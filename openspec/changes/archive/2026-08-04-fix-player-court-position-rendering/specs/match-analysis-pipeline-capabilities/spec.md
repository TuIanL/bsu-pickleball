## ADDED Requirements

### Requirement: Projection diagnostics expose per-sample details
The match-analysis pipeline SHALL emit a `projection_diagnostics.json` artifact that records, for every tracked player sample, the footpoint method used, raw and smoothed court coordinates, projection confidence, and the reason the sample was accepted or filtered.

#### Scenario: Sample accepted
- **WHEN** a player sample projects to a court position within `0 ≤ court_x ≤ 20` and `0 ≤ court_y ≤ 44`
- **THEN** the diagnostics entry SHALL record `projection_status="accepted"` together with the chosen footpoint method, raw court coordinates, smoothed court coordinates, and confidence

#### Scenario: Sample filtered out of range
- **WHEN** a player sample projects to a court position outside the allowed player bounds (`-4 ≤ court_x ≤ 24` and `-8 ≤ court_y ≤ 52`)
- **THEN** the diagnostics entry SHALL record `projection_status="filtered_out_of_range"` together with `filter_reason` describing the offending axis
- **AND** the sample SHALL NOT be written to the main player trajectory artifact with a `[0, 0]` fallback

#### Scenario: Player stands outside the court bounds (serve position)
- **WHEN** a player sample projects to a court position outside the standard court (`0..20` x `0..44`) but within the allowed player bounds (`-4..24` x `-8..52`)
- **THEN** the sample SHALL be recorded with `projection_status="out_of_bounds_allowed"`
- **AND** the sample SHALL be written to the main player trajectory artifact so the minimap can render the player outside the court lines (e.g. while serving from behind the baseline)
- **AND** the diagnostics entry SHALL note the `in_bounds=false` condition without treating it as an error

#### Scenario: Ball samples keep strict bounds
- **WHEN** a ball sample projects to a court position outside the standard court bounds
- **THEN** the ball trajectory SHALL keep its existing strict validation and SHALL NOT be relaxed by the player out-of-bounds allowance

#### Scenario: Footpoint falls back to bbox with explicit metadata
- **WHEN** the configured method is `hybrid` but pose keypoints are unavailable for a sample
- **THEN** the footpoint SHALL fall back to the bbox bottom-center
- **AND** the diagnostics entry SHALL record `footpoint_method="bbox_bottom_center"` together with `pose_unavailable=true` in metadata
- **AND** when the bbox bottom is near the frame edge, the entry SHALL also record `near_frame_bottom=true`

### Requirement: Calibration enforces baseline Y monotonicity
The manual court calibration page SHALL validate that the two near-baseline corner points have larger image Y than the two far-baseline corner points, and SHALL warn the user when the baseline order appears reversed.

#### Scenario: Calibration baselines are in expected order
- **WHEN** the user finishes selecting four court corners
- **THEN** the calibration page SHALL compute the average image Y of the two far-baseline corners and the two near-baseline corners
- **AND** if `near_baseline_avg_y - far_baseline_avg_y` is greater than a reasonable threshold, the page SHALL accept the calibration without further prompt

#### Scenario: Calibration baselines appear reversed
- **WHEN** the user finishes selecting four court corners
- **AND** the near-baseline average image Y is less than the far-baseline average image Y (or the difference is below the threshold)
- **THEN** the calibration page SHALL surface a confirmation prompt such as "近端与远端底线可能颠倒，请确认画面顶/底对应的场地底线"
- **AND** the user MAY proceed with the calibration after confirming

#### Scenario: Calibration Y values are missing or non-finite
- **WHEN** one or more of the four corner image Y values are not finite
- **THEN** the calibration page SHALL treat the order check as inconclusive and proceed without prompting