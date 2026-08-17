## ADDED Requirements

### Requirement: fused player overlay 产物字段

分析产物 contract SHALL 新增 `fused_player_overlay_json_path` / `fused_player_overlay_url` / `fused_player_overlay_status` / `fused_player_overlay_detail` 四字段，作为 joint 模式正式球员叠加层的产物契约（对应 `multiview-fused-player-overlay.v1` artifact）。

#### Scenario: joint 模式填充字段

- **WHEN** joint_tracking_v2 任务完成 compose 且 fused overlay 生成成功
- **THEN** `fused_player_overlay_json_path` SHALL 指向 Parent 命名空间的 overlay JSON 文件
- **AND** `fused_player_overlay_url` SHALL 为浏览器可访问的 artifact URL（非本地绝对路径）
- **AND** `fused_player_overlay_status` SHALL 为 `available`

#### Scenario: 生成失败显式状态

- **WHEN** fused overlay 生成失败
- **THEN** `fused_player_overlay_status` SHALL 为 `unavailable`
- **AND** `fused_player_overlay_detail` SHALL 说明失败原因

#### Scenario: 非 joint 模式不填充

- **WHEN** 任务执行模式为单摄或 late_fusion_v1
- **THEN** `fused_player_overlay_*` 字段 SHALL 保持未设置（null）
- **AND** 既有 `tracking_overlay_*` 字段行为 SHALL 不变
