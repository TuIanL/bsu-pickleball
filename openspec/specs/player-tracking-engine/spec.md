# player-tracking-engine Specification

## Purpose
TBD - created by archiving change implement-player-tracking-engine. Update Purpose after archive.
## Requirements
### Requirement: Person detection for fixed-camera frames
The backend SHALL provide a Player Tracking Engine detector that reads decoded video frames, runs an optional Ultralytics YOLO person model, filters detections to `person` class only, applies a configurable confidence threshold, and emits normalized detection records.

#### Scenario: YOLO returns mixed classes
- **WHEN** the detector receives model results containing person and non-person boxes
- **THEN** the detector returns only records with `class_name` equal to `person`, each including `bbox`, `confidence`, and `class_name`

#### Scenario: Detector confidence threshold is configured
- **WHEN** a detection confidence is below the configured threshold
- **THEN** the detector excludes that detection from the normalized output

#### Scenario: Detector is imported without model assets
- **WHEN** backend modules import the detector package before YOLO weights are loaded
- **THEN** the import succeeds without requiring CUDA, downloaded model weights, or an active video file

#### Scenario: Detector selects runtime device
- **WHEN** the detector is initialized without an explicit device
- **THEN** the detector chooses GPU when available and otherwise uses CPU

### Requirement: Multi-object player tracking
The backend SHALL provide a replaceable `MultiObjectTracker` that accepts current-frame person detections and returns track records with stable integer `track_id`, bbox, confidence, and lost-state metadata.

#### Scenario: Detection overlaps an existing track
- **WHEN** a current detection has IOU above the configured association threshold with an active prior track
- **THEN** the tracker reuses that track's `track_id` for the current frame

#### Scenario: Detection has no matching track
- **WHEN** a current detection cannot be associated with an active prior track
- **THEN** the tracker creates a new integer `track_id` for that detection

#### Scenario: Track is temporarily unmatched
- **WHEN** an existing track is not matched in the current frame but has not exceeded the lost-frame limit
- **THEN** the tracker retains its internal state for possible reassociation without emitting it as an active player position

#### Scenario: Tracker implementation is replaced later
- **WHEN** ByteTrack or BoT-SORT is introduced as a future implementation
- **THEN** it can satisfy the same detection-in and track-out interface without changing projection, metrics, or pipeline result schemas

### Requirement: Footpoint estimation

后端 SHALL 提供 `FootpointEstimator`，从每帧跟踪球员框和可选姿态关键点估计图像空间地面接触点。估计 SHALL 采用 hybrid 策略：优先双踝中点、其次单踝、再膝外推，最后 fallback 到 bbox 底边中点；当 bbox 底边接近画面底部时 SHALL 降低基于 bbox 的估计置信度。

#### Scenario: Bbox bottom center is estimated

- **WHEN** 估计器接收 bbox `[x1, y1, x2, y2]` 且无姿态关键点可用
- **AND** bbox y2 不接近画面底部（y2 <= frame_height * 0.94 或无 frame_shape）
- **THEN** 返回 `image_footpoint` 等于 `[(x1 + x2) / 2, y2]`，method 为 `bbox_bottom_center`，confidence 为 0.7

#### Scenario: 双踝关键点可用

- **WHEN** 姿态关键点中左右踝（COCO 15/16）置信度均 >= 0.35
- **THEN** 返回 method 为 `pose_ankle_midpoint`，confidence 为 min(左右踝置信度)
- **AND** image_footpoint 为左右踝坐标均值

#### Scenario: 单踝关键点可用

- **WHEN** 仅一侧踝关键点置信度 >= 0.35
- **THEN** 返回 method 为 `pose_ankle_single`，confidence 为该踝置信度
- **AND** image_footpoint 为该踝坐标

#### Scenario: 膝外推

- **WHEN** 双膝关键点（COCO 13/14）置信度均 >= 0.4 且双踝均不可用
- **THEN** 返回 method 为 `knee_extrapolated`，confidence 为 min(膝置信度) * 0.8
- **AND** image_footpoint 基于膝中点向下外推计算

