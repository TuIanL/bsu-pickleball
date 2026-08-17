# visual-analysis-workspace Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
### Requirement: Video-first analysis workspace
The system SHALL provide a dedicated visual analysis page centered on a job-aware pickleball video player, with completed job routes using a clean video-and-status layout and demo routes preserving simulated visuals.

#### Scenario: User opens the visual analysis demo page
- **WHEN** the user navigates to `/vision` without a job context
- **THEN** the system may render the local demo analysis experience with a large video-style analysis card, sample context, and clear demo/source indication

#### Scenario: User views the simulated video layer
- **WHEN** the video analysis card is visible without a real job context
- **THEN** the system shows a pickleball court mockup with court lines, kitchen zones, player markers or boxes, shot trajectories, landing or heat indicators, and AI labels

#### Scenario: User views a completed real-job video layer
- **WHEN** the video analysis card is visible for a completed uploaded-video job with a source video URL
- **THEN** the system plays the uploaded source video in the primary visual area and places job status, overlay status, and report navigation in the adjacent status rail rather than surrounding the video with full report dashboards

### Requirement: AI overlay labels
The system SHALL display contextual AI labels over the simulated video to explain important shot patterns and risks.

#### Scenario: User views active rally overlays
- **WHEN** an active rally is displayed in the visual analysis workspace
- **THEN** the system shows labels such as third-shot drop, high-risk drive, kitchen error, winning pattern, or equivalent original copy tied to mock rally events

### Requirement: Highlights and coach notes
The system SHALL keep highlights and coach-like insights available as lower-level analysis content without cluttering the primary completed-result video viewport.

#### Scenario: User opens completed visual analysis
- **WHEN** a completed job-specific visual analysis page is visible
- **THEN** the primary viewport area focuses on the video and status rail instead of rendering full coach-note and highlight cards around the video

#### Scenario: User reviews coach notes or highlights
- **WHEN** the user opens a lower-level report tab, report detail page, or equivalent secondary result view
- **THEN** the system displays readable highlights or AI coach notes covering strengths, risks, major errors, and training recommendations with distinct status treatments

### Requirement: Rally timeline and shot filtering
The system SHALL keep video timeline review close to the video player while moving detailed shot exploration into lower-level analysis views.

#### Scenario: User reviews timeline markers
- **WHEN** timeline markers are available for the current video result or demo
- **THEN** the player exposes concise marker labels or tooltips without forcing full shot-explorer content into the primary completed-result viewport

#### Scenario: User selects a shot filter chip
- **WHEN** the user opens a lower-level shot exploration or rally report view and clicks a shot filter such as All, Serve, Return, Third Shot, Dink, Drive, Reset, Volley, Smash, or Error
- **THEN** the selected chip visibly changes state and the displayed shot list or shot summary reflects that local selection

### Requirement: Video workspace report actions
The system SHALL present compact lower-level result actions from the visual analysis workspace without exposing removed landing or ball-capture analysis as current real-job reports.

#### Scenario: User views report actions
- **WHEN** the user reviews a completed job-specific video analysis workspace
- **THEN** the status rail or adjacent secondary navigation shows actions for analysis details and currently supported movement or diagnosis views rather than a landing report action

#### Scenario: User selects a result action
- **WHEN** the user clicks analysis details from a completed job-specific result
- **THEN** the system navigates to `/analysis/:jobId/details`

#### Scenario: User selects a supported report action
- **WHEN** the user clicks a currently supported report action from a completed job-specific result
- **THEN** the system navigates to the matching job-specific `/analysis/:jobId/reports/:type` report detail page or equivalent lower-level tab state

### Requirement: Premium sports-tech visual style
The system SHALL make the visual analysis workspace feel like a mature AI sports video analytics product with a bright sports-tech theme.

#### Scenario: User views the visual analysis page
- **WHEN** the visual analysis page renders
- **THEN** the system uses bright primary surfaces, restrained green highlights, preserved blue/orange/red status accents, clean cards, subtle borders, hover states, and video-first hierarchy rather than a heavy dark interface or a generic admin-table layout

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

The system SHALL visualize available player movement and court coverage data from backend pipeline results in the visual analysis workspace, including synchronized movement paths and current-position summaries in the video analysis HUD when projected tracks are available.

#### Scenario: Projected tracks are available

- **WHEN** a completed real analysis job includes projected player tracks
- **THEN** the workspace renders movement paths, current player positions, direction indicators, or heat distribution from those tracks rather than static demo coordinates
- **AND** the video HUD identifies stable player labels and uses a time window tied to the current video playback time

