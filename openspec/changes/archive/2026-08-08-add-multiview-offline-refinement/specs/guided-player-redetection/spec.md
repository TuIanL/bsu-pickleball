# guided-player-redetection Delta

## ADDED Requirements

### Requirement: 离线第二遍检测复用 pre-gate 且只读 F0

offline refinement(F1)的 recovered detection SHALL 复用 guided candidate pre-gate 与 `detection_origin` 机制,不重写检测链、不修改 F0 的 tracker / lock / identity / global state。第二遍的 accepted 观测 SHALL 标记 `observation_origin=offline_refinement`,并同样满足"pre-gate 拒绝的 candidate 绝不碰 tracker"(invariant 9)。连续多帧证明 SHALL 使用窗口内轻量 `RecoveryTracklet`,不使用 F0 tracker。

#### Scenario: 离线路径复用 pre-gate 且不碰 tracker

- **WHEN** F1 对 RecoveryTickPlan 的 target tick 执行 `detect_regions`
- **THEN** 结果 SHALL 经 guided pre-gate 过滤
- **AND** 拒绝的 candidate 与 accepted 的 recovered 均 SHALL NOT 调用 F0 tracker / lock / identity 的 update

#### Scenario: RecoveryTracklet 窗口内累积

- **WHEN** 需要连续多帧证明某 recovered observation
- **THEN** 系统 SHALL 用 `RecoveryTracklet { recovery_window_id, previous_bbox, previous_canonical_position, consecutive_hits }`
- **AND** SHALL NOT 复用或改写 F0 `MultiObjectTracker`

#### Scenario: 离线来源标记

- **WHEN** 一个 F1 第二遍检测被接受
- **THEN** 其观测 SHALL 标记 `observation_origin=offline_refinement`
- **AND** 与 `base` / `guided_roi` 来源正交可区分