#### Scenario: near-clip fallback

- **WHEN** 无姿态关键点可用，且 bbox y2 > frame_height * 0.94
- **THEN** 返回 method 为 `bbox_bottom_clipped`，confidence <= 0.35
- **AND** image_footpoint 仍为 `[(x1 + x2) / 2, y2]`

#### Scenario: 正常 bbox fallback

- **WHEN** 无姿态关键点可用，且 bbox y2 <= frame_height * 0.94（或 frame_shape 为 None）
- **THEN** 返回 method 为 `bbox_bottom_center`，confidence 为 0.7
- **AND** image_footpoint 为 `[(x1 + x2) / 2, y2]`

#### Scenario: Future footpoint strategy is selected

- **WHEN** 未来 pose 或 segmentation 策略被引入
- **THEN** 估计器接口可以报告新的 method 值，而无需改变下游投影输出形状

### Requirement: Player footpoint projection
The backend SHALL project tracked image footpoints through a CourtVision image-to-court homography into canonical pickleball court coordinates and emit frame-level player position records.

#### Scenario: Valid footpoint is projected
- **WHEN** a track has bbox, confidence, and a bottom-center image footpoint and a valid homography is available
- **THEN** the projector returns a `PlayerFramePosition` with frame index, timestamp, track id, bbox, image footpoint, court position, and confidence

#### Scenario: Projected point is outside tolerated court bounds
- **WHEN** a projected court coordinate falls outside the configured tolerant bounds around the standard 20 ft by 44 ft court
- **THEN** the projector either excludes the point from valid output or marks it invalid according to its configured filtering mode

#### Scenario: Spectators are detected outside the court
- **WHEN** YOLO detects people whose footpoints project beyond the tolerated court coordinate range
- **THEN** those detections do not contribute to valid player trajectories used by movement metrics

### Requirement: Tracking result serialization
The backend SHALL define JSON-serializable schemas for frame-indexed detections, tracks, per-frame player positions, and complete tracking results with video timing metadata so both metrics and video overlays can consume the same analysis output.

#### Scenario: Tracking result is serialized
- **WHEN** a tracking result contains frame-indexed detections, tracks, positions, frame count, FPS, frame dimensions, and frame stride metadata
- **THEN** the result can be dumped to JSON without custom encoders or non-serializable numeric types

#### Scenario: Double-player or four-player rallies are tracked
- **WHEN** two or four on-court players are detected across frames
- **THEN** the tracking result can represent multiple concurrent `track_id` trajectories in the same frame

#### Scenario: Frontend consumes detection overlays
- **WHEN** a completed real job exposes tracking overlay data
- **THEN** each renderable person box includes `frame_index`, `timestamp_seconds`, `track_id` when available, `bbox`, `confidence`, and source frame dimensions

#### Scenario: Tracking data is used for court projection
- **WHEN** tracked player boxes are projected into court coordinates
- **THEN** the existing player position and movement metric data remain available for downstream metrics

### Requirement: Video tracking execution
The backend SHALL process uploaded video frames for player tracking using configurable frame stride, per-frame timestamps, FPS metadata, and progress logging, with defaults suitable for smooth 60fps overlay presentation.

#### Scenario: Every frame is processed
- **WHEN** `frame_stride` is set to 1
- **THEN** the engine attempts detection, tracking, footpoint estimation, and projection for every decoded frame

#### Scenario: Sparse frame processing is configured
- **WHEN** `frame_stride` is set to 2 or 5
- **THEN** the engine processes only matching frame indices while preserving timestamps derived from the source FPS

#### Scenario: Default 60fps overlay processing is used
- **WHEN** a real job is processed without an explicit overlay frame stride override
- **THEN** the backend uses a default stride that produces substantially smoother overlay samples than 2fps for 60fps source footage

