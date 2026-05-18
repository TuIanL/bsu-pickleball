# visual-analysis-workspace Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
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

### Requirement: AI overlay labels
The system SHALL display contextual AI labels over the simulated video to explain important shot patterns and risks.

#### Scenario: User views active rally overlays
- **WHEN** an active rally is displayed in the visual analysis workspace
- **THEN** the system shows labels such as third-shot drop, high-risk drive, kitchen error, winning pattern, or equivalent original copy tied to mock rally events

### Requirement: Highlights and coach notes
The system SHALL pair video review with readable highlights and coach-like insights.

#### Scenario: User reviews coach notes
- **WHEN** the visual analysis page is visible
- **THEN** the system displays three to five AI coach notes covering strengths, risks, major errors, and training recommendations with distinct status treatments

#### Scenario: User reviews highlights
- **WHEN** key moments are available in mock data
- **THEN** the system displays a highlights list with rally title, time context, result or category, and an action affordance to inspect the moment

### Requirement: Rally timeline and shot filtering
The system SHALL include lightweight interaction for rally review and shot exploration without backend dependencies.

#### Scenario: User selects a shot filter chip
- **WHEN** the user clicks a shot filter such as All, Serve, Return, Third Shot, Dink, Drive, Reset, Volley, Smash, or Error
- **THEN** the selected chip visibly changes state and the displayed shot list or shot summary reflects that local selection

#### Scenario: User hovers timeline marker
- **WHEN** the user hovers or focuses a timeline marker
- **THEN** the system exposes a concise label or tooltip for the represented key event

### Requirement: Video workspace report actions
The system SHALL present clear report actions from the visual analysis workspace.

#### Scenario: User views report actions
- **WHEN** the user reviews the video analysis workspace
- **THEN** the system shows actions for landing analysis report, movement analysis report, rally tactics report, and motion diagnosis report

#### Scenario: User selects a report action
- **WHEN** the user clicks one of the report actions
- **THEN** the system navigates to the matching `/reports/:type` report detail page

### Requirement: Premium sports-tech visual style
The system SHALL make the visual analysis workspace feel like a mature AI sports video analytics product with a bright sports-tech theme.

#### Scenario: User views the visual analysis page
- **WHEN** the visual analysis page renders
- **THEN** the system uses bright primary surfaces, restrained green highlights, preserved blue/orange/red status accents, clean cards, subtle borders, hover states, and video-first hierarchy rather than a heavy dark interface or a generic admin-table layout

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

### Requirement: Job-aware visual analysis states
The system SHALL communicate when a job-specific visual analysis result is not ready or cannot be loaded.

#### Scenario: User opens visual analysis before completion
- **WHEN** the user opens a visual analysis route for a job that is queued or processing
- **THEN** the system routes back to or displays the job status state instead of showing incomplete report visuals

#### Scenario: User opens visual analysis for a failed job
- **WHEN** the user opens a visual analysis route for a failed job
- **THEN** the system shows a stable failed-analysis state with a return or retry action

#### Scenario: User opens visual analysis for an unknown job
- **WHEN** the user opens a visual analysis route for a job identifier that cannot be found
- **THEN** the system shows a stable not-found or fallback state without broken overlays

### Requirement: Result-source clarity
The system SHALL distinguish demo analysis, limited real analysis, and algorithm-derived job analysis without disrupting the visual hierarchy.

#### Scenario: User views demo analysis
- **WHEN** the visual analysis workspace is rendering local demo data
- **THEN** the system provides a subtle demo/sample indication in the page context or metadata

#### Scenario: User views algorithm-derived job analysis
- **WHEN** the visual analysis workspace is rendering a completed uploaded-video job with pipeline output
- **THEN** the system shows job, match, uploaded video, calibration, and generated result metadata associated with the analysis

#### Scenario: User views limited job analysis
- **WHEN** the visual analysis workspace is rendering a completed job that lacks enough algorithm output for a module
- **THEN** the system labels the affected module as unavailable or limited and explains the missing prerequisite such as calibration or detections

