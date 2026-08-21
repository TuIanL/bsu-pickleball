## ADDED Requirements

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