#### Scenario: Processing progress is logged
- **WHEN** a video with known or unknown frame count is processed
- **THEN** the pipeline logs progress at regular intervals without changing tracking output semantics

### Requirement: YOLO-backed detection activation
The backend SHALL run YOLO person detection for real uploaded-video jobs when model inference is explicitly enabled and model assets are available.

#### Scenario: Model inference is enabled
- **WHEN** a real analysis job has a readable video, valid calibration, and model inference enabled
- **THEN** the pipeline uses the YOLO-backed person detector instead of the empty fallback detector

#### Scenario: Model inference is disabled
- **WHEN** model inference is disabled
- **THEN** the pipeline reports that person detection is unavailable or skipped and does not claim that uploaded-video person boxes were detected

#### Scenario: YOLO detects players
- **WHEN** YOLO returns person detections for processed frames
- **THEN** the pipeline persists those detections with frame timing so the frontend can render player boxes over the source video

#### Scenario: YOLO returns no players
- **WHEN** YOLO completes but returns no usable person detections
- **THEN** the pipeline completes with a no-detections state that guides the user to check camera angle, video quality, calibration, or model setup

### Requirement: Detection overlay artifact
The backend SHALL expose a tracking or detection overlay artifact for completed real jobs that processed video frames, and renderable overlay boxes SHALL be limited to court-relevant tracked persons derived from calibrated footpoint projection.

#### Scenario: Tracking artifact is generated
- **WHEN** a real job runs YOLO detection, tracking, and calibrated footpoint projection
- **THEN** the raw pipeline result references a JSON artifact containing frame-indexed boxes and track labels only for tracked persons whose projected footpoints fall within the configured match-relevant court bounds

#### Scenario: Spectator is detected outside match bounds
- **WHEN** YOLO detects a person whose tracked footpoint projects beyond the configured match-relevant court bounds
- **THEN** that person is excluded from renderable detection overlay frames while raw detection and tracking internals may still record model output for diagnostics

#### Scenario: Player steps near court boundary
- **WHEN** a tracked player footpoint projects slightly outside the standard court lines but remains within configured tolerated bounds
- **THEN** the backend keeps that player eligible for renderable overlay boxes

#### Scenario: Artifact path is not browser-safe
- **WHEN** the backend stores overlay artifacts on the local filesystem
- **THEN** the API exposes a browser-loadable artifact URL or endpoint instead of requiring the frontend to read local paths directly

### Requirement: Primary-player overlay subject selection

系统 SHALL 根据 `MatchAnalysisContext.expected_player_count` 选择渲染叠加层球员，而不是使用固定的全局人数上限。

**FROM**: 选择器使用固定的全局配置 `max_subjects=4`，按置信度和 tracklet 质量排序后取前 N 名。

**TO**: 选择器使用 `MatchAnalysisContext.expected_player_count` 作为 `max_subjects`，在单打上下文中引擎 SHALL 只选择最多 2 名球员，双打上下文中选择最多 4 名球员。

系统 SHALL 选择渲染叠加层展示球员时使用赛制感知的目标球员数量，而不是全局固定值。

#### Scenario: High-confidence match players are selected
- **WHEN** 在单打上下文中处理帧或选择窗口，包含高置信度、稳定 tracklet 历史和强目标球场归属的跟踪人员
- **THEN** 后端 SHALL 最多包含 2 名该等 track 到渲染叠加帧中

- **WHEN** 在双打上下文中处理帧或选择窗口
- **THEN** 后端 SHALL 最多包含 4 名该等 track 到渲染叠加帧中

#### Scenario: Low-confidence incidental detections are dropped
- **WHEN** a processed frame or selection window contains tracked people whose detection confidence, track quality, or target-court membership falls below the configured primary-player selection threshold
- **THEN** the backend excludes those tracks from renderable overlay frames while preserving raw detection or tracking diagnostics where available

