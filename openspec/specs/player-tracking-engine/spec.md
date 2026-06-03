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
The backend SHALL provide a `FootpointEstimator` that estimates the player's image-space ground contact point from each tracked person bbox using bbox bottom-center for the MVP.

#### Scenario: Bbox bottom center is estimated
- **WHEN** the estimator receives bbox `[x1, y1, x2, y2]`
- **THEN** it returns `image_footpoint` equal to `[(x1 + x2) / 2, y2]` with method `bbox_bottom_center`

#### Scenario: Future footpoint strategy is selected
- **WHEN** future pose or segmentation strategies are added
- **THEN** the estimator interface can report `pose_ankle_average` or `segmentation_mask_bottom` without changing downstream projection output shape

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
The backend SHALL select renderable overlay subjects from tracked people using target-court-aware tracklet scoring and participant-limited ranking based on detection confidence, track quality, target court membership, and group consistency rather than using standard court-line bounds or single-frame track quality as the primary visibility rule.

#### Scenario: High-confidence match players are selected
- **WHEN** a processed frame or selection window contains tracked people with high detection confidence, stable recent track history, and strong target-court membership
- **THEN** the backend includes those tracks in renderable overlay frames up to the configured participant limit

#### Scenario: Low-confidence incidental detections are dropped
- **WHEN** a processed frame or selection window contains tracked people whose detection confidence, track quality, or target-court membership falls below the configured primary-player selection threshold
- **THEN** the backend excludes those tracks from renderable overlay frames while preserving raw detection or tracking diagnostics where available

#### Scenario: Player steps outside court lines
- **WHEN** a tracked player has high confidence, primary-player track quality, and strong target-court membership but their projected footpoint is slightly outside the standard court lines during normal match movement
- **THEN** the backend keeps that track eligible for renderable overlay frames instead of hiding it solely because it is line-out

#### Scenario: Frame contains more tracked people than match participants
- **WHEN** a frame or selection window contains more eligible tracked people than the configured player count for the match context
- **THEN** the backend keeps the highest-ranked target-court primary-player tracks and excludes lower-ranked incidental or non-target-court tracks from renderable overlay frames

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
The Player Tracking Engine SHALL support overlay labels that include stable player identity when available while preserving existing temporary track labels for diagnostics.

#### Scenario: Player identity is available for frame detection
- **WHEN** an overlay frame is built after player identity assignment
- **THEN** each eligible player box can include a renderable label equivalent to `P<player_id> / T<track_id>`

#### Scenario: Player identity is not available
- **WHEN** an overlay frame is built before identity assignment or identity assignment is disabled
- **THEN** the overlay remains compatible with existing `track_id`-only rendering

#### Scenario: More eligible tracks than match participants
- **WHEN** a frame contains more eligible tracked people than the configured participant count
- **THEN** the backend limits player-identity overlay subjects to the configured participant count and keeps rejected tracks in diagnostics where available

### Requirement: 投影观测点 schema 边界语义
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

