## MODIFIED Requirements

### Requirement: 可复用逐帧接口 step()

后端 SHALL 提供 `ViewTrackingSession`，封装单视角逐帧球员跟踪计算链（检测 → detection ROI 过滤 → 多目标跟踪 → 重复抑制 → 脚点 → 投影 → 平滑 → 主球员选择 → 锁定 → 身份 → 渲染观测），暴露 `step(frame, *, frame_index, timestamp, guidance=()) -> ViewFrameResult` 接口。默认 `guidance=()` 时输出与既有单视角 pipeline 完全一致（行为保护）。

#### Scenario: 逐帧调用
- **WHEN** 调用方逐帧调用 `step` 传入 frame / frame_index / timestamp
- **THEN** 返回 `ViewFrameResult`，包含 `frame_detections` / `frame_positions` / `render_raw_by_track` / `player_motion_pixels`
- **AND** session 内部按每 source frame 至多一次完整 tracking 链推进其 per-view 状态

#### Scenario: 默认 guidance 行为保护
- **WHEN** `guidance=()` 且无 guided detection 输入
- **THEN** session 输出 SHALL 与重构前的单视角跟踪路径一致
- **AND** 重构前后 synthetic differential test SHALL 逐项一致（raw detections / frame detections / positions / render observations / render events / player trajectory / metric tracks / ROI counters）

#### Scenario: joint guidance 与 formal eligibility
- **WHEN** `joint_tracking_v2` 传入非空 guidance
- **THEN** session SHALL 执行 guided ROI detection、pre-gate、merge 与一次 tracker update
- **AND** 仅经 `lock_only` formal eligibility 接纳且具 stable local `player_id` 的 detection 才可输出为 joint observation evidence

## ADDED Requirements

### Requirement: mode-scoped eligibility policy

session SHALL 支持 `legacy_union` 与 `lock_only` eligibility policy。单摄与 `late_fusion_v1` SHALL 保持 `legacy_union`，`joint_tracking_v2` SHALL 使用 `lock_only`；suggested track 不得绕过 lock-only 进入 joint boundary。

#### Scenario: guided track 未获 lock
- **WHEN** guided candidate 被 tracker 接住但不在 lock manager 的正式集合中
- **THEN** 系统 SHALL 不为其创建 JointViewObservation

### Requirement: joint local identity evidence

joint adapter SHALL 从 formal frame detections 中选择具有 stable local `player_id` 与 `identity_epoch` 的项，并与同 track 的 projected position 关联；其 source track 仅作为 provenance，不能替代 local identity。仅在 duplicate suppression 后仍 surviving 的 track evidence 才可输出。

#### Scenario: 非正式 track 被排除
- **WHEN** tracker 有 court position 但没有 formal local player identity
- **THEN** 该 track SHALL NOT 进入 global association

#### Scenario: suppressed track evidence 被排除
- **WHEN** assignment 后某 track 被 duplicate suppressor 移除
- **THEN** 与该 track 关联的 guided evidence SHALL NOT 输出为 JointViewObservation