#### Scenario: Player steps outside court lines
- **WHEN** a tracked player has high confidence, primary-player track quality, and strong target-court membership but their projected footpoint is slightly outside the standard court lines during normal match movement
- **THEN** the backend keeps that track eligible for renderable overlay frames instead of hiding it solely because it is line-out

#### Scenario: Frame contains more tracked people than match participants
- **WHEN** 单打上下文中一帧包含超过 2 名符合条件的跟踪人员
- **THEN** 后端 SHALL 只保留评分最高的 2 名近端/远端目标球场球员
- **AND** 超出的人员 SHALL 被排除在渲染叠加帧之外，仅在诊断中保留

#### Scenario: Neighbor court players are moving
- **WHEN** tracked people from an adjacent court are confidently detected, persist across frames, and show active match movement
- **THEN** the backend excludes them from target-court renderable overlay frames when their target-court membership and group consistency scores identify them as non-target-court candidates

#### Scenario: Person is clearly far from the match scene
- **WHEN** a tracked person is confidently detected but is clearly outside a broad match-scene sanity region or otherwise fails primary-player track quality checks
- **THEN** the backend may exclude that person from renderable overlay frames without treating normal court-line movement as invalid

### Requirement: Multi-target player compatibility
The Player Tracking Engine SHALL remain compatible with existing person-only detections while allowing normalized multi-target player detections to feed the same tracking, projection, and overlay path.

#### Scenario: Person detector remains active
- **WHEN** a real analysis job runs with the existing person detector
- **THEN** the backend continues to generate player tracks, projected positions, detection overlays, and pose inputs using the current person tracking contract

#### Scenario: Multi-target detector emits players
- **WHEN** a configured multi-target detector emits `player` detections for processed frames
- **THEN** those detections can be converted into the Player Tracking Engine input shape without changing projected movement metrics or browser-facing player overlay schemas

#### Scenario: Ball or paddle detections are present
- **WHEN** normalized multi-target output includes `ball` or `paddle` detections alongside player detections
- **THEN** the Player Tracking Engine ignores non-player targets for player projection and movement metrics while preserving them for their dedicated artifacts

### Requirement: Stable player identity handoff
The Player Tracking Engine SHALL expose projected tracker observations in a form that can be consumed by a downstream player identity manager without treating `track_id` as the final player identity.

#### Scenario: Projected observation is created
- **WHEN** a tracked person box is projected into court coordinates
- **THEN** the projected observation includes source `track_id`, bbox, image footpoint, court position, confidence, frame index, and timestamp

#### Scenario: Final identity differs from source track
- **WHEN** downstream identity assignment maps a source `track_id` to a stable `player_id`
- **THEN** overlay and trajectory consumers can display both identifiers without losing source tracker diagnostics

#### Scenario: Tracker is replaced
- **WHEN** the implementation changes from the simple IOU tracker to BoT-SORT, ByteTrack, or another compatible tracker
- **THEN** the projection and identity handoff contract remains stable

### Requirement: Metric projection compatibility
The Player Tracking Engine SHALL provide enough unit metadata or conversion behavior for downstream components to consume court coordinates in meters.

#### Scenario: Projection output is metric
- **WHEN** the projector emits metric court coordinates
- **THEN** downstream identity and trajectory components consume those coordinates directly with unit metadata declaring meters

#### Scenario: Projection output is imperial
- **WHEN** the projector emits coordinates in feet for compatibility with existing court geometry helpers
- **THEN** downstream components receive explicit unit metadata or convert the coordinates to meters before player identity matching

#### Scenario: Court dimensions are serialized
- **WHEN** tracking or trajectory artifacts include court coordinate metadata
- **THEN** they include canonical metric dimensions and imperial reference dimensions

### Requirement: Participant-limited overlay labels

系统 SHALL 根据比赛上下文限制叠加层身份标签的参与者数量，并保留稳定的球员身份标识。

**FROM**: 叠加层标签限制基于固定全局配置值判定参与者数量。

