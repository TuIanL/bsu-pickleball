## MODIFIED Requirements

### Requirement: Primary-player overlay subject selection

**FROM**: 选择器使用固定的全局配置 `max_subjects=4`，按置信度和 tracklet 质量排序后取前 N 名。

**TO**: 选择器使用 `MatchAnalysisContext.expected_player_count` 作为 `max_subjects`，在单打上下文中引擎 SHALL 只选择最多 2 名球员，双打上下文中选择最多 4 名球员。

系统 SHALL 选择渲染叠加层展示球员时使用赛制感知的目标球员数量，而不是全局固定值。

#### Scenario: High-confidence match players are selected

- **WHEN** 在单打上下文中处理帧或选择窗口，包含高置信度、稳定 tracklet 历史和强目标球场归属的跟踪人员
- **THEN** 后端 SHALL 最多包含 2 名该等 track 到渲染叠加帧中

- **WHEN** 在双打上下文中处理帧或选择窗口
- **THEN** 后端 SHALL 最多包含 4 名该等 track 到渲染叠加帧中

#### Scenario: Frame contains more tracked people than match participants

- **WHEN** 单打上下文中一帧包含超过 2 名符合条件的跟踪人员
- **THEN** 后端 SHALL 只保留评分最高的 2 名近端/远端目标球场球员
- **AND** 超出的人员 SHALL 被排除在渲染叠加帧之外，仅在诊断中保留

### Requirement: Participant-limited overlay labels

**FROM**: 叠加层标签限制基于固定全局配置值判定参与者数量。

**TO**: 叠加层标签的参与者上限由 `MatchAnalysisContext` 驱动。单打最多 2 个身份，双打最多 4 个身份。

系统 SHALL 支持叠加层标签包含稳定的球员身份标识，同时根据赛制限制可用身份数量。

#### Scenario: Player identity is available for frame detection

- **WHEN** 单打分析中叠加帧在球员身份分配后生成
- **THEN** 每帧最多 2 个符合条件的球员框包含 `P<player_id> / T<track_id>` 标签
- **AND** 标签应使用 `Player_1` 和 `Player_2`，不应出现 `Player_3` 或 `Player_4`

- **WHEN** 双打分析中叠加帧在球员身份分配后生成
- **THEN** 每帧最多 4 个符合条件的球员框包含身份标签

#### Scenario: More eligible tracks than match participants

- **WHEN** 单打上下文中一帧包含超过 2 名符合条件的跟踪人员
- **THEN** 后端 SHALL 将球员身份叠加层主题限制为 2 名
- **AND** 被排除的 track SHALL 仅在诊断中保留

### Requirement: 投影观测点 schema 边界语义

**FROM**: 运动指标始终假设存在 4 名球员轨迹。

**TO**: 运动指标接收赛制上下文，根据 expected_player_count 和球场投影坐标映射球员轨迹。单打场景 SHALL 只产生 2 组轨迹，双打场景产生 4 组。

#### Scenario: 单打场景轨迹

- **WHEN** 分析任务是单打
- **THEN** 球员轨迹 JSON SHALL 最多包含 2 名不同球员的轨迹
- **AND** 轨迹 artifact SHALL 包含 `match_context` 声明格式和期望人数

### ADDED Requirements

### Requirement: PrimaryPlayerSelector 生命周期对齐 tracking run

系统 SHALL 在每次 `_run_tracking` 开始时创建新的 `PrimaryPlayerSelector` 实例，而非在 Pipeline 初始化时一次性创建。

#### Scenario: 单次 tracking run 创建

- **WHEN** `_run_tracking` 开始执行
- **THEN** 一个新的 `PrimaryPlayerSelector` SHALL 被创建
- **AND** 其 `max_subjects` SHALL 来自 `MatchAnalysisContext.expected_player_count`
- **AND** 其 `group_profile` SHALL 来自 `MatchAnalysisContext.group_profile`
- **AND** 旧的 selector 实例 SHALL 不再被引用

#### Scenario: 销毁不残留

- **WHEN** `_run_tracking` 因任何原因结束（成功、失败、取消）
- **THEN** 该次创建的 selector 及其内部 `_qualities`、`_history`、诊断数据 SHALL 不再影响下一次 tracking run

### Requirement: _is_in_court_neighborhood 语义澄清

系统 SHALL 将现有方法 `_is_in_near_court_area` 重命名为 `_is_in_court_neighborhood`，避免名称中的 "near" 与近端半场概念混淆。

#### Scenario: 重命名后行为不变

- **WHEN** `_is_in_court_neighborhood(court_position, margin_ft)` 被调用
- **THEN** 其行为 SHALL 与重命名前的 `_is_in_near_court_area` 完全一致
- **AND** 检查逻辑仍为"投影坐标是否在球场矩形加指定边距范围内"

### Requirement: 统一容量校验而非静默 min

系统 SHALL 将三个独立人数配置合并为统一的 `player_analysis_hard_limit`。当配置容量低于比赛需求时，系统 SHALL 以明确错误拒绝任务，而非静默 min 降级。

#### Scenario: 容量满足需求

- **WHEN** `settings.player_analysis_hard_limit=4` 且 `match_context.expected_player_count=4`
- **THEN** `effective_player_count` SHALL 为 4
- **AND** 任务 SHALL 正常运行

#### Scenario: 容量低于需求

- **WHEN** `settings.player_analysis_hard_limit=2` 且 `match_context.expected_player_count=4`（双打）
- **THEN** Pipeline SHALL 抛 `PipelineConfigurationError`
- **AND** 错误码 SHALL 为 `PLAYER_CAPACITY_BELOW_MATCH_REQUIREMENT`
- **AND** 错误信息 SHALL 包含期望值和配置值
- **AND** 任务 SHALL NOT 被视为普通的 `player_count_mismatch`"
