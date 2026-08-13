# video-analysis-job-flow Specification

## Purpose
TBD - created by archiving change add-analysis-workflow-backend-foundation. Update Purpose after archive.
## Requirements
### Requirement: New video analysis entry
The system SHALL provide a user-facing entry point for starting a new pickleball video analysis.

#### Scenario: User opens the new analysis page
- **WHEN** the user navigates to the new analysis or upload route
- **THEN** the system displays a video upload workflow with match metadata fields, calibration guidance, a clear action to start analysis, and access to analysis task history

#### Scenario: User accesses upload from primary navigation
- **WHEN** the user selects the video analysis action from the app shell
- **THEN** the system opens the new analysis workflow instead of showing the completed-result workspace or a static demo report

### Requirement: Video upload form states
The system SHALL guide users through valid video selection and required match context before creating an analysis job.

#### Scenario: User selects a supported video
- **WHEN** the user chooses a supported local video file
- **THEN** the system shows the selected file name, size or duration placeholder, and enables analysis submission when required metadata is complete

#### Scenario: User has incomplete upload input
- **WHEN** no video file is selected or required metadata is missing
- **THEN** the system keeps the start-analysis action disabled or presents a clear validation message

### Requirement: Analysis job creation
The system SHALL create a real analysis job by uploading the selected video to the backend, linking the returned backend video identifier to the job request, persisting a durable queued job record, and reserving metadata-only jobs for explicit demo or developer flows.

#### Scenario: User submits a valid real upload request
- **WHEN** the user starts analysis with a selected video and required metadata
- **THEN** the frontend uploads the video file to the backend video upload API, creates an analysis job with the returned `videoId`, and routes the user to the analysis task management page with the new task visible

#### Scenario: User submits a calibrated backend video reference
- **WHEN** the user starts analysis with a valid backend video identifier, calibration identifier, and required metadata
- **THEN** the backend creates a durable queued analysis job linked to that video and calibration and schedules the MVP analysis pipeline for worker execution

#### Scenario: Duplicate real submission is detected
- **WHEN** the user submits the same video, calibration, and analysis configuration without requesting a new analysis version
- **THEN** the backend returns or references the existing matching queued, running, or succeeded job instead of starting duplicate pipeline work

#### Scenario: Backend is unavailable during real upload submission
- **WHEN** the user submits an analysis request and the backend cannot upload the file or create the job
- **THEN** the system shows a recoverable error state without losing the selected file and metadata context and does not silently create a successful mock job

#### Scenario: Developer submits a metadata-only demo request
- **WHEN** a developer or explicit sample mode creates an analysis job without a backend video identifier
- **THEN** the backend may return a demo-compatible job response that is distinguishable from a real uploaded-video analysis

### Requirement: Analysis job status page
The system SHALL provide a job-specific page that communicates orchestration-aware analysis progress, MVP pipeline stage telemetry, model-backed detection and pose stages, cancellation state, and next actions within the task-centered workflow. The page SHALL present the analysis stages as a horizontal capsule stepper with the currently running stage highlighted, instead of a verbose vertical stage list.

#### Scenario: User opens a queued job
- **WHEN** the user navigates to an analysis job that is queued
- **THEN** the system shows a queued status, job metadata, queue timing, a message that processing has not started yet, a cancellation action when allowed, and a way back to task management

#### Scenario: User opens a running job
- **WHEN** the user navigates to an analysis job that is running or displayed as processing
- **THEN** the system shows the current processing stage, a horizontal capsule stage stepper that scrolls horizontally and auto-focuses the active stage, the active stage's detail text (such as processed frame counts) on its own line, an overall percentage as secondary text, cancellation action when allowed, polls for updates, and keeps result actions unavailable until completion

#### Scenario: User views the horizontal stage stepper
- **WHEN** the user views a non-terminal analysis job with multiple reported stages
- **THEN** the system renders the stages as a single horizontally scrollable row of capsules with connector lines, colors completed stages green, the active stage orange with a breathing emphasis, failed stages red, skipped stages gray, and pending stages light gray, and automatically scrolls the active (or failed) stage into the visible area

#### Scenario: User opens a pipeline-backed processing job
- **WHEN** the user navigates to an analysis job currently running the MVP backend pipeline
- **THEN** the system displays stages for upload, calibration, video read, detection, tracking, pose estimation, projection, metrics, visualization, and report generation when those stages are reported by the backend

