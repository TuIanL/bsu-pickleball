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
- **WHEN** the pipeline does not provide non-play timeline events or a `BallSearchPolicy` semantic snapshot
- **THEN** the tracker SHALL use `player_motion_pixels` as a weak signal of active play
- **AND** if `player_motion_pixels` is also unavailable, the tracker SHALL fall back to the existing stationary blacklist behavior without error
- **AND** this ensures the player-motion-aware static suppression does not block on missing timeline data

#### Scenario: Semantic policy is available
- **WHEN** the pipeline provides a `BallSearchPolicy` decision for the canonical tick
- **THEN** the tracker SHALL consume the decision after semantic evaluation and before formal candidate publication
- **AND** raw detector candidates SHALL remain available for diagnostics even when the policy suppresses formal output

#### Scenario: Semantic context is unknown or fails open
- **WHEN** the semantic phase is `UNKNOWN` or the timeline/provider fails in a recoverable way
- **THEN** the tracker SHALL preserve the existing candidate filtering and state-machine behavior
- **AND** the job SHALL continue without treating missing semantic context as a ball-tracking failure

#### Scenario: Authoritative non-play context suppresses formal candidates
- **WHEN** the canonical time is inside an authoritative manual or corrected `non_play` window
- **AND** policy mode is `enforced`
- **THEN** the tracker SHALL prevent new candidates from entering formal tracker output
- **AND** the pipeline SHALL retain the raw candidates, suppression reason, and semantic diagnostics
- **AND** policy suppression MUST NOT by itself add a candidate to the stationary false-positive blacklist

#### Scenario: Algorithmic activity remains a soft constraint
- **WHEN** non-play evidence comes only from player motion, player placement, or inferred activity changes
- **THEN** the tracker MAY lower candidate priority or record a policy suggestion
- **AND** it MUST NOT hard-disable the formal ball chain without sufficiently stable corroborating evidence

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

### Requirement: Authoritative semantic gating controls formal tracker lifecycle

当 take/job 显式启用 Enforced rollout，且 canonical semantic snapshot 来自 manual/corrected 权威时间线时，球跟踪 SHALL 在正式候选发布边界执行语义 gate 和 lifecycle action；Shadow、UNKNOWN、algorithm authority 或 provider 失败 SHALL 保持 fail-open 兼容行为。

#### Scenario: 权威非比赛封存当前正式球段

- **WHEN** 当前时间命中 manual/corrected 的 `non_play` 或 `rally_end`
- **AND** Enforced rollout 已启用
- **THEN** tracker SHALL 在该边界封存当前 formal trajectory segment
- **AND** SHALL 禁止边界后的新候选进入已封存段或正式 overlay
- **AND** SHALL 保留 raw candidate、suppression reason 和 boundary metadata

#### Scenario: Tracker reset 只在边界边沿执行一次

- **WHEN** semantic phase 从 active/pre-serve 进入 `NON_PLAY_CONFIRMED` 或 `POST_RALLY`
- **THEN** tracker SHALL 清理预测位置、暂态候选、连续性计数和本回合 formal state
- **AND** 同一 `boundary_action_id` 的后续 tick MUST NOT 重复 reset 或重复封存
- **AND** job 级语义诊断和 raw candidate history SHALL 保留

#### Scenario: Semantic suppression does not pollute stationary blacklist

- **WHEN** 候选仅因 authoritative semantic gate 被抑制
- **THEN** tracker SHALL NOT 增加该候选的 stationary false-positive blacklist 计数
- **AND** 该候选 SHALL 可在 diagnostics 中标记为 `policy_suppressed`

#### Scenario: Unknown or algorithm context fails open

- **WHEN** snapshot phase 为 `UNKNOWN`、authority 为 `algorithm/none` 或 semantic provider 失败
- **THEN** tracker SHALL 继续使用既有连续性、物理门、预测和黑名单逻辑
- **AND** SHALL NOT 因语义上下文缺失而 reset 或禁止正式输出

### Requirement: Serve reacquisition is separated from formal publication

球跟踪 SHALL 在 `PRE_SERVE` 和 `SERVE_ARMED` 阶段支持 warm/reacquire 路径；手持静止球或单帧弱候选不得直接成为正式球点，只有满足运动、连续性、发球区域或权威回合开始条件的候选才可进入正式发布。

#### Scenario: Prepare serve ignores stationary handheld candidate

- **WHEN** semantic phase 为 `PRE_SERVE`
- **AND** detector 输出位于球员手部/身体附近且在连续 tick 中基本静止的候选
- **THEN** tracker SHALL 将候选保留为 raw 或 warm diagnostic
- **AND** SHALL NOT 将其直接发布为 formal trajectory sample

#### Scenario: Armed serve permits progressive reacquisition

- **WHEN** semantic phase 为 `SERVE_ARMED`
- **AND** 候选满足配置的发球区域、运动变化或连续性门槛
- **THEN** tracker SHALL 允许候选进入 reacquire/tracker path
- **AND** formal publish SHALL 仅在候选满足正式发布条件或命中权威 `rally_start` 后生效