**TO**: 叠加层标签的参与者上限由 `MatchAnalysisContext` 驱动。单打最多 2 个身份，双打最多 4 个身份。

系统 SHALL 支持叠加层标签包含稳定的球员身份标识，同时根据赛制限制可用身份数量。

#### Scenario: Player identity is available for frame detection
- **WHEN** 单打分析中叠加帧在球员身份分配后生成
- **THEN** 每帧最多 2 个符合条件的球员框包含 `P<player_id> / T<track_id>` 标签
- **AND** 标签应使用 `Player_1` 和 `Player_2`，不应出现 `Player_3` 或 `Player_4`

- **WHEN** 双打分析中叠加帧在球员身份分配后生成
- **THEN** 每帧最多 4 个符合条件的球员框包含身份标签

#### Scenario: More eligible tracks than match participants
- **WHEN** 单打上下文中一帧包含超过 2 名符合条件的跟踪人员
- **THEN** 后端 SHALL 将球员身份叠加层主题限制为 2 名
- **AND** 被排除的 track SHALL 仅在诊断中保留

### Requirement: Court-view gated player tracking
Player Tracking Engine SHALL 支持 court-view gate 对真实视频帧的检测、跟踪和姿态输入进行保守门控，同时保留与普通无检测帧不同的诊断。

#### Scenario: 非球场视角帧跳过检测
- **WHEN** court-view gate 明确判定当前处理帧不是目标球场视角且门控跳过已启用
- **THEN** Player Tracking Engine SHALL 跳过该帧的 person detection 和 pose estimation，并记录 gated frame 诊断

#### Scenario: Court-view gate 不可用
- **WHEN** court-view gate 状态为 `unavailable`、`skipped` 或诊断-only
- **THEN** Player Tracking Engine SHALL 使用现有检测、跟踪、投影路径继续处理可用帧

#### Scenario: Gated frame 不伪装成无检测
- **WHEN** 一帧因 court-view gate 被跳过
- **THEN** tracking diagnostics SHALL 区分 `gated_non_court_view` 与模型运行后 `no_detections`，以便任务详情和测试能解释轨迹缺口

### Requirement: ROI-aware person detection
Player Tracking Engine SHALL 在 detection ROI 可用时限制 person detection 输入或过滤 detection 输出，以减少目标球场外人物干扰。

#### Scenario: ROI 裁剪检测输入
- **WHEN** detection ROI 可用且实现选择在 ROI 上运行模型
- **THEN** detector SHALL 将 ROI 内检测框转换回源帧坐标后再交给 tracker、projector、pose estimator 和 overlay artifact

#### Scenario: ROI 过滤检测输出
- **WHEN** detection ROI 可用且实现选择全帧推理后过滤
- **THEN** Player Tracking Engine SHALL 排除 ROI 外 person detections 进入 match-relevant tracking 路径，并记录过滤数量

#### Scenario: ROI 不可用时全帧回退
- **WHEN** detection ROI 不可用或被配置禁用
- **THEN** Player Tracking Engine SHALL 回退到现有全帧检测行为，并在诊断中记录 full-frame fallback

### Requirement: ROI 与投影坐标一致
ROI-aware detection SHALL preserve source-frame coordinate semantics for tracking, projection, pose overlay, and frontend rendering.

#### Scenario: 投影使用源帧脚点
- **WHEN** ROI-aware detection 产生 player bbox 并估计 footpoint
- **THEN** footpoint projection SHALL 使用源视频坐标系下的 footpoint，而不是 ROI-local 坐标

#### Scenario: Pose overlay 使用源帧尺寸
- **WHEN** pose estimator 消费 ROI-aware detection subjects
- **THEN** pose overlay artifact SHALL 继续声明源视频 frame width/height，并输出可与 source video 对齐的 keypoints