#### Scenario: Movement metrics are available

- **WHEN** a completed real analysis job includes distance, speed, kitchen dwell, doubles spacing, or heatmap metrics
- **THEN** the workspace presents movement-focused feedback derived from those metrics with readable labels and values
- **AND** the HUD MAY show a compact current-position or speed summary without replacing the detailed report metrics

#### Scenario: Movement track has a data gap

- **WHEN** a projected player track contains a timestamp gap beyond the safe interpolation/connection threshold
- **THEN** the workspace breaks the displayed movement path at the gap and communicates the missing or degraded coverage instead of drawing a misleading connecting line

#### Scenario: No detections are produced

- **WHEN** the backend pipeline completes but produces no usable player detections or projected positions
- **THEN** the workspace shows an analysis-completed-but-no-tracks state with guidance to check camera angle, calibration, model setup, or video quality
- **AND** the workspace does not render simulated player positions in the real-job HUD

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

### Requirement: Fullscreen real-video overlay playback

The visual analysis workspace SHALL provide fullscreen playback for real uploaded-video jobs without losing visible person boxes, skeleton joints, independently controlled HUD layers, or overlay status labels.

#### Scenario: User enters fullscreen real-video playback

- **WHEN** a user opens fullscreen playback from a completed real-job video that has detection, pose, player-track, ball, or bounce data
- **THEN** the fullscreen surface includes the source video, enabled overlay layers, the synchronized court HUD when data is available, layer toggles, and playback status labels in the same aligned visual area

#### Scenario: Fullscreen preserves HUD geometry

- **WHEN** the user enters or exits fullscreen while a court HUD is visible
- **THEN** the HUD preserves the standard court aspect ratio, remains within the video content area, and does not overlap the primary playback controls

#### Scenario: Fullscreen is unavailable

- **WHEN** the browser does not support fullscreen for the video overlay container
- **THEN** the workspace keeps inline playback usable and does not hide or break existing overlays or HUD status

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

### Requirement: Right-side analysis status rail
The visual analysis workspace SHALL provide a vertical status rail beside the primary video area for completed job results.

#### Scenario: User opens a completed result on desktop
- **WHEN** a completed job-specific visual analysis page renders on a desktop viewport
- **THEN** the page shows the video viewport as the primary content and a right-side rail with task status, match metadata, overlay availability, and report tab actions

#### Scenario: User opens a completed result on a narrow viewport
- **WHEN** a completed job-specific visual analysis page renders on a narrow viewport
- **THEN** the status rail stacks below or near the video without overlapping the video controls or report actions

#### Scenario: Overlay data is partially available
- **WHEN** a completed job has only some overlay artifacts available
- **THEN** the status rail labels available, unavailable, skipped, or failed video layers without presenting unavailable model output as real analysis

### Requirement: 真实视频发球开始 marker

真实视频分析工作台 SHALL 在完成任务的播放器下方显示独立的发球候选回合导航条，并支持用户快速跳转复盘；播放器进度条 SHALL 保留为播放控制，不再作为密集发球候选的主要浏览入口。

#### Scenario: 发球事件导航条可用
- **WHEN** 用户打开完成的真实视频分析工作台且发球事件 artifact 已加载并包含候选事件
- **THEN** 播放器下方 SHALL 渲染与视频播放器宽度对齐的横向导航条，每个候选事件显示为可点击矩形卡片，并展示候选序号、时间、置信度、检测模式和简短依据

#### Scenario: 用户点击发球候选卡片
- **WHEN** 用户点击发球候选导航条中的矩形卡片
- **THEN** 播放器 SHALL 跳转到该候选的 `seek_time_seconds`，使用户能看到发球前准备和击球附近画面

#### Scenario: 候选数量较多
- **WHEN** 发球候选数量超过播放器宽度能够舒适展示的数量
- **THEN** 导航条 SHALL 在固定宽度容器内支持横向平滑滚动，而不得把所有候选铺成超出页面的静态长横排

#### Scenario: 当前播放时间命中候选片段
- **WHEN** 当前视频时间处于某个候选的 `start_time_seconds` 到 `end_time_seconds` 范围内，或接近该候选 `timestamp_seconds`
- **THEN** 导航条 SHALL 以可见样式高亮对应候选卡片，且不得改变视频播放状态

