# ball-tracking Specification

## Purpose
Define the inactive state for ball detection, trajectory, overlay, and event-analysis artifacts while the active product flow focuses on player movement and pose analysis.
## Requirements
### Requirement: Ball detection artifact
系统 SHALL 在球检测启用且所需 detector 依赖可用时，为真实分析任务创建并暴露球检测 artifact，包括 `ball_overlay.json`（帧级叠加数据）、`detections.jsonl`（共享检测合同）和 `ball_trajectory.json`（轨迹连续采样）。

#### Scenario: Ball detection enabled and candidates are produced
- **WHEN** 真实分析任务启用球检测且配置的 detector 输出可用球候选
- **THEN** backend SHALL 写入 `ball_overlay.json`（帧级叠加数据）
- **AND** backend SHALL 将球检测记录写入共享 `detections.jsonl` artifact 合同
- **AND** backend SHALL 写入 `ball_trajectory.json`（原始轨迹 sample）
- **AND** job result SHALL 暴露生成的 artifact URL、status 和 detail

#### Scenario: Ball detection disabled
- **WHEN** 真实分析任务在球检测关闭时运行
- **THEN** backend SHALL 不生成 `ball_overlay.json`
- **AND** `ball_overlay_status` SHALL 为 `skipped`
- **AND** pipeline SHALL 不因此失败

#### Scenario: Ball detector dependencies are unavailable
- **WHEN** 球检测启用但 detector 配置、模型路径、adapter 或运行时依赖不可用
- **THEN** backend SHALL 将球检测阶段标记为 unavailable 或 failed 并附明确诊断
- **AND** 现有 player movement、pose、tracking、projection 和 serve 输出在自身输入有效时 MUST 继续可用

#### Scenario: Legacy ball artifacts exist
- **WHEN** 旧持久化输出目录仍包含当前 job result 未引用的球 artifact 文件
- **THEN** 系统 SHALL 将这些文件视为旧清理数据而非活跃分析输出

### Requirement: Ball trajectory continuity
The backend SHALL generate ball trajectory continuity artifacts when ball detection is enabled and the pipeline receives usable ball candidate samples.

#### Scenario: Trajectory processing runs
- **WHEN** a current real analysis job runs with ball detection enabled and frame-level ball candidates are available
- **THEN** the pipeline runs ball trajectory filtering, prediction, continuity checks, cleaning, and short-gap interpolation
- **AND** the pipeline writes raw and cleaned ball trajectory artifacts with status and detail

#### Scenario: Trajectory input is unavailable
- **WHEN** ball trajectory processing lacks detector samples, frame timing, or required video metadata
- **THEN** the pipeline records the trajectory stage as skipped, unavailable, partial, or no-candidates with an explanatory detail
- **AND** the job MUST NOT fail solely because ball trajectory output is unavailable

#### Scenario: Player movement remains supported
- **WHEN** ball trajectory processing is omitted, unavailable, or fails in a recoverable way
- **THEN** player/person detection, pose, tracking, projection, and movement metrics remain the supported analysis path

#### Scenario: Stationary false positives are filtered over time
- **WHEN** ball tracker processes frames where a stationary object (e.g., court marking, debris) is repeatedly detected at the same image position
- **THEN** the tracker SHALL accumulate a per-position stationary vote count across frames
- **AND** the tracker SHALL also accept an optional `player_motion_pixels` signal from the pipeline
- **AND** if `player_motion_pixels` is provided and exceeds `player_motion_min_pixels`, the stationary vote SHALL be weighted higher
- **AND** SHALL permanently reject candidates at positions whose accumulated stationary frame count exceeds the configured threshold (default 60 frames)
- **AND** the rejection reason SHALL be recorded as `static_false_positive`
- **AND** the blacklist SHALL be scoped to the current job (cleared on recalibration)

#### Scenario: Genuine ball movement overrides stationary blacklist
- **WHEN** a candidate at a blacklisted position passes continuity checks (within dynamic physics gate of the last valid ball position)
- **THEN** the tracker SHALL accept the candidate despite the blacklist
- **AND** this ensures the blacklist does not inhibit real ball tracking when the ball happens to occupy a previously flagged position

