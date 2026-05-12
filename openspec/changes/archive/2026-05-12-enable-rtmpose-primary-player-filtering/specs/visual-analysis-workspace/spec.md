## MODIFIED Requirements

### Requirement: Synchronized person-box overlay playback
The visual analysis workspace SHALL render selected primary-player YOLO person boxes over the uploaded source video for completed real jobs when detection overlay data is available.

#### Scenario: Detection overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed detection overlay data
- **THEN** the workspace draws the matching playback frame's selected primary-player person boxes with confidence and track labels aligned to the rendered video frame

#### Scenario: Video is letterboxed or resized
- **WHEN** the video is displayed with object-fit sizing that differs from the source frame dimensions
- **THEN** the overlay transforms source pixel coordinates into rendered video coordinates without drifting into the letterbox area

#### Scenario: Detection overlay data is unavailable
- **WHEN** the job has no detection overlay artifact
- **THEN** the workspace plays the source video and shows a clear no-detection-overlay state instead of displaying simulated player markers as real detections

### Requirement: Synchronized skeleton overlay playback
The visual analysis workspace SHALL render RTMPose skeleton keypoints and joint connections for selected primary-player subjects over the uploaded source video for completed real jobs when pose overlay data is available.

#### Scenario: Pose overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed pose overlay data
- **THEN** the workspace draws visible joints and skeleton connections for the matching playback frame using selected primary-player pose subjects

#### Scenario: Pose overlay is disabled by the user
- **WHEN** the user turns off the skeleton overlay control
- **THEN** the workspace hides skeleton keypoints while keeping the source video and other enabled overlays visible

#### Scenario: Pose overlay data is unavailable
- **WHEN** YOLO boxes are available but RTMPose keypoints are not
- **THEN** the workspace can still show person boxes and labels the skeleton layer as unavailable

### Requirement: Real-overlay source clarity
The visual analysis workspace SHALL distinguish real video overlays from demo overlays and from unavailable model output, including RTMPose configuration and primary-player filtering outcomes.

#### Scenario: Real overlays are shown
- **WHEN** source video, detection overlays, or skeleton overlays are rendered for a completed real job
- **THEN** the workspace labels the visible layers as generated from the uploaded video and includes job/source metadata in the page context

#### Scenario: RTMPose is not configured or disabled
- **WHEN** detection overlays are available but pose inference was disabled, missing assets, failed runtime loading, or unsupported schema prevented skeleton generation
- **THEN** the workspace explains the RTMPose-specific unavailable reason without implying that player detection failed

#### Scenario: Primary-player filtering selected no subjects
- **WHEN** model inference runs but no tracked people satisfy primary-player selection for overlay or pose rendering
- **THEN** the workspace shows a completed-but-no-primary-players state with guidance to check confidence thresholds, player count configuration, camera angle, video quality, or filtering settings
