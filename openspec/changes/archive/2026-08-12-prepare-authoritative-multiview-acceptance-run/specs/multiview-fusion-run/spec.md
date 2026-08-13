## ADDED Requirements

### Requirement: Joint debug trace ownership

`joint_tracking_v2` 的 `joint_debug_trace.v1.json` SHALL 归属于 `jointRunId` 的 diagnostic artifact 目录，并 SHALL 与 `fused_player_trajectory.v2`、recovery diagnostics 和 refinement artifacts 分离。`late_fusion_v1` SHALL 不因该能力产生 debug trace。

#### Scenario: joint run 开启 debug trace
- **WHEN** `joint_tracking_v2` 的 debug trace 开关为 true
- **THEN** trace SHALL 写入当前 JointRun 目录
- **AND** manifest SHALL 记录 trace schema/version 和启用配置

#### Scenario: late fusion 运行
- **WHEN** Parent execution mode 为 `late_fusion_v1`
- **THEN** 系统 SHALL 保持原有 MultiViewFusionRun artifact 行为
- **AND** SHALL NOT 写入 joint debug trace

### Requirement: Trace uses canonical run decisions

debug trace SHALL 使用 `MultiViewJointRun` 已产生的 canonical tick、FrameSample、guidance snapshot、ViewFrameResult、association update 和 fused state。trace renderer 和 writer SHALL NOT 重新运行 tracker、重新调用 detector 或重新选择 source frame。

#### Scenario: renderer 重放已完成 run
- **WHEN** JointRun trace 与原视频可用
- **THEN** renderer SHALL 按 trace 中的 source frame index 读取两路视频
- **AND** 两路视频 SHALL 在同一 canonical tick 下展示

#### Scenario: trace 缺少 source decision
- **WHEN** trace 无法提供某 view 的 source frame/status decision
- **THEN** renderer SHALL 报告 trace schema/input error
- **AND** SHALL NOT 按相同 frame number 进行隐式配对

### Requirement: Diagnostic deletion isolation

删除或重新生成 debug trace、debug MP4 和 summary report SHALL 不删除、不覆盖、不改变 `fused_player_trajectory.v2`、existing recovery diagnostics、原视频或单视角 artifacts。

#### Scenario: 清理 debug 输出
- **WHEN** 开发者删除某次 Visual Acceptance Run 的 debug directory
- **THEN** 业务 trajectory、diagnostics、CaptureTake 和原始 media SHALL 保持不变
