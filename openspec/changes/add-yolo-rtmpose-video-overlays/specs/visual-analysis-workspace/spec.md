## MODIFIED Requirements

### Requirement: Video-first analysis workspace
The system SHALL provide a dedicated visual analysis page centered on a job-aware pickleball video player that uses simulated visuals for demo routes and the uploaded source video for completed real jobs when available.

#### Scenario: User opens the visual analysis page
- **WHEN** the user navigates to `/vision`
- **THEN** the primary content is a large video-style analysis card with a 16:9 visual area, match score, current rally context, video controls, and timeline markers

#### Scenario: User views the simulated video layer
- **WHEN** the video analysis card is visible without a real job context
- **THEN** the system shows a pickleball court mockup with court lines, kitchen zones, player markers or boxes, shot trajectories, landing or heat indicators, and AI labels

#### Scenario: User views a completed real-job video layer
- **WHEN** the video analysis card is visible for a completed uploaded-video job with a source video URL
- **THEN** the system plays the uploaded source video in the primary visual area instead of showing only the simulated SVG scene

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job data from backend report payloads, available MVP pipeline algorithm results, and video overlay artifacts in addition to the existing demo data.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, timeline markers, overlay labels, highlights, coach notes, shot explorer, and report actions render from that job's report payload, algorithm-derived fields, and available detection or pose overlays

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, supported MVP metrics, detection boxes, or pose keypoints
- **THEN** the workspace shows a limited-analysis state for unavailable modules instead of filling those modules with unrelated demo shot or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data

## ADDED Requirements

### Requirement: Synchronized person-box overlay playback
The visual analysis workspace SHALL render YOLO person boxes over the uploaded source video for completed real jobs when detection overlay data is available.

#### Scenario: Detection overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed detection overlay data
- **THEN** the workspace draws the nearest matching frame's person boxes with confidence and track labels aligned to the rendered video frame

#### Scenario: Video is letterboxed or resized
- **WHEN** the video is displayed with object-fit sizing that differs from the source frame dimensions
- **THEN** the overlay transforms source pixel coordinates into rendered video coordinates without drifting into the letterbox area

#### Scenario: Detection overlay data is unavailable
- **WHEN** the job has no detection overlay artifact
- **THEN** the workspace plays the source video and shows a clear no-detection-overlay state instead of displaying simulated player markers as real detections

### Requirement: Synchronized skeleton overlay playback
The visual analysis workspace SHALL render RTMPose skeleton keypoints and joint connections over the uploaded source video for completed real jobs when pose overlay data is available.

#### Scenario: Pose overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed pose overlay data
- **THEN** the workspace draws visible joints and skeleton connections for the nearest matching processed frame

#### Scenario: Pose overlay is disabled by the user
- **WHEN** the user turns off the skeleton overlay control
- **THEN** the workspace hides skeleton keypoints while keeping the source video and other enabled overlays visible

#### Scenario: Pose overlay data is unavailable
- **WHEN** YOLO boxes are available but RTMPose keypoints are not
- **THEN** the workspace can still show person boxes and labels the skeleton layer as unavailable

### Requirement: Real-overlay source clarity
The visual analysis workspace SHALL distinguish real video overlays from demo overlays and from unavailable model output.

#### Scenario: Real overlays are shown
- **WHEN** source video, detection overlays, or skeleton overlays are rendered for a completed real job
- **THEN** the workspace labels the visible layers as generated from the uploaded video and includes job/source metadata in the page context

#### Scenario: Model output is missing
- **WHEN** detection or pose inference did not run, failed, or produced no usable results
- **THEN** the workspace explains the missing prerequisite such as model inference disabled, RTMPose assets unavailable, no players detected, or video quality too low
