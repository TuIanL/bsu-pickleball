# multiview-fused-player-overlay Delta

## ADDED Requirements

### Requirement: 正式 Player overlay 支持按 view 输出

joint 模式正式 Player overlay SHALL 为每个可用 view 提供以 canonical tick/timestamp 对齐的 image-space frames。所有 view SHALL 只读复用同一份 canonical Player roster；view-specific bbox、footpoint、evidence、donor 和质量字段不得改变 `player_id` 或 `render_slot`。

#### Scenario: 两路都可生成 overlay

- **WHEN** joint 任务包含 `cam_1` 与 `cam_2` 的 view geometry
- **THEN** overlay artifact 或其 view-scoped API SHALL 能分别返回 `cam_1` 与 `cam_2` 的 frames
- **AND** 同一 tick 的 P1-P4 SHALL 在两路使用相同 canonical identity

#### Scenario: 目标 view 没有可靠 bbox

- **WHEN** 某 Player 在目标 view 没有通过质量门的 bbox
- **THEN** 该 view 的 entity SHALL 保留 canonical identity、canonical position 或明确缺失状态
- **AND** bbox SHALL 为 `null` 或由已有合法 view-specific evidence 生成
- **AND** SHALL NOT 复制其他 Player 的 bbox 或重新分配 roster

### Requirement: 旧 overlay artifact 安全归一化

读取仅包含顶层 `reference_view_id` 和单路 `frames` 的历史 overlay 时，系统 SHALL 将其归一化为仅 reference view 可用的 view-scoped 结构。系统 SHALL NOT 宣称历史 artifact 包含另一 view 的 Player overlay。

#### Scenario: 历史 v1 overlay

- **WHEN** 前端读取旧版单路 fused overlay
- **THEN** 默认 reference view SHALL 正常展示
- **AND** 另一 view 的切换控件 SHALL 禁用或显示明确的产物不可用状态
