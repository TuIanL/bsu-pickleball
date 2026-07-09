# pose-estimation-engine Delta Spec

## MODIFIED Requirements

### Requirement: Frame-level pose estimation
The backend SHALL run RTMPose on court-relevant tracked player boxes from processed video frames and emit normalized frame-level pose results.

#### Scenario: Tracked player boxes are available
- **WHEN** a processed video frame has one or more tracked player boxes that remain eligible after court-relevance filtering
- **THEN** the pose engine estimates keypoints for each eligible tracked subject and associates each pose result with `frame_index`, `timestamp_seconds`, and `track_id`

#### Scenario: Tracked person is outside match bounds
- **WHEN** a processed video frame has a tracked person whose projected footpoint is outside the configured match-relevant court bounds
- **THEN** the pose engine does not run or persist a renderable pose subject for that person

#### Scenario: No player boxes are available
- **WHEN** a processed video frame has no usable court-relevant player boxes
- **THEN** the pose engine skips that frame without fabricating skeleton keypoints

#### Scenario: Low-confidence keypoints are returned
- **WHEN** RTMPose returns keypoints whose confidence values are near the configured thresholds
- **THEN** keypoint visibility SHALL use hysteresis: keypoints transition from invisible to visible when confidence >= enter_threshold (default 0.30), and from visible to invisible only when confidence drops below exit_threshold (default 0.20)
- **AND** keypoints already marked visible SHALL retain visibility through brief confidence dips between exit_threshold and enter_threshold, eliminating flicker
- **AND** keypoints with confidence below exit_threshold SHALL be marked invisible immediately regardless of prior state
- **AND** both enter_threshold and exit_threshold SHALL be independently configurable via environment variables

#### Scenario: Distant players produce stable skeletons
- **WHEN** a distant player's bounding box is detected with PersonDetector confidence as low as 0.15
- **THEN** the detection SHALL be forwarded to pose estimation (PersonDetector.conf_threshold lowered from 0.25 to 0.15)
- **AND** the pose engine SHALL apply hysteresis to keypoint visibility for that player, reducing skeleton flicker caused by marginally low keypoint confidence at long range
- **AND** low-confidence detections SHALL still be subject to court-relevance and ROI filtering downstream
