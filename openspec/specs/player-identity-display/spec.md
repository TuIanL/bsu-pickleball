# player-identity-display Specification

## Purpose

用户可见输出（视频检测叠加、球场 minimap、轨迹详情页、报告）只呈现 canonical player ID（`1`–`4`），原始 tracker `track_id` 不得出现在任何面向用户的 API 字段或文案中。

## ADDED Requirements

### Requirement: 视频检测叠加使用 canonical player ID

视频叠加层（`VideoAnalysisCard`）对每个检测框的标签 SHALL 显示 canonical player ID（如 `P1`），不得显示原始 `track_id`。

#### Scenario: 已关联身份的检测显示 canonical ID

- **WHEN** 一个检测框已关联到 `Player_2`
- **THEN** 框标签 SHALL 显示 `P2`（或等价 canonical 形式）
- **AND** 标签 SHALL NOT 包含原始 `track_id` 数字

#### Scenario: 未关联身份的检测不显示原始 track_id

- **WHEN** 一个检测框尚未关联到任何身份（`player_id` 为空）
- **THEN** 框标签 SHALL 显示中性文本（如 `person`）
- **AND** 标签 SHALL NOT 显示 `ID {track_id}` 形式的原始数字

### Requirement: 球场 minimap 使用 canonical player ID

球场 minimap（`CourtMinimap`）轨迹点的分组键与标签 SHALL 使用 canonical player ID，不得按原始 `track_id` 分组或标注。

#### Scenario: minimap 标签显示 canonical ID

- **WHEN** 一条轨迹属于 `Player_3`
- **THEN** minimap 上该轨迹的最新点标签 SHALL 为 `P3`（或等价 canonical 形式）
- **AND** SHALL NOT 显示 `ID` 加原始 `track_id` 片段

#### Scenario: minimap 按身份分组而非按 track 分组

- **WHEN** 同一球员跨多个 source `track_id` 出现
- **THEN** minimap SHALL 把所有这些点归为同一身份分组绘制
- **AND** 同一身份 SHALL 只使用一种标签

### Requirement: 轨迹详情页使用 canonical player ID

轨迹详情页（`AnalysisDetailsPage`）的轨迹摘要、点位检查等展示 SHALL 使用 canonical player ID，不再展示"原始 ID"形式的 raw `track_id`。

#### Scenario: 轨迹摘要显示 canonical ID

- **WHEN** 展示一条轨迹摘要
- **THEN** 摘要标签 SHALL 为 canonical player ID（如 `P1`）
- **AND** 不显示形如 `原始 ID：164` 的原始 `track_id`

#### Scenario: 短片段归属 canonical 身份

- **WHEN** 一条短轨迹片段由同一球员的某个 source `track_id` 生成
- **THEN** 该片段 SHALL 归属到对应的 canonical player ID 展示
- **AND** 片段说明不得引用原始 `track_id`

### Requirement: 面向用户的 API 字段只含 canonical player ID

后端面向用户的分析产物（轨迹、检测叠加、渲染轨迹、报告）中，球员标识字段 SHALL 只取 canonical player ID（`Player_1`..`Player_4`），对应对外展示整数 `1`–`4`；原始 `track_id` 仅允许出现在内部调试产物（projection debug、诊断 `history_track_ids`）中。

#### Scenario: 轨迹产物只含 canonical ID

- **WHEN** 分析完成生成 `player_render_trajectory` 或 trajectory artifact
- **THEN** 其中的球员标识字段 SHALL 均为 canonical player ID
- **AND** SHALL NOT 出现原始 `track_id` 作为身份标识

#### Scenario: 检测叠加字段区分身份与内部 track

- **WHEN** `FrameDetection` 同时携带 `player_id` 与 `track_id`
- **THEN** `player_id` SHALL 为 canonical player ID
- **AND** `track_id` SHALL 被标记为内部字段，前端默认不渲染

#### Scenario: 报告指标以身份维度聚合

- **WHEN** 报告或 metrics 按球员聚合
- **THEN** 聚合键 SHALL 为 canonical player ID（`1`–`4`）
- **AND** SHALL NOT 泄漏原始 `track_id` 到指标标签
## Requirements
### Requirement: 软接管产生的临时身份显示 canonical 标签

视频检测叠加层（`VideoAnalysisCard`）对经位置连续性软接管获得身份的检测框 SHALL 显示对应的 canonical player ID（如 `P1`），不得因置信度低而降级为 `person`。仅当检测框的 `player_id` 完全为空（软接管也不适用）时，标签 SHALL 显示中性文本（如 `person`）。

#### Scenario: 软接管身份的检测显示 canonical ID

- **WHEN** 一个检测框的 `player_id` 由身份层软接管（`tracking_status="tentative"`）指派为 `Player_2`
- **THEN** 框标签 SHALL 显示 `P2`（或等价 canonical 形式）
- **AND** SHALL NOT 因低置信度而显示 `person` 或原始 `track_id`

#### Scenario: 完全未关联的检测仍显示中性文本

- **WHEN** 一个检测框 `player_id` 为空，且位置连续性软接管不适用
- **THEN** 框标签 SHALL 显示中性文本（如 `person`）
- **AND** SHALL NOT 显示 `ID {track_id}` 形式的原始数字