#### Scenario: User opens a terminal job with collapsed progress
- **WHEN** the user navigates to an analysis job that is completed, failed, or canceled
- **THEN** the progress area collapses to a one-line summary (for example total completed stages and overall duration for completed jobs, or the failing/canceled stage), and result or recovery actions become the primary content of the page

#### Scenario: User opens a failed job
- **WHEN** the user navigates to an analysis job that failed
- **THEN** the system shows the user-facing failure reason and stable error code when available and offers a retry, return-to-upload, or return-to-task-management action

#### Scenario: User opens a canceled job
- **WHEN** the user navigates to an analysis job that was canceled
- **THEN** the system shows a stable canceled state, cancellation timing when available, and actions to start a new upload or return to task management

#### Scenario: User opens a completed job
- **WHEN** the user navigates to an analysis job that completed successfully
- **THEN** the system shows completion status and provides actions to open the visual analysis workspace, analysis details page, and task management page

#### Scenario: User views a multiview parent job
- **WHEN** the user navigates to an analysis job with `analysisKind=multiview` that exposes `viewRuns`
- **THEN** the page shows the A/B per-view progress bars inside the progress area instead of as a separate block, and the per-view progress remains a summary of the two child runs

#### Scenario: Pipeline reports tracking progress
- **WHEN** the backend processes a video with player tracking enabled
- **THEN** the reported pipeline stages include progress details derived from upload state, calibration state, processed frame counts, detection counts, projected track counts, generated person or pose overlay artifacts, stage timestamps, durations, and generated result artifacts when available

#### Scenario: Pipeline reports pose progress
- **WHEN** the backend processes a video with pose inference enabled
- **THEN** the reported pipeline stages include pose-estimation status, processed subject counts, skeleton artifact availability, stage timing, retry or skip context, or a clear skipped/failed reason

### Requirement: Analysis job result routing
The system SHALL route users from completed tasks and completed job details to job-specific visual analysis, analysis details, and currently supported report views.

#### Scenario: User opens completed visual analysis
- **WHEN** the user selects the visual analysis action for a completed job from task management or the job status detail
- **THEN** the system opens a visual analysis route associated with that job identifier

#### Scenario: User opens completed analysis details
- **WHEN** the user selects the analysis details action for a completed job from task management, job status detail, or visual analysis
- **THEN** the system opens `/analysis/:jobId/details` for that job identifier

#### Scenario: User opens supported completed report type
- **WHEN** the user selects a currently supported report action for a completed job
- **THEN** the system opens the matching report detail route associated with that job identifier and report type

### Requirement: Demo fallback for analysis flow
The system SHALL preserve a demo path when no backend job is available.

#### Scenario: User views demo analysis without a job
- **WHEN** the user opens the existing demo visual analysis or sample report route
- **THEN** the system continues to render the structured local demo data without requiring a backend

#### Scenario: Job result cannot be loaded
- **WHEN** a job-specific result route cannot load report data
- **THEN** the system shows a stable error or fallback state rather than rendering a broken visualization

### Requirement: Calibration-assisted analysis flow
The system SHALL support manual or semi-manual court calibration data as part of a video analysis workflow and use available calibration to project tracked player footpoints into court coordinates.

#### Scenario: User submits calibration before analysis
- **WHEN** the user or developer submits court keypoint correspondences for an uploaded video before creating an analysis job
- **THEN** the backend stores the calibration and allows the analysis job to reference it

#### Scenario: Analysis starts without calibration
- **WHEN** an MVP analysis job starts without a calibration reference
- **THEN** the backend still creates the job and returns a mock, empty-tracks, or calibration-pending result instead of crashing

#### Scenario: Analysis starts with video and calibration
- **WHEN** an analysis job starts with a readable uploaded video and a valid calibration homography
- **THEN** the backend runs player detection, tracking, footpoint estimation, court projection, and metrics stages using the calibration-derived court coordinates

### Requirement: Algorithm result retrieval
The system SHALL allow a completed pipeline-backed analysis job to expose its raw algorithm result separately from the frontend report payload, including tracking artifacts when real video tracking was executed.

#### Scenario: Developer requests raw algorithm result
- **WHEN** a developer requests the result for a completed pipeline-backed job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, projected tracks, movement metrics, heatmap data, tracking metadata, and output artifact paths where available

#### Scenario: Result is not ready
- **WHEN** a client requests the raw algorithm result before the job is completed
- **THEN** the backend returns the current job status or a clear not-ready response without pretending the result is final