#### Scenario: ROI 过滤不删除原始诊断
- **WHEN** ROI 过滤排除了检测框
- **THEN** 系统 SHALL 在 tracking 或 court-view/ROI artifact 中保留被过滤计数和原因，以便调试邻场或观众误检

### Requirement: 投影观测点 schema 边界语义

后端 SHALL 根据赛制上下文区分严格标定控制点和可容忍的球员脚点投影观测点，并在指标输入前处理标准球场边界。

**FROM**: 运动指标始终假设存在 4 名球员轨迹。

**TO**: 运动指标接收赛制上下文，根据 expected_player_count 和球场投影坐标映射球员轨迹。单打场景 SHALL 只产生 2 组轨迹，双打场景产生 4 组。

后端 SHALL 使用不同的数据模型表达严格标定控制点和球员脚点投影观测点。标定控制点 MUST 保持标准 20 ft x 44 ft 球场内边界校验；球员脚点投影观测点 MUST 能表达有限数值的真实投影坐标，包括配置容差内的边界外坐标；运动指标和标准球场可视化输入 MUST 只使用经过标准球场边界处理的点。

#### Scenario: 容差内越界投影点可序列化
- **WHEN** 一个已跟踪球员脚点投影到 `x` 位于标准宽度附近且 `y` 等于 `44.2195 ft`
- **THEN** 后端可以将该点作为投影观测记录序列化，而不会因为标准球场 `y <= 44 ft` 的严格校验使分析阶段失败

#### Scenario: 标定控制点保持严格边界
- **WHEN** 手动或半自动标定提交的球场控制点坐标超出 `x 0..20 ft` 或 `y 0..44 ft`
- **THEN** 后端继续拒绝该标定输入并返回校验错误

#### Scenario: 运动指标排除标准边界外观测
- **WHEN** 投影观测记录包含标准球场边界外坐标
- **THEN** 距离、速度、厨房区、双打间距和热力图计算不会把该越界观测作为标准球场内轨迹点消费

#### Scenario: 原始投影观测保留诊断价值
- **WHEN** 分析结果包含处于跟踪容差内但标准球场边界外的投影观测
- **THEN** tracking 或 player trajectory artifact 保留该观测的原始坐标，以便排查标定误差、脚点估计抖动或边界动作

#### Scenario: 单打场景轨迹
- **WHEN** 分析任务是单打
- **THEN** 球员轨迹 JSON SHALL 最多包含 2 名不同球员的轨迹
- **AND** 轨迹 artifact SHALL 包含 `match_context` 声明格式和期望人数

### Requirement: 空间门控三层区域

系统 SHALL 基于已有 `PickleballCourtGeometry.court_bounds` 和 `PickleballCourtGeometry.tracking_bounds`，叠加自定义外扩，构建三层空间门控。

```python
所有值单位为英尺
inside_court:
  x: [0, 20], y: [0, 44]           # court_bounds（已有）

near_court_area（新增）：
  x: [-court_margin_x, 20+court_margin_x]
  y: [-court_margin_y, 44+court_margin_y]
  默认 court_margin_x=12, court_margin_y=12

tracking_area：
  x: [-4, 24], y: [-8, 52]         # tracking_bounds（已有）
```

#### Scenario: 候选按空间区域门控

- **WHEN** 新检测候选进入球员跟踪流程
- **THEN** 系统 SHALL 使用 `near_court_area` 判断是否允许初始化，并使用 `tracking_area` 判断已锁定轨迹是否继续跟踪
- **AND** 位于 `tracking_area` 外的候选 MUST 被拒绝并记录门控原因

#### Scenario: 新候选只能在 near_court_area 内初始化

- **WHEN** 候选投影坐标在 near_court_area 之外（即 court_margin_ft 外）
- **AND** 候选尚未被任何 player slot 锁定
- **THEN** 候选 SHALL NOT 被用于初始化新的 player slot
- **AND** 拒绝原因 SHALL 记录为 `rejected_outside_near_court_area`

#### Scenario: 已锁定球员的候选使用 tracking_area