#### Scenario: Rally start opens a new formal segment

- **WHEN** canonical semantic context 进入 `RALLY_ACTIVE`
- **AND** 已执行 `open_formal_segment`
- **THEN** 后续通过 tracker 质量门的候选 SHALL 进入新的 formal segment
- **AND** 新 segment MUST NOT 复用上一回合的 segment id 或预测历史

### Requirement: Dual-view semantic boundary application is consistent

双摄球处理 SHALL 在同一个 canonical tick 使用一个 `MatchSemanticSnapshot`、一个 `BallSearchDecision` 和一个 boundary action；两路 tracker 各自消费候选，但不得独立重算 phase、重复封存或重复 reset。

#### Scenario: Both views share one boundary action

- **WHEN** 双摄 canonical tick 命中权威 semantic boundary
- **THEN** 两个视角 SHALL 使用同一 `boundary_action_id` 和 `take_timestamp_ms`
- **AND** formal publish gate SHALL 在两路 commit 前生效
- **AND** 两路 SHALL 各自保留 raw/formal before-after diagnostics

#### Scenario: One view is missing at the boundary

- **WHEN** 一个视角在 semantic boundary tick 缺帧或为 `available_extrapolated`
- **THEN** 缺失视角 SHALL 不运行新的 detector/tracker 输入
- **AND** joint semantic boundary SHALL 仍只执行一次
- **AND** 另一可用视角不得因此创建第二个 phase 或第二个 segment

### Requirement: Calibrated semantic boundaries preserve reversible tracker lifecycle

当 semantic adjudicator 输出 `pending_start` 或 `pending_end` 时，BallTracker SHALL 保留受配置 grace window 约束的连续性上下文；只有 confirmed boundary 在 Enforced rollout 下才可以封存 segment、reset tracker 或打开新的 formal segment。

#### Scenario: Pending end does not clear active tracker state

- **WHEN** algorithmic evidence 使回合结束变得可能但 boundary 尚未 confirmed
- **THEN** tracker SHALL 保留当前预测位置、连续性计数和 formal segment
- **AND** SHALL 将候选标记为 pending 或 diagnostic，而不是立即执行 reset

#### Scenario: Confirmed boundary still resets exactly once

- **WHEN** manual/corrected boundary 已通过 adjudicator 确认且 Enforced rollout 生效
- **THEN** tracker SHALL 在 formal candidate publication 前执行对应 lifecycle action
- **AND** 同一 `boundary_action_id` 的后续 tick MUST NOT 重复封存、reset 或创建 segment

#### Scenario: New rally does not reuse the sealed segment

- **WHEN** confirmed end 已封存上一段且后续语义进入 `RALLY_ACTIVE`
- **THEN** tracker SHALL 创建新的 formal segment id
- **AND** 新段 MUST NOT 复用上一段的预测历史、暂态候选或 segment id

### Requirement: Pending semantic boundaries support bounded active-rally rescue

系统 SHALL 允许在 boundary 尚未 confirmed 时使用满足配置的球运动、轨迹连续性和球员活动联合证据救援当前回合；rescue 不得跨越已经执行的 authoritative reset。

#### Scenario: Continuous moving candidates rescue pending end

- **WHEN** tracker 处于 `pending_end`
- **AND** 候选在预测门内连续出现且球员活动符合比赛中条件
- **THEN** tracker SHALL 清除 pending end 影响并继续当前 formal segment
- **AND** diagnostics SHALL 记录 `rescued_active` 及其证据 ids

#### Scenario: Weak candidate cannot rescue by itself

- **WHEN** pending end 期间只有单帧高置信候选但没有运动连续性或球员活动 corroboration
- **THEN** tracker SHALL 保持 pending 或 fail-open 的既有处理
- **AND** SHALL NOT 因该候选直接创建新的 formal segment

#### Scenario: Authoritative reset blocks rescue across segments

- **WHEN** authoritative boundary 已确认并执行 `seal_formal_segment` 与 `reset_tracker_for_next_rally`
- **THEN** 后续候选 MUST NOT 追加到旧 segment
- **AND** 只能通过新的 rally start/open action 进入新的 segment

### Requirement: Tracker diagnostics expose adjudication impact

系统 SHALL 在球跟踪诊断中区分 pending、confirmed、rescued 和 suppressed candidate，并记录 semantic boundary action、formal candidate before/after、segment id、grace window 和 fallback reason。

#### Scenario: Pending candidate is auditable

- **WHEN** 候选被 pending semantic boundary 影响
- **THEN** diagnostics SHALL 保留 raw candidate、pending reason、evidence ids 和当前 segment id
- **AND** SHALL 不将其误记为 stationary false positive

#### Scenario: Enforced and Shadow remain distinguishable

- **WHEN** 同一输入分别运行 Shadow 与 Enforced policy
- **THEN** tracker diagnostics SHALL 能区分建议的 boundary action 与实际执行的 lifecycle action
- **AND** SHALL 记录两种模式的 formal candidate counts