#### Scenario: Tracking artifact is available
- **WHEN** a completed job processed video frames with a valid calibration
- **THEN** the raw algorithm result includes or references a persisted `tracking_result.json` artifact containing frame timing metadata and player positions

### Requirement: User-facing calibration handoff
The system SHALL provide a lightweight calibration handoff for real uploaded video analysis so player positions can be projected into court coordinates.

#### Scenario: User marks four court corners
- **WHEN** the selected video is ready for real analysis and the user marks top-left, top-right, bottom-right, and bottom-left court corners on a representative frame
- **THEN** the frontend submits those image points with the backend video identifier and stores the returned calibration identifier for job creation

#### Scenario: Calibration cannot be created
- **WHEN** the calibration request is rejected or cannot compute a valid homography
- **THEN** the system keeps the user in the upload/calibration workflow with a clear error and does not start a full real analysis job

#### Scenario: User skips calibration
- **WHEN** the user chooses to start without calibration if that option is available
- **THEN** the resulting job is labeled as limited analysis and MUST NOT present court-projected movement metrics as if calibration was available

### Requirement: Raw pipeline result consumption
The system SHALL make completed real analysis jobs expose raw MVP pipeline results that the frontend can use to generate user-facing movement, status, and standard-court feedback.

#### Scenario: Frontend requests a completed pipeline result
- **WHEN** the frontend requests the raw result for a completed real analysis job
- **THEN** the backend returns structured JSON containing video reference, calibration reference, stage results, projected tracks, movement metrics, heatmap data, person/pose artifact paths, and a completion message where available

#### Scenario: Frontend requests a result before completion
- **WHEN** the frontend requests raw algorithm output for a queued or processing job
- **THEN** the backend returns the current job status or a clear not-ready response without pretending final algorithm output exists

#### Scenario: Pipeline result is unavailable for a completed job
- **WHEN** a completed job has no raw algorithm result due to storage or processing failure
- **THEN** the frontend shows a stable unavailable-result state or demo/sample distinction instead of broken report modules

### Requirement: True-model pose artifact reporting
The system SHALL distinguish true RTMPose model output from unavailable, skipped, injected-test, or placeholder pose states in completed real analysis results.

#### Scenario: True RTMPose pose artifact is available
- **WHEN** a completed calibrated real analysis job runs with RTMPose inference enabled, supported model assets configured, and at least one frame producing valid skeleton keypoints
- **THEN** the raw pipeline result includes a done pose stage, `pose_overlay_status` of `available`, a retrievable `pose_overlay_url`, and detail text derived from generated subject/keypoint counts

#### Scenario: RTMPose runtime or assets are unavailable
- **WHEN** a completed real analysis job cannot run RTMPose because dependencies, config, checkpoint, or device setup is unavailable
- **THEN** the raw pipeline result exposes a skipped or unavailable pose stage with a clear diagnostic and omits any available pose overlay URL

#### Scenario: Detection exists without usable pose
- **WHEN** a completed real analysis job produces player boxes but RTMPose returns no usable skeleton keypoints
- **THEN** the raw pipeline result keeps tracking artifacts available and labels the pose overlay as no-pose or unavailable without failing the entire analysis

### Requirement: Video and overlay artifact retrieval
The system SHALL allow completed real jobs to expose browser-loadable source video and overlay artifact references for visual playback.

#### Scenario: Source video is available
- **WHEN** a completed real job references an uploaded `videoId`
- **THEN** the backend exposes a browser-loadable source video URL or stream endpoint for that video

#### Scenario: Overlay artifacts are available
- **WHEN** a completed real job produced detection, tracking, or pose overlay artifacts
- **THEN** the raw pipeline result references those artifacts with browser-loadable URLs or API paths

#### Scenario: Overlay artifacts are unavailable
- **WHEN** model inference was disabled, failed, or produced no supported overlay artifacts
- **THEN** the job result distinguishes no-overlay availability from demo data and keeps report navigation stable

### Requirement: Pose-aware raw pipeline result
The system SHALL include pose overlay availability in completed real analysis results.

#### Scenario: Pose artifact exists
- **WHEN** the frontend requests raw output for a completed job with RTMPose results
- **THEN** the result includes pose artifact metadata, stage status, and enough source video metadata to align keypoints to the video frame