#### Scenario: marker 超出视频时长保护
- **WHEN** 发球事件 artifact 中的候选时间接近视频起点或终点
- **THEN** 工作台 SHALL 将候选卡片的跳转时间限制在有效视频时长内，避免播放器跳转到无效时间

#### Scenario: 候选展示信号摘要
- **WHEN** 发球候选事件包含 signal scores、候选片段时间窗或覆盖诊断
- **THEN** 候选卡片、tooltip、状态区域或相邻详情 SHALL 能展示底线站位、发球前静止、手臂或 ROI 峰值、后续回合激活、覆盖不足等摘要，而不阻塞播放器操作

### Requirement: 发球事件加载和降级状态

真实视频分析工作台 SHALL 将发球事件 artifact 作为独立数据层加载，使缺失、加载中、降级或失败状态不影响基础视频播放。

#### Scenario: 发球事件正在加载
- **WHEN** 完成任务的 source video 已可播放但发球事件 artifact 仍在加载
- **THEN** 工作台 SHALL 保持视频和已有 overlay 可用，并在控制区或状态区域显示发球 marker 加载状态

#### Scenario: 发球事件不可用
- **WHEN** 发球事件 artifact 状态为 `unavailable`、`no_candidates` 或 `partial`
- **THEN** 工作台 SHALL 显示对应状态说明，并不得用 demo timeline marker 或模拟发球点填充真实视频进度条

#### Scenario: 发球事件请求失败
- **WHEN** 发球事件 artifact 请求失败
- **THEN** 工作台 SHALL 仅标记发球 marker 层失败，并继续允许用户播放、暂停、拖动进度条和查看已加载 overlay

#### Scenario: 发球事件使用降级检测模式
- **WHEN** 发球事件 artifact 或候选事件声明检测模式为无 pose、ROI 差分或其他 partial 模式
- **THEN** 工作台 SHALL 以候选语义展示 marker，并在可用状态说明中表达检测信号受限

### Requirement: 发球候选导航条加载和降级状态

真实视频分析工作台 SHALL 将发球候选导航条作为独立数据层加载，使缺失、加载中、降级或失败状态不影响基础视频播放。

#### Scenario: 发球事件正在加载
- **WHEN** 完成任务的 source video 已可播放但发球事件 artifact 仍在加载
- **THEN** 工作台 SHALL 保持视频和已有 overlay 可用，并在播放器下方导航区域显示发球候选加载状态

#### Scenario: 发球事件不可用
- **WHEN** 发球事件 artifact 状态为 `unavailable` 或 `no_candidates`
- **THEN** 导航条区域 SHALL 显示对应状态说明，并不得用 demo timeline marker 或模拟发球点填充真实视频

#### Scenario: 发球事件部分可用
- **WHEN** 发球事件 artifact 状态为 `partial` 或候选声明降级检测模式
- **THEN** 导航条 SHALL 仍显示可用候选，并以候选语义表达检测信号受限

#### Scenario: 发球事件请求失败
- **WHEN** 发球事件 artifact 请求失败
- **THEN** 工作台 SHALL 仅标记发球候选导航层失败，并继续允许用户播放、暂停、拖动进度条和查看已加载 overlay

### Requirement: 发球 marker 来源清晰

真实视频分析工作台 SHALL 清楚区分发球时刻候选 marker、demo timeline marker 和未来可能的完整回合边界。

#### Scenario: 用户查看真实任务 marker
- **WHEN** 用户在真实视频播放器上看到发球时刻 marker
- **THEN** UI SHALL 使用“发球候选”“发球时刻候选”或等效文案表达不确定性，并避免称其为完整回合切分结果

#### Scenario: 用户查看 demo marker
- **WHEN** 用户打开没有真实 job context 的 demo 视觉分析页
- **THEN** 系统 SHALL 保持现有 demo timeline 行为，不得把 demo marker 表示为后端发球检测结果

#### Scenario: 调试 artifact 可用
- **WHEN** 真实任务包含发球候选调试 artifact 引用
- **THEN** 工作台 SHALL 可提供非阻塞入口或状态说明，使用户理解 marker 来自后端上下文检测而不是 demo 数据

### Requirement: Real ball layer playback
The visual analysis workspace SHALL load and render real ball trajectory, ball overlay, and bounce candidate layers for completed uploaded-video jobs when the corresponding artifacts are available.

#### Scenario: Ball trajectory artifact is available
- **WHEN** a completed real job references a valid ball trajectory or cleaned ball trajectory artifact
- **THEN** the workspace SHALL fetch the artifact independently from the source video shell
- **AND** the workspace SHALL render a synchronized ball path or current ball marker using uploaded-video coordinates

