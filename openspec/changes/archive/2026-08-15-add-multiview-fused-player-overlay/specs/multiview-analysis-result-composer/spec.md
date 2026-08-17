## MODIFIED Requirements

### Requirement: joint_tracking_v2 compose 来源

当 Parent 的 `multiviewExecutionMode=joint_tracking_v2` 时，Composer SHALL 从 Parent-owned `JointViewRuntime` A/B 与 `MultiViewJointRun` 获取产物，而非从 reference child 继承。正式视频叠加层（fused player overlay）SHALL 来自 `multiview-fused-player-overlay.v1` 构建产物；overlay 球员标签 SHALL 使用 canonical `Player_1/2...`（展示为 P1-P4），不使用 `GlobalPlayer_<id>` 或 child 局部的 `Player_<id>`。

#### Scenario: joint compose 来源

- **WHEN** joint Parent 完成 joint run
- **THEN** Composer SHALL 从 JointRun 获取 cam_1 / cam_2 view artifact 与 fused trajectory
- **AND** SHALL NOT 依赖 reference child 继承路径

#### Scenario: 正式叠加层使用 fused overlay

- **WHEN** joint 模式渲染视频 overlay
- **THEN** 数据源 SHALL 为 `multiview-fused-player-overlay.v1` 构建产物（F0/F1 evidence + roster + geometry）
- **AND** SHALL NOT 从 `joint_debug_trace` 聚合正式检测框

#### Scenario: 全局身份标签

- **WHEN** joint 模式渲染视频 overlay
- **THEN** 球员标签 SHALL 来自 canonical `Player_N`（P1-P4）
- **AND** 同一真实球员在双摄下 SHALL 显示同一 canonical 标签
- **AND** `global_player_<id>` SHALL NOT 出现在面向用户的 overlay 字段

## ADDED Requirements

### Requirement: fused overlay 产物发布

joint 模式 Composer SHALL 把 `multiview-fused-player-overlay.v1` 发布到 Parent artifact 命名空间，补齐 `fused_player_overlay_url` / `fused_player_overlay_status` / `fused_player_overlay_detail` 契约，并将 overlay 入口加入 `fused_manifest.json` 的 artifacts 区。`tracking_overlay` 在 joint 模式 SHALL 不再作为正式视觉层发布（降级 debug-only），单摄模式行为不变。

#### Scenario: joint 模式发布 fused overlay

- **WHEN** joint Parent 完成 compose
- **THEN** Parent artifacts SHALL 包含 `fused_player_overlay_url`
- **AND** `fused_manifest.json` artifacts 区 SHALL 包含 fused overlay 入口

#### Scenario: joint 模式 tracking_overlay 降级

- **WHEN** joint 模式生成视觉产物
- **THEN** `tracking_overlay` SHALL 不作为正式视觉层发布
- **AND** 单摄（非 joint）模式 `tracking_overlay` SHALL 保持既有行为
