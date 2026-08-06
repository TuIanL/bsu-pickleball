## ADDED Requirements

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