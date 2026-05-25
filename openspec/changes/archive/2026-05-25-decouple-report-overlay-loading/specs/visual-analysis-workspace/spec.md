## ADDED Requirements

### Requirement: Independent real-overlay artifact loading
The visual analysis workspace SHALL load heavyweight tracking and pose overlay artifacts as independent visual layers so the completed-job video shell, status rail, and report navigation remain usable while those artifacts are loading or unavailable.

#### Scenario: Completed job shell loads before overlays
- **WHEN** the user opens a completed real-job visual analysis route and the job summary, report payload, and source video reference are available
- **THEN** the workspace renders the source video area, job metadata, status rail, and report actions even if tracking or pose overlay artifacts are still downloading

#### Scenario: Tracking overlay loads before pose overlay
- **WHEN** tracking overlay data becomes available before pose overlay data
- **THEN** the workspace can render person boxes and mark the skeleton layer as loading, unavailable, or failed without blocking playback

#### Scenario: Pose overlay is slow or large
- **WHEN** a completed real job references a large pose overlay artifact that takes noticeably longer to download or parse
- **THEN** the workspace keeps the source video, person-box layer state, status rail, and report navigation interactive while the pose layer remains in a loading state

#### Scenario: Overlay artifact request fails
- **WHEN** a tracking or pose overlay artifact request fails after the completed job shell has loaded
- **THEN** the workspace marks only that overlay layer as failed or unavailable and does not replace the whole page with a report-loading or analysis-loading state

## MODIFIED Requirements

### Requirement: Job-specific visual analysis data
The system SHALL allow the visual analysis workspace to render completed analysis job video and status data from backend report payloads, available MVP pipeline algorithm results, and person/pose overlay artifacts in addition to the existing demo data, with heavyweight overlays loaded independently from the initial completed-job shell.

#### Scenario: User opens visual analysis for a completed real job
- **WHEN** the user navigates to a visual analysis route associated with a completed uploaded-video analysis job
- **THEN** the video analysis card, source video, report-derived timeline markers, and status rail render from that job's report payload and available algorithm-derived fields while detection or pose overlays may load as independent layers

#### Scenario: Completed real job only has limited algorithm output
- **WHEN** the completed job lacks calibration, projected tracks, supported MVP metrics, detection boxes, or pose keypoints
- **THEN** the workspace shows limited or unavailable states in the status rail and lower-level analysis views instead of filling modules with unrelated demo shot, landing, ball, or tactical labels

#### Scenario: User opens visual analysis without job context
- **WHEN** the user navigates to the existing demo visual analysis route without a job identifier
- **THEN** the workspace continues to render the local demo analysis data with clear sample context

### Requirement: Synchronized person-box overlay playback
The visual analysis workspace SHALL render court-relevant YOLO person boxes over the uploaded source video for completed real jobs when detection overlay data is available, without preventing the base video workspace from rendering while the detection artifact loads.

#### Scenario: Detection overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed detection overlay data
- **THEN** the workspace draws the matching playback frame's court-relevant person boxes with confidence and track labels aligned to the rendered video frame

#### Scenario: Video is letterboxed or resized
- **WHEN** the video is displayed with object-fit sizing that differs from the source frame dimensions
- **THEN** the overlay transforms source pixel coordinates into rendered video coordinates without drifting into the letterbox area

#### Scenario: Detection overlay data is still loading
- **WHEN** a completed real-job video is ready but the detection overlay artifact is still loading
- **THEN** the workspace keeps the source video playable and labels the person-box layer as loading

#### Scenario: Detection overlay data is unavailable
- **WHEN** the job has no detection overlay artifact
- **THEN** the workspace plays the source video and shows a clear no-detection-overlay state instead of displaying simulated player markers as real detections

### Requirement: Synchronized skeleton overlay playback
The visual analysis workspace SHALL render court-relevant RTMPose skeleton keypoints and joint connections over the uploaded source video for completed real jobs when pose overlay data is available, without preventing the base video workspace from rendering while the pose artifact loads.

#### Scenario: Pose overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed pose overlay data
- **THEN** the workspace draws visible joints and skeleton connections for the matching playback frame using only court-relevant pose subjects

#### Scenario: Pose overlay is disabled by the user
- **WHEN** the user turns off the skeleton overlay control
- **THEN** the workspace hides skeleton keypoints while keeping the source video and other enabled overlays visible

#### Scenario: Pose overlay data is still loading
- **WHEN** a completed real-job video is ready but the pose overlay artifact is still downloading or parsing
- **THEN** the workspace keeps playback and other available layers usable while labeling the skeleton layer as loading

#### Scenario: Pose overlay data is unavailable
- **WHEN** YOLO boxes are available but RTMPose keypoints are not
- **THEN** the workspace can still show person boxes and labels the skeleton layer as unavailable