- **WHEN** 候选已被某 LOCKED slot 关联
- **AND** 候选投影坐标在 tracking_area 内
- **THEN** 候选 SHALL 被接纳
- **AND** 即使候选在 near_court_area 外但 tracking_area 内，仍被接纳

#### Scenario: tracking_area 外的所有候选被拒绝

- **WHEN** 候选投影坐标在 tracking_area 外
- **THEN** 候选 SHALL 被拒绝
- **AND** 拒绝原因 SHALL 记录为 `rejected_outside_tracking_area`

### Requirement: 球员跟踪依据 effective FPS 计算时间
球员跟踪引擎 SHALL 使用后端统一的 `effective_fps` 计算帧时间戳、跟踪缓冲、身份重连窗口、插值窗口和主球员选择窗口。

#### Scenario: 时间戳使用 effective FPS
- **WHEN** 分析任务的 `effective_fps` 为 60fps 且处理第 120 帧
- **THEN** tracking overlay 中该帧时间戳 MUST 为约 2.0 秒
- **AND** 后端 MUST NOT 使用 30fps 或 90fps 默认值计算该时间戳

#### Scenario: 身份缓冲按秒换算
- **WHEN** 身份跟踪丢失缓冲配置为 1 秒，且 `effective_fps` 为 90fps
- **THEN** PlayerIdentityManager 接收的丢失缓冲 MUST 为约 90 帧
- **AND** 相同配置在 30fps 下 MUST 为约 30 帧

#### Scenario: 主球员选择窗口按真实时长一致
- **WHEN** 主球员选择窗口配置为 1 秒，且任务分别以 30fps 和 120fps 运行
- **THEN** PrimaryPlayerSelector 的窗口帧数 MUST 分别约为 30 和 120
- **AND** 两者代表的真实时间窗口 MUST 一致

### Requirement: PrimaryPlayerSelector 生命周期对齐 tracking run
系统 SHALL 在每次 `_run_tracking` 开始时创建新的 `PrimaryPlayerSelector` 实例，而非在 Pipeline 初始化时一次性创建。

#### Scenario: 单次 tracking run 创建
- **WHEN** `_run_tracking` 开始执行
- **THEN** 一个新的 `PrimaryPlayerSelector` SHALL 被创建
- **AND** 其 `max_subjects` SHALL 来自 `MatchAnalysisContext.expected_player_count`
- **AND** 其 `group_profile` SHALL 来自 `build_player_group_profile(match_context)`
- **AND** 旧的 selector 实例 SHALL 不再被引用

#### Scenario: 销毁不残留
- **WHEN** `_run_tracking` 因任何原因结束（成功、失败、取消）
- **THEN** 该次创建的 selector 及其内部 `_qualities`、`_history`、诊断数据 SHALL 不再影响下一次 tracking run

### Requirement: _is_in_court_neighborhood 语义澄清
系统 SHALL 将现有方法 `_is_in_near_court_area` 重命名为 `_is_in_court_neighborhood`，避免名称中的 "near" 与近端半场概念混淆。

#### Scenario: 重命名后行为不变
- **WHEN** `_is_in_court_neighborhood(court_position, margin_ft)` 被调用
- **THEN** 其行为 SHALL 与重命名前的 `_is_in_near_court_area` 完全一致
- **AND** 检查逻辑仍为"投影坐标是否在球场矩形加指定边距范围内"

### Requirement: 统一容量校验而非静默 min
系统 SHALL 将三个独立人数配置合并为统一的 `player_analysis_hard_limit`。当配置容量低于比赛需求时，系统 SHALL 以明确错误拒绝任务，而非静默 min 降级。

#### Scenario: 容量满足需求
- **WHEN** `settings.player_analysis_hard_limit=4` 且 `match_context.expected_player_count=4`
- **THEN** `effective_player_count` SHALL 为 4
- **AND** 任务 SHALL 正常运行