#### Scenario: Detection exists without pose
- **WHEN** a completed job has YOLO detections but no RTMPose skeletons
- **THEN** the result allows the frontend to render person boxes and label skeleton overlay as unavailable

### Requirement: Automatic calibration suggestion handoff
The system SHALL allow the video upload calibration step to request and review an automatic court calibration suggestion before creating a real analysis job.

#### Scenario: User requests automatic calibration after upload
- **WHEN** the user has uploaded a readable video and selects automatic court calibration
- **THEN** the frontend requests an automatic calibration suggestion for the uploaded video and presents the returned status, confidence, keypoints, and preview when available

#### Scenario: User accepts automatic calibration
- **WHEN** an automatic calibration suggestion passes backend validation and the user accepts it
- **THEN** the frontend stores the returned calibration identifier and creates the real analysis job with that calibration identifier

#### Scenario: User corrects automatic keypoints
- **WHEN** an automatic calibration suggestion is visible but one or more points need adjustment
- **THEN** the frontend lets the user submit corrected keypoints through the calibration handoff before creating the real analysis job

#### Scenario: Automatic calibration is unavailable or rejected
- **WHEN** the automatic calibration request fails, the model is unavailable, or the backend rejects the detected geometry
- **THEN** the workflow keeps manual calibration and limited-analysis fallback choices available without losing the uploaded video or match metadata

### Requirement: Structured analysis error diagnostics
The system SHALL preserve and display structured backend error diagnostics for real video upload, calibration, job creation, job status, and result retrieval failures.

#### Scenario: Backend returns an error payload
- **WHEN** a frontend analysis API request receives a non-success response with backend detail
- **THEN** the frontend error state includes the operation context, request path, HTTP status, and backend detail when available

#### Scenario: Backend cannot be reached
- **WHEN** a frontend analysis API request fails before receiving an HTTP response
- **THEN** the frontend error state identifies the operation that failed and communicates that the backend connection or network request failed

#### Scenario: User sees a failed analysis job
- **WHEN** the user opens a job whose status is `failed`
- **THEN** the job status page shows the failed stage, stored failure message, and any available stage detail instead of only a generic failure sentence

### Requirement: Stage-based real analysis progress
The system SHALL persist and display real intermediate progress for pipeline-backed analysis jobs using backend-reported stage state.

#### Scenario: Pipeline job starts processing
- **WHEN** a queued real analysis job begins backend processing
- **THEN** the backend updates the job to `processing` with the active stage and progress derived from the ordered analysis stages

#### Scenario: Pipeline advances between stages
- **WHEN** the backend completes or skips a meaningful pipeline stage
- **THEN** the backend persists updated stages, current active stage, updated timestamp, and a monotonic progress percentage before the final result is available

#### Scenario: Frontend polls a running job
- **WHEN** the job status page polls a processing job
- **THEN** it renders the current stage label, progress percentage, and stage list from the latest backend job summary

#### Scenario: Pipeline fails during an intermediate stage
- **WHEN** a real analysis job fails before report generation
- **THEN** the backend records the first failed stage and the frontend displays that stage as failed with the diagnostic detail

### Requirement: Analysis job cancellation flow
The system SHALL allow users to request cancellation for queued or running real analysis jobs from job-aware status surfaces.

#### Scenario: User cancels a queued job
- **WHEN** the user requests cancellation for a queued analysis job
- **THEN** the backend accepts the cancellation, marks the job as canceled without running the pipeline, and the frontend updates the job status

#### Scenario: User cancels a running job
- **WHEN** the user requests cancellation for a running analysis job
- **THEN** the backend records the cancellation request and the frontend shows cancellation pending or canceled status based on the latest job telemetry

#### Scenario: User cannot cancel terminal job
- **WHEN** the user attempts to cancel a succeeded, failed, or already canceled job
- **THEN** the system prevents or rejects the action without deleting artifacts or altering terminal results

### Requirement: Court-view/ROI 阶段记录
真实视频分析 pipeline SHALL 在任务阶段记录中暴露 court-view gate 与 detection ROI 的执行状态和摘要。

#### Scenario: Court-view/ROI 阶段完成
- **WHEN** 完成的真实已标定视频分析任务运行了 court-view gate 或 detection ROI
- **THEN** pipeline stages SHALL 包含 court-view/ROI 阶段状态、处理帧计数、候选片段数量、ROI 状态、跳过帧数量和过滤检测数量

