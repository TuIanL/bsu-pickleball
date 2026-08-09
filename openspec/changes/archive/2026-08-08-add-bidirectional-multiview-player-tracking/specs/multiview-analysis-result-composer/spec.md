# multiview-analysis-result-composer Delta

## ADDED Requirements

### Requirement: v1/v2 独立 writer + 公共 version-aware reader

系统 SHALL 提供独立 artifact writer:`late_fusion_v1 → writer_v1 → fused_player_trajectory.v1`(P0 writer 永远保留);`joint_tracking_v2 → writer_v2 → fused_player_trajectory.v2`。系统 SHALL 提供公共 `load_fused_trajectory(path)` reader:按 schema_version 归一化(`normalize_v1` / `normalize_v2`)为 Composer 消费的 internal model。

#### Scenario: version-aware 读取

- **WHEN** Composer 需要消费 fused trajectory
- **THEN** 系统 SHALL 按 schema_version 选择 v1/v2 归一化
- **AND** SHALL NOT 依赖"v1 reader 能读 v2 未知字段"的假设

#### Scenario: late_fusion 保留 v1

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 产物 SHALL 为 `fused_player_trajectory.v1`(writer_v1 不升级)
- **AND** 与 joint 的 v2 独立,A/B 为两个稳定版本

### Requirement: joint_tracking_v2 compose 来源

当 Parent 的 `multiviewExecutionMode=joint_tracking_v2` 时,Composer SHALL 从 Parent-owned `JointViewRuntime` A/B 与 `MultiViewJointRun` 获取产物,而非从 reference child 继承。overlay 球员标签 SHALL 使用 `GlobalPlayer_1/2...`,不使用 child 局部的 `Player_1/2...`。

#### Scenario: joint compose 来源

- **WHEN** joint Parent 完成 joint run
- **THEN** Composer SHALL 从 JointRun 获取 cam_1 / cam_2 view artifact 与 fused trajectory
- **AND** SHALL NOT 依赖 reference child 继承路径

#### Scenario: 全局身份标签

- **WHEN** joint 模式渲染视频 overlay
- **THEN** 球员标签 SHALL 来自 `GlobalPlayer_<id>`
- **AND** 同一真实球员在双摄下 SHALL 显示同一全局标签

### Requirement: late_fusion_v1 compose 不变

`executionMode=late_fusion_v1` 的 Composer 行为 SHALL 完全保持 P0 现状:位置类指标基于 fused 重算、非位置类产物从 reference child 继承、`fused_manifest.json` 作为 Parent 唯一出口。

#### Scenario: late_fusion child inheritance 保持

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** Composer SHALL 从 reference child 继承 pose/ball/overlay/serve 等
- **AND** 位置类指标基于 fused trajectory 重算(与 P0 一致)