#### Scenario: Stationary candidate during player inactivity is not penalized
- **WHEN** a candidate remains stationary
- **AND** player motion is below `player_motion_min_pixels` (player is also stationary or absent)
- **THEN** the tracker SHALL NOT apply the player-motion-aware static penalty
- **AND** the candidate SHALL be evaluated using normal state-dependent scoring

#### Scenario: Non-play timeline context is optional
- **WHEN** the pipeline does not provide non-play timeline events
- **THEN** the tracker SHALL use `player_motion_pixels` as a weak signal of active play
- **AND** if `player_motion_pixels` is also unavailable, the tracker SHALL fall back to the existing stationary blacklist behavior without error
- **AND** this ensures the player-motion-aware static suppression does not block on missing timeline data

### Requirement: Ball overlay artifact retrieval
系统 SHALL 在 job 生成 `ball_overlay.json` 时通过共享分析 artifact 合同支持球 overlay artifact 获取，返回包含 source metadata、coverage 摘要和 frame 数组的完整 payload。

#### Scenario: Client opens a current job with ball overlay available
- **WHEN** 已完成的当前 job 引用 `ball_overlay.json`
- **THEN** 客户端 MAY 获取并渲染球 overlay 数据作为真实 job 图层
- **AND** 响应 MUST 包含 source metadata（width、height、fps、frame_stride、processed_frame_count）
- **AND** 响应 MUST 包含 coverage 摘要（overlay_frame_count、missing_frame_count、detection_rate）

#### Scenario: Client opens a current job without ball overlay
- **WHEN** 已完成的当前 job 没有生成 ball overlay
- **THEN** 客户端 SHALL 忽略缺失的球 overlay artifact 或标记图层 unavailable
- **AND** 客户端 MUST NOT 渲染模拟球 overlay 数据作为真实 job 结果

#### Scenario: Ball overlay endpoint is requested for a missing current artifact
- **WHEN** 客户端请求未生成 `ball_overlay.json` 的当前 job 的 `ball-overlay`
- **THEN** backend SHALL 返回 404 而非将 artifact name 拒绝为不支持

#### Scenario: Ball overlay endpoint is requested for an existing artifact file
- **WHEN** 客户端请求 job 目录包含 `ball_overlay.json` 的 `ball-overlay`
- **THEN** backend SHALL 通过共享分析 artifact API 返回 JSON artifact

### Requirement: Ball overlay contains frame-level detection data
系统 SHALL 在球检测启用且有候选时写入 `ball_overlay.json`，包含逐帧 image-space bbox/center/confidence 和可选的 court-space 投影点，用于前端视频叠加渲染。

#### Scenario: Ball overlay is generated when detection succeeds
- **WHEN** 真实分析任务启用球检测且逐帧 ball tracker 产生 sample
- **THEN** pipeline SHALL 写入 `ball_overlay.json` 到 `outputs/{job_id}/ball_overlay.json`
- **AND** `AnalysisPipelineResult.artifacts` SHALL 填充 `ball_overlay_json_path`、`ball_overlay_url`、`ball_overlay_status` 和 `ball_overlay_detail`

#### Scenario: Ball overlay records per-frame detection status
- **WHEN** pipeline 写入 `ball_overlay.json`
- **THEN** 每个 frame SHALL 通过 `track_status` 字段区分 `detected`（检测到且接受）、`missing`（无候选或未通过连续性检查）、`rejected`（被面积/长宽比/ROI 过滤）

#### Scenario: Ball overlay aligns with ball trajectory frame indices
- **WHEN** `ball_overlay.json` 和 `ball_trajectory.json` 同时生成
- **THEN** 两者的 `frame_index` 和 `timestamp_seconds` MUST 对齐
- **AND** 同一 `frame_index` 的 ball center 坐标 MUST 一致

