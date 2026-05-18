## ADDED Requirements

### Requirement: Fullscreen real-video overlay playback
The visual analysis workspace SHALL provide fullscreen playback for real uploaded-video jobs without losing visible person boxes, skeleton joints, overlay toggles, or overlay status labels.

#### Scenario: User enters fullscreen real-video playback
- **WHEN** a user opens fullscreen playback from a completed real-job video that has detection or pose overlay data
- **THEN** the fullscreen surface includes the source video, enabled person-box overlay, enabled skeleton overlay, layer toggles, and playback status labels in the same aligned visual area

#### Scenario: Fullscreen is unavailable
- **WHEN** the browser does not support fullscreen for the video overlay container
- **THEN** the workspace keeps inline playback usable and does not hide or break existing overlays

### Requirement: Smooth real-overlay playback for high-frame-rate video
The visual analysis workspace SHALL synchronize real detection and pose overlays to source video playback using frame-aligned timing and smooth transitions suitable for 60fps source footage.

#### Scenario: Real video is playing
- **WHEN** a completed real-job source video is actively playing with frame-indexed overlay data
- **THEN** the workspace updates overlay rendering from video-frame timing rather than relying only on low-frequency native timeupdate events

#### Scenario: Adjacent overlay frames are available
- **WHEN** the current playback time falls between two processed overlay frames with matching track identifiers
- **THEN** the workspace renders boxes and skeleton keypoints using interpolated or equivalently smoothed positions between those frames

#### Scenario: Overlay frames cannot be safely interpolated
- **WHEN** surrounding overlay frames are missing, track identifiers do not match, or pose keypoints cannot be paired
- **THEN** the workspace falls back to the nearest valid processed overlay frame without hiding the source video

## MODIFIED Requirements

### Requirement: Synchronized person-box overlay playback
The visual analysis workspace SHALL render court-relevant YOLO person boxes over the uploaded source video for completed real jobs when detection overlay data is available.

#### Scenario: Detection overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed detection overlay data
- **THEN** the workspace draws the matching playback frame's court-relevant person boxes with confidence and track labels aligned to the rendered video frame

#### Scenario: Video is letterboxed or resized
- **WHEN** the video is displayed with object-fit sizing that differs from the source frame dimensions
- **THEN** the overlay transforms source pixel coordinates into rendered video coordinates without drifting into the letterbox area

#### Scenario: Detection overlay data is unavailable
- **WHEN** the job has no detection overlay artifact
- **THEN** the workspace plays the source video and shows a clear no-detection-overlay state instead of displaying simulated player markers as real detections

### Requirement: Synchronized skeleton overlay playback
The visual analysis workspace SHALL render court-relevant RTMPose skeleton keypoints and joint connections over the uploaded source video for completed real jobs when pose overlay data is available.

#### Scenario: Pose overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed pose overlay data
- **THEN** the workspace draws visible joints and skeleton connections for the matching playback frame using only court-relevant pose subjects

#### Scenario: Pose overlay is disabled by the user
- **WHEN** the user turns off the skeleton overlay control
- **THEN** the workspace hides skeleton keypoints while keeping the source video and other enabled overlays visible

#### Scenario: Pose overlay data is unavailable
- **WHEN** YOLO boxes are available but RTMPose keypoints are not
- **THEN** the workspace can still show person boxes and labels the skeleton layer as unavailable