### Requirement: Algorithm-backed movement visualization
The system SHALL visualize available player movement and court coverage data from backend pipeline results in the visual analysis workspace.

#### Scenario: Projected tracks are available
- **WHEN** a completed real analysis job includes projected player tracks
- **THEN** the workspace renders movement paths, player positions, or heat distribution from those tracks rather than static demo coordinates

#### Scenario: Movement metrics are available
- **WHEN** a completed real analysis job includes distance, speed, kitchen dwell, doubles spacing, or heatmap metrics
- **THEN** the workspace presents movement-focused feedback derived from those metrics with readable labels and values

#### Scenario: No detections are produced
- **WHEN** the backend pipeline completes but produces no usable player detections or projected positions
- **THEN** the workspace shows an analysis-completed-but-no-tracks state with guidance to check camera angle, calibration, model setup, or video quality

### Requirement: True RTMPose skeleton rendering verification
The visual analysis workspace SHALL render skeleton joints and edges from true RTMPose pose overlay artifacts for completed real jobs and preserve clear degraded states when those artifacts are unavailable.

#### Scenario: True RTMPose overlay is loaded
- **WHEN** a user opens a completed real-job workspace whose raw result references an available pose overlay generated by configured RTMPose inference
- **THEN** the workspace fetches the pose artifact, synchronizes it to the source video, and draws visible keypoints and skeleton edges for the nearest processed frame

#### Scenario: Pose overlay is unavailable
- **WHEN** a completed real-job workspace has tracking boxes but the pose stage is skipped, unavailable, failed, or no-pose
- **THEN** the workspace keeps the source video and person boxes usable while communicating that skeleton joints are unavailable for the reported reason

#### Scenario: Skeleton layer is toggled
- **WHEN** true RTMPose keypoints are available and the user toggles the skeleton overlay control
- **THEN** the workspace hides or shows skeleton joints without changing video playback, person boxes, or loaded artifact state

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

### Requirement: Synchronized ball overlay playback
The visual analysis workspace SHALL render backend-generated ball points and ball trajectories over uploaded source video for completed real jobs when ball overlay data is available.

#### Scenario: Ball overlay data is available
- **WHEN** the user plays or scrubs a completed real-job video with frame-indexed ball overlay data
- **THEN** the workspace draws the matching playback frame's ball point or trajectory segment aligned to the rendered video frame

#### Scenario: Ball trajectory includes repaired points
- **WHEN** the ball overlay artifact includes observed and repaired or predicted trajectory points
- **THEN** the workspace renders the point sources with distinguishable visual treatment or labels so repaired motion is not presented as direct detection

#### Scenario: Video is resized or letterboxed
- **WHEN** the video display size differs from the source frame dimensions
- **THEN** ball overlay coordinates are transformed into rendered video coordinates without drifting into letterbox areas

### Requirement: Ball overlay source clarity
The visual analysis workspace SHALL distinguish real ball overlays from demo shot trajectories and unavailable ball-tracking output.

#### Scenario: Real ball overlay is unavailable
- **WHEN** a completed real job has no available ball overlay artifact
- **THEN** the workspace does not render demo shot trajectories as real ball data and shows a clear unavailable or skipped state for ball tracking

#### Scenario: Real ball overlay is partial
- **WHEN** a completed real job has partial ball trajectory data
- **THEN** the workspace can render available points while communicating the partial status from the backend artifact detail

#### Scenario: Demo analysis is shown
- **WHEN** the visual analysis workspace is rendering local demo data without a real job context
- **THEN** existing simulated shot paths may remain visible as demo visuals and are not labeled as uploaded-video ball tracking

### Requirement: Ball overlay controls
The visual analysis workspace SHALL provide user controls for showing or hiding real ball overlays independently from player boxes and skeleton overlays when ball data is available.

#### Scenario: User toggles ball overlay
- **WHEN** real ball overlay data is loaded and the user changes the ball overlay control
- **THEN** the workspace hides or shows ball points and trajectory segments without changing video playback, player boxes, skeletons, or loaded artifact state

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