#### Scenario: Ball overlay is not generated when tracking is unavailable
- **WHEN** 球检测未启用、模型不可用或 pipeline 路径 B/C（无标定/无视频）
- **THEN** `ball_overlay_status` MUST 为 `skipped` 或 `unavailable`
- **AND** `ball_overlay_json_path` 和 `ball_overlay_url` MAY 为 null
- **AND** pipeline MUST NOT failed

### Requirement: Ball tracking does not imply shot events
The system SHALL allow ball tracking, trajectory, and bounce candidate artifacts to become available before full shot, rally, scoring, or tactical event semantics are implemented.

#### Scenario: Ball trajectory facts are available
- **WHEN** a current real-job report surface has ball trajectory or bounce candidate artifacts
- **THEN** the system may present those facts as algorithm-derived candidates
- **AND** the system MUST label them distinctly from complete shot, rally, scoring, or tactical conclusions

#### Scenario: Report requires event semantics
- **WHEN** a current real-job report surface would require hit events, shot classification, rally segmentation, scoring, or tactical conclusions that are not implemented
- **THEN** the system omits that surface or marks it unavailable rather than fabricating event conclusions

### Requirement: Locked-state missing-over-false-positive policy
The system SHALL respect the missing-over-false-positive policy when the ball tracker is in LOCKED state. No candidate may be accepted solely because it has the highest detector confidence if it fails the dynamic physics gate.

#### Scenario: Missing frame preferred over distant false positive
- **WHEN** the ball tracker is in LOCKED state
- **AND** the true ball is temporarily occluded or missed by the detector
- **AND** the only available candidate is a high-confidence detection far from the predicted position
- **THEN** the tracker MUST reject the distant candidate
- **AND** SHALL emit a missing frame with `overall_decision = "missing_predicted_only"`
- **AND** SHALL record `predicted_position` in the frame output
- **AND** the ball trajectory artifact SHALL contain the predicted position for downstream use (interpolation, bounce detection, rally segmentation)

#### Scenario: Candidate must pass physics gate in LOCKED state
- **WHEN** the ball tracker is in LOCKED state
- **AND** multiple candidates exist
- **THEN** each candidate MUST pass the dynamic physics gate before being eligible for acceptance
- **AND** candidates that fail the gate SHALL be rejected regardless of detector confidence
- **AND** the rejection reason for gated candidates SHALL be `physics_gate_rejected`

#### Scenario: SEARCHING state does not enforce missing-over-false-positive
- **WHEN** the ball tracker is in SEARCHING state
- **AND** a single high-confidence candidate exists far from previous detections
- **THEN** the tracker MAY accept the candidate to initialize a new track
- **AND** the missing-over-false-positive policy SHALL NOT apply in SEARCHING state

### Requirement: Per-frame debug metadata in ball overlay
The ball overlay artifact SHALL include per-frame track state and candidate decision metadata when the ball tracking pipeline is enabled.

#### Scenario: Debug metadata is available in ball_overlay.json
- **WHEN** `ball_overlay.json` is generated with ball tracking enabled
- **AND** this change's state machine and physics gating are active
- **THEN** each frame SHALL include optional debug fields: `track_state`, `predicted_position`, `accepted_candidate_id`, and `overall_decision`
- **AND** the debug fields SHALL be optional and positioned after the core detection data

#### Scenario: Missing frame contains predicted position
- **WHEN** a frame has `track_status = "missing"` and the tracker is in LOCKED or LOST state
- **THEN** the frame SHALL include `predicted_position` in image coordinates
- **AND** the frame SHALL include `track_state` indicating LOCKED or LOST

### Requirement: 球跟踪和弹跳检测依据 effective FPS
球跟踪、静止候选过滤和弹跳检测 SHALL 使用后端统一的 `effective_fps` 计算速度、静止时长、缺失窗口和事件间隔。

#### Scenario: 静止球黑名单按秒换算
- **WHEN** 静止候选黑名单阈值配置为 2 秒，且 `effective_fps` 为 60fps
- **THEN** BallTracker MUST 在约 120 帧静止累计后触发黑名单逻辑
- **AND** 该逻辑 MUST NOT 固定使用 60 帧