#### Scenario: 容量低于需求
- **WHEN** `settings.player_analysis_hard_limit=2` 且 `match_context.expected_player_count=4`（双打）
- **THEN** Pipeline SHALL 抛 `PipelineConfigurationError`
- **AND** 错误码 SHALL 为 `PLAYER_CAPACITY_BELOW_MATCH_REQUIREMENT`
- **AND** 错误信息 SHALL 包含期望值和配置值
- **AND** 任务 SHALL NOT 被视为普通的 `player_count_mismatch`

### Requirement: 重复重叠 track 抑制

后端 SHALL 对球员多目标跟踪输出应用重复 track 抑制：当两个 track 的 bbox 重叠度（IoU）超过阈值并持续达到连续帧数时，SHALL 只输出其中较可信/较旧的一个 track，抑制同一目标的重复跟踪，且不得影响球路径跟踪。

#### Scenario: 同目标分身被抑制

- **WHEN** 两个球员 track 的 bbox IoU ≥ 0.6 且持续 ≥ 3 帧（含单帧缺席容错）
- **THEN** 其中较新的 track（或置信度显著更低者）SHALL 从输出中剔除
- **AND** 置信度较高的 track SHALL 保留

#### Scenario: 短时或低度重叠不抑制

- **WHEN** 两个 track 的重叠低于阈值或未达到连续帧数
- **THEN** 两个 track SHALL 均保留输出

#### Scenario: 抑制对分离后恢复

- **WHEN** 曾被视为重复的 track 对后续 IoU 下降（目标分离）
- **THEN** 被抑制的 track SHALL 在分离持续数帧（重叠计数衰减到阈值以下）后可重新出现在输出中

### Requirement: 可选 ROI 检测契约 detect_regions

`PersonDetector` SHALL 提供方法 `detect_regions(frame, regions, confidence_override=None) -> list[Detection]`，对指定的图像 ROI 区域执行检测并返回源帧坐标系检测框。该方法 SHALL 为可选能力：未实现 ROI 推理的实现 SHALL 显式抛出 `RegionDetectionUnsupported`（并提供 `supports_region_detection = False`），SHALL NOT 用空列表静默表示"不支持"；`EmptyPersonDetector` SHALL 返回空列表（其语义为"永无检测"）。新增方法 SHALL NOT 改变现有 `detect` / `detect_frame` 行为。

#### Scenario: 未实现 ROI 推理显式报错

- **WHEN** 调用 `detect_regions` 于未实现 ROI 推理的 `PersonDetector` 实现
- **THEN** 系统 SHALL 抛出 `RegionDetectionUnsupported`
- **AND** `supports_region_detection` SHALL 为 False

#### Scenario: EmptyPersonDetector 返回空

- **WHEN** 调用 `detect_regions` 于 `EmptyPersonDetector`
- **THEN** 返回空列表且不抛异常

#### Scenario: 不影响现有接口

- **WHEN** 使用 `detect` / `detect_frame`
- **THEN** 行为 SHALL 与实现 `detect_regions` 之前完全一致

#### Scenario: ROI 结果坐标语义（P1 预留）

- **WHEN** 某实现返回 ROI 检测结果
- **THEN** 检测框坐标 SHALL 为源帧坐标系（非 ROI-local 坐标），与现有检测输出可互换

### Requirement: assignment-aware tracker update

`MultiObjectTracker` SHALL 提供兼容的 assignment-aware update，返回 tracks 以及本次输入 detection index 到 assigned track id 的精确映射。既有 `update(detections)` SHALL 保持原返回类型与行为，并可委托该新接口。

#### Scenario: 兼容 legacy update
- **WHEN** 既有单摄调用 `update(detections)`
- **THEN** 调用方 SHALL 获得与此前相同语义的 track list

#### Scenario: 获取 detection assignment
- **WHEN** joint session 使用 assignment-aware update
- **THEN** 系统 SHALL 能将 accepted guided detection 精确关联到其 assigned track id