#### Scenario: Court-view/ROI 阶段降级
- **WHEN** court-view gate 缺少参考帧或 ROI 缺少标定角点但基础 tracking 仍可运行
- **THEN** pipeline stages SHALL 将对应部分标记为 `skipped`、`partial` 或 `unavailable`，并保持 detection、tracking、pose、projection 和 metrics 阶段按可用输入继续执行

#### Scenario: Court-view/ROI 阶段失败
- **WHEN** court-view/ROI 处理发生可恢复错误
- **THEN** pipeline SHALL 记录失败或 unavailable 诊断，并不得因为该辅助门控失败而伪造成功的 court-view segment

### Requirement: Court-view/ROI artifact 引用
完成的 pipeline raw result SHALL 在 artifacts 中提供 court-view/ROI artifact 的可选引用、状态和说明。

#### Scenario: Artifact 可用
- **WHEN** court-view/ROI artifact 已写入 storage
- **THEN** raw pipeline result artifacts SHALL 包含浏览器可加载的 artifact URL、文件路径、状态和 detail

#### Scenario: Artifact 不可用
- **WHEN** court-view/ROI artifact 因缺少前置条件未生成
- **THEN** raw pipeline result SHALL 暴露不可用状态和原因，而不是要求前端猜测该能力是否运行

#### Scenario: 旧客户端忽略新字段
- **WHEN** 客户端尚未渲染 court-view/ROI artifact
- **THEN** tracking overlay、pose overlay、source video、movement metrics 和现有 job navigation SHALL 继续保持兼容

### Requirement: Court-view 候选不改变报告语义边界
视频分析 job flow SHALL 将 court-view candidates 作为输入质量和导航辅助，而不是完整比赛事件输出。

#### Scenario: 报告需要 rally 语义
- **WHEN** report 或 analysis details 需要完整 rally segmentation、得分、失误、球落点或战术判断
- **THEN** 系统 SHALL 继续标记这些语义为 unavailable，除非未来专门能力提供相应证据

#### Scenario: Serve-start 消费 court-view candidates
- **WHEN** serve-start detector 使用 court-view candidates 作为辅助上下文
- **THEN** 发球 artifact SHALL 仍以发球候选点形式输出，并记录 court-view 只是辅助信号

### Requirement: 创建分析任务携带源 FPS
系统 SHALL 在上传视频和录制视频创建分析任务时携带用户确认的源视频 FPS。

#### Scenario: 上传视频分析任务包含 FPS
- **WHEN** 用户上传本地视频并提交真实分析任务
- **THEN** 创建分析任务请求 MUST 包含用户确认的源视频 FPS
- **AND** 后端 MUST 将该 FPS 保存到任务 metadata 或 pipeline options

#### Scenario: 已有 videoId 的录制视频可提交
- **WHEN** 用户从录制完成页进入创建分析任务页面且 URL 包含 `videoId`
- **THEN** 页面 SHALL 允许在没有本地 `selectedFile` 的情况下提交分析任务
- **AND** 任务 MUST 使用该 `videoId`、标定结果和用户确认 FPS 创建

#### Scenario: 任务页面展示 FPS 输入状态
- **WHEN** 创建分析任务页面已从视频 metadata 或录制 session 获得 FPS
- **THEN** 页面 SHALL 展示该 FPS 作为默认值
- **AND** 用户修改后提交的值 MUST 覆盖默认值

### Requirement: Per-job inference toggles in job creation
The system SHALL allow users to choose, when creating an analysis job from the upload flow, whether to enable human detection (YOLO) and pose estimation (RTMPose) model inference for that job, defaulting to enabled.

#### Scenario: Upload page exposes inference toggles
- **WHEN** the user completes video upload and court calibration on the new-analysis page and is about to submit the job
- **THEN** the form SHALL show two independent toggles labeled for human detection (YOLO) and pose estimation (RTMPose), both defaulting to enabled

#### Scenario: Toggles are sent with the job request
- **WHEN** the user submits the analysis job
- **THEN** the job creation request SHALL include `enableModelInference` and `enablePoseInference` reflecting the toggle states

#### Scenario: Toggles default to enabled
- **WHEN** the user does not touch the toggles
- **THEN** both `enableModelInference` and `enablePoseInference` SHALL be submitted as enabled

#### Scenario: Toggle hint without calibration
- **WHEN** the current flow has no valid court calibration (limited or demo mode)
- **THEN** the inference toggles SHALL remain visible with a hint that they take effect only after court calibration