#### Scenario: 弹跳事件间隔按 FPS 换算
- **WHEN** BounceDetector 的最小事件间隔配置为 0.25 秒，且 `effective_fps` 为 120fps
- **THEN** BounceDetector MUST 使用约 30 帧作为事件去重间隔
- **AND** 在 30fps 下 MUST 使用约 8 帧

#### Scenario: 球速度使用真实 FPS
- **WHEN** 相邻帧球坐标位移为 10 像素且 `effective_fps` 为 90fps
- **THEN** 球速度计算 MUST 使用 900 像素/秒作为该位移对应速度
- **AND** 后端 MUST NOT 使用 30fps fallback 计算为 300 像素/秒

### Requirement: 候选证据共享且 detector 每帧一次
系统 SHALL 使 `BallTracker` 支持从外部候选集合消费：抽出 `update_from_candidates(frame_index, view_candidates, ...)`，同时保留 `update(frame)` 现有单摄行为，detector 每视角每 canonical tick 只运行一次。

#### Scenario: 单次检测多消费者
- **WHEN** joint runtime 某视角某 tick 需要球跟踪
- **THEN** detector SHALL 只运行一次
- **AND** 经基础视觉过滤得到 `BallViewCandidate[]` 后，同一集合同时供本地 tracker 与 stereo associator
- **AND** `BallTracker` SHALL 通过 `update_from_candidates(...)` 消费该集合，不再自行重复 detect

#### Scenario: 单摄行为保持
- **WHEN** 现有单摄分析调用 `BallTracker.update(frame)`
- **THEN** 其行为 SHALL 与改动前一致（behavior-preserving refactor）
- **AND** 既有 ball tracking 回归测试 SHALL 全部通过

#### Scenario: stereo 不反向修改 tracker 状态
- **WHEN** stereo associator 完成跨视角关联
- **THEN** 关联结果 SHALL NOT 反向修改 `BallTracker` 状态
- **AND** 执行序 SHALL 为 detect/filter → snapshot predictor → stereo association → local tracker update

### Requirement: 球链仅消费 available 帧
系统 SHALL 使球检测/跟踪仅消费 `frame_status == "available"` 的真实源帧，`available_extrapolated` 不进入球链。

#### Scenario: 外推帧不进 tracker
- **WHEN** 某 canonical tick 的 view 帧为 `available_extrapolated`
- **THEN** 该帧 SHALL NOT 作为新的 detector/tracker 输入
- **AND** 仅作 Debug Replay 显示

### Requirement: 高速小球多帧候选一致性
系统 SHALL 在不重复运行 detector 的前提下，以连续多帧候选、预测位置、尺度变化、场地 ROI、静态位置历史和运动物理约束筛选球候选，并保存每个候选的接受或拒绝原因。

#### Scenario: 单帧高置信静态误检
- **WHEN** 高置信候选长期停留在广告牌、边线标记或固定灯光位置且不符合球运动
- **THEN** tracker SHALL 将其标记为静态误检并加入有期限的黑名单
- **AND** MUST NOT 仅因单帧置信度最高而锁定该候选

#### Scenario: 高速球短时模糊或漏检
- **WHEN** 真球在短时间内出现尺度变化、运动模糊或少量缺帧但仍与预测轨迹一致
- **THEN** tracker SHALL 保持同一轨迹身份
- **AND** 缺失帧 SHALL 标记为 predicted，不得冒充 detector 观测

### Requirement: 球跟踪连续性使用有效时间步长
球 tracker 的速度、预测门、静止窗口和丢失阈值 SHALL 使用 effective FPS、frame stride 与真实 timestamp 计算，MUST NOT 假设相邻处理样本的 source frame index 差恒为 1。

#### Scenario: stride 为 2
- **WHEN** 源视频 60 FPS 且分析 stride 为 2
- **THEN** frame index 从 `n` 变为 `n+2` SHALL 被视为一个正常处理时间步
- **AND** tracker SHALL NOT 因帧索引差为 2 自动进入 lost 或重新搜索状态