#### Scenario: Bounce candidates are available
- **WHEN** a completed real job references `bounce_events.json` with candidate events
- **THEN** the workspace SHALL render timeline markers or court/video markers as candidate bounce events
- **AND** the workspace MUST NOT label them as confirmed scoring, landing, fault, or tactical outcomes

#### Scenario: Ball layer is unavailable
- **WHEN** a completed real job has no ball artifact because configuration is disabled, dependencies are missing, detection found no candidates, or the stage failed
- **THEN** the workspace SHALL show a layer state matching skipped, unavailable, no-detection, partial, or failed
- **AND** the workspace MUST NOT render demo ball paths as real job output

### Requirement: Ball layer controls preserve existing overlays
The visual analysis workspace SHALL allow ball-related layers to coexist with source video, person boxes, skeleton overlays, serve markers, and status rail actions.

#### Scenario: User toggles ball layer
- **WHEN** ball trajectory or ball overlay data is available and the user toggles the ball layer
- **THEN** the workspace hides or shows the ball layer without changing video playback, person boxes, skeleton state, or loaded artifact status

#### Scenario: Ball artifact request fails
- **WHEN** the ball layer artifact request fails after the completed job shell has loaded
- **THEN** the workspace marks only the ball layer as failed
- **AND** source video, person boxes, skeleton overlay, report navigation, and status rail remain usable

### Requirement: 完成态视频视图不显示开发向状态卡片与占位比分

真实视频分析工作台的完成态视频卡片 SHALL NOT 在视频下方渲染面向用户的 artifact 可用性卡片（YOLO 人体框、RTMPose 骨架、球轨迹、弹跳候选四张卡片及其 status/detail 文案）。视频标题右侧的比分胶囊 SHALL 仅在存在真实比分时显示，SHALL NOT 显示 "MVP" 之类的占位符。图层可用性状态 SHALL 仍通过视频内状态徽章与图层开关呈现。

#### Scenario: 完成态真实任务不显示四张卡片

- **WHEN** 用户打开完成态真实分析任务的视频工作台
- **THEN** 视频下方不显示 YOLO 人体框 / RTMPose 骨架 / 球轨迹 / 弹跳候选 四张信息卡及其 detail 文案

#### Scenario: 标题不显示 MVP 占位比分

- **WHEN** 真实分析任务的 `match.score` 为占位符 "MVP"
- **THEN** 视频标题右侧不渲染该占位比分胶囊

#### Scenario: demo 显示真实比分

- **WHEN** demo 或任务存在真实比分（如 "11 - 8"）
- **THEN** 视频标题右侧渲染该比分胶囊

#### Scenario: 图层状态仍可通过视频内控制查看

- **WHEN** 用户需要查看人体框、骨架、球或弹跳图层的可用性
- **THEN** 通过视频内的状态徽章或图层开关查看，视频播放层不因移除四张卡片而改变

### Requirement: 双摄协同详情快捷入口

视频分析结果页（`/analysis/:id/vision`）头部 SHALL 在任务为双摄协同（`analysisKind === "multiview"`）且分析完成时提供**查看双摄协同详情**按钮，点击直达 `/analysis/:id/multiview`；导航 SHALL 保留任务列表来源上下文。非双摄协同任务或未完成任务 MUST NOT 展示该入口。

#### Scenario: 双摄协同任务直达协同详情

- **WHEN** 用户在视频分析结果页查看一个已完成的双摄协同任务
- **THEN** 页面头部 SHALL 展示"查看双摄协同详情"按钮
- **AND** 点击 SHALL 直接导航到 `/analysis/:id/multiview`，无需先返回任务管理

#### Scenario: 非双摄任务不展示入口

- **WHEN** 视频分析结果页对应任务不是双摄协同（`analysisKind !== "multiview"`）
- **THEN** 页面 MUST NOT 展示"查看双摄协同详情"按钮

#### Scenario: 未完成任务不展示入口

- **WHEN** 双摄协同任务尚未完成
- **THEN** 页面 MUST NOT 展示"查看双摄协同详情"按钮

#### Scenario: 入口保留来源上下文

- **WHEN** 用户从双摄协同详情页点击返回
- **THEN** 返回目标 SHALL 保持在双摄任务管理上下文中
- **AND** 页面 SHALL 保留任务列表来源与 session 上下文参数

