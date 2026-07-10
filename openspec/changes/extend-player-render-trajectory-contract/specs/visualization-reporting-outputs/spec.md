## ADDED Requirements

### Requirement: style_profile 和 segmentation_profile 快照写入渲染轨迹 artifact

系统 SHALL 在生成 `player_render_trajectory.json` 时将当前渲染配置的 `style_profile` 和 `segmentation_profile` 快照分别写入两个独立字段。

#### Scenario: style_profile 快照包含颜色映射和渲染参数

- **WHEN** visualization 阶段生成 player render trajectory artifact
- **THEN** `style_profile.players` MUST 包含每个 render_slot 的 hex 颜色（slot_1~4）
- **AND** `style_profile` MUST 包含球和弹跳点颜色
- **AND** `style_profile` MUST 包含 `player_trail_seconds`、`ball_trail_seconds`、`bounce_display_seconds`
- **AND** `style_profile` MUST 包含 `radius.min_px` 和 `radius.max_px`

#### Scenario: segmentation_profile 快照包含分段算法参数

- **WHEN** visualization 阶段生成 player render trajectory artifact
- **THEN** `segmentation_profile` MUST 包含 `jump_threshold_ft`、`max_visible_gap_seconds`
- **AND** `segmentation_profile.version` MUST 独立于 `style_profile.version`

#### Scenario: 主题和分段参数独立演进

- **WHEN** 主题资源文件升级为 `court-visual-theme.v2`（仅颜色变更）
- **AND** artifact schema 仍为 `player-render-trajectory.v2`
- **THEN** `style_profile.version` MUST 为 `court-visual-theme.v2`
- **AND** `segmentation_profile.version` MUST 仍为 `court-track-segmentation.v1`
- **AND** `schema_version` MUST 仍为 `player-render-trajectory.v2`

#### Scenario: 资源文件不可用时 fallback

- **WHEN** 后端无法读取 `court_render_profile.v1.json` 资源文件
- **THEN** 系统 SHALL 使用内置默认 profile 生成 style_profile 和 segmentation_profile 快照
- **AND** 系统 MAY 记录警告日志
- **AND** 系统 MUST NOT 因资源文件缺失导致 artifact 生成失败

### Requirement: style_profile 不影响现有 OverlayVideoWriter 渲染行为

系统 SHALL 在 artifact 中携带 style_profile 快照，但在本 Change 中不得改变 OverlayVideoWriter 的颜色或标记渲染逻辑。

#### Scenario: OverlayVideoWriter 行为不变

- **WHEN** OverlayVideoWriter 消费 v2 artifact 渲染分析叠加视频
- **THEN** 颜色、标记大小、线宽 MUST 与消费 v1 artifact 时一致
- **AND** 仅 segment_id 变化时清空 deque（新增行为除外）
