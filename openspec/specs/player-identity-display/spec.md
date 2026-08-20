# player-identity-display Specification

## Purpose

用户可见输出（视频检测叠加、球场 minimap、轨迹详情页、报告）只呈现 canonical player ID（`1`–`4`），原始 tracker `track_id` 不得出现在任何面向用户的 API 字段或文案中。

## Requirements

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
### Requirement: 软接管产生的临时身份显示 canonical 标签

视频检测叠加层对经 lock hint 或位置连续性软接管获得身份的检测框 SHALL 显示对应的 canonical player ID（如 `P1`），不得因 `tentative` 或低置信度而降级为 `person`。仅当检测框在当前帧确实没有可证明的 `player_id` 时，标签 SHALL 显示中性文本。

#### Scenario: 软接管身份的检测显示 canonical ID

- **WHEN** 一个检测框的 `player_id` 由身份层软接管指派为 `Player_2`
- **THEN** 框标签 SHALL 显示 `P2`
- **AND** SHALL NOT 因 `tracking_status="tentative"` 显示 `person`

#### Scenario: lock hint 恢复身份的检测显示 canonical ID

- **WHEN** 一个新 track 由 lock hint 指派到 `Player_3`
- **THEN** 框标签 SHALL 显示 `P3`
- **AND** 标签 SHALL NOT 显示原始 `track_id`

#### Scenario: 完全未关联的检测仍显示中性文本

- **WHEN** 一个检测框 `player_id` 为空且 soft takeover 不适用
- **THEN** 框标签 SHALL 显示 `person`
- **AND** SHALL NOT 显示 `ID {track_id}` 形式的原始数字

### Requirement: 相邻 overlay 帧保持可证明的 canonical 身份

前端 overlay 帧解析在相邻帧之间插值时 SHALL 保留或继承可证明的 canonical player identity，但 SHALL NOT 根据不同 track 的空间距离自行猜测身份。

#### Scenario: 同一 track 的下一帧恢复身份

- **WHEN** 当前 overlay 帧的 detection 与下一 overlay 帧使用相同 `track_id`
- **AND** 当前帧 `player_id` 为空而下一帧为 `Player_1`
- **THEN** 插值后的当前渲染 detection SHALL 使用 `Player_1`
- **AND** 标签 SHALL 显示 `P1` 而不是 `person`

#### Scenario: 不同 track 不由前端猜测身份

- **WHEN** 当前帧和下一帧的 track_id 不同
- **AND** 后端没有为下一 track 提供 `player_id`
- **THEN** 前端 SHALL NOT 仅凭空间距离将其标为某个 P ID
- **AND** SHALL 保留中性标签或等待后端身份数据

#### Scenario: canonical ID 不泄漏 raw track_id

- **WHEN** overlay detection 同时包含 `player_id` 和 `track_id`
- **THEN** 用户可见标签 SHALL 只显示 `P1`..`P4`
- **AND** SHALL NOT 显示 raw `track_id`

### Requirement: 结构化可视化产物使用 canonical player ID 与展示标签

后端 `/visualization-data` 中的 `heatmaps.players`、`scatter_plots.players`、`zone_stats.players`、`player_trajectories` 球员标识字段 SHALL 使用 canonical player ID（`Player_1`..`Player_4`），展示标签 SHALL 为 `P1`..`P4`；SHALL NOT 使用排序索引（如 `"0"`）或 `"球员N"` 形式作为标识或标签。

#### Scenario: 热力图球员 id 为 canonical

- **WHEN** 分析完成生成 heatmaps 结构化数据
- **THEN** `heatmaps.players[].id` SHALL 为 canonical player ID（如 `Player_2`）
- **AND** `heatmaps.players[].label` SHALL 为 `P2`（或等价 canonical 形式）

#### Scenario: zone_stats 球员 id 为 canonical

- **WHEN** 分析完成生成 zone_stats 结构化数据
- **THEN** `zone_stats.players[].id` SHALL 为 canonical player ID（如 `Player_1`）
- **AND** `zone_stats.players[].label` SHALL 为 `P1`（或等价 canonical 形式）

#### Scenario: 散点图球员 id 为 canonical

- **WHEN** 分析完成生成 scatter_plots 结构化数据
- **THEN** `scatter_plots.players[].id` SHALL 为 canonical player ID（如 `Player_3`）

#### Scenario: 非 canonical 标签不参与对齐声明

- **WHEN** 某球员点 label 无法解析为 `Player_N` 形式
- **THEN** 该 id 原样保留且颜色回退索引分配
- **AND** 该产物不声称与 canonical P1-P4 对齐

### Requirement: playerMarkers 的 team 字段按 canonical 槽位语义赋值

球场 minimap 与报告的 `playerMarkers[].team` 字段 SHALL 按 canonical `Player_N` 槽位语义赋值，MUST NOT 按遍历顺序或 `latest.entries()` 的插入顺序赋值。双打模式：`Player_1`/`Player_2` SHALL 为 `near`，`Player_3`/`Player_4` SHALL 为 `far`；单打模式：`Player_1` SHALL 为 `near`，`Player_2` SHALL 为 `far`。该语义 SHALL 与 `player-lock-state-machine` 的槽位位置语义一致。

#### Scenario: 双打 markers 按编号分侧

- **WHEN** 双打分析产出 `Player_1`、`Player_2`、`Player_3`、`Player_4` 四条轨迹
- **THEN** `playerMarkers` 中 `Player_1`/`Player_2` 的 `team` SHALL 为 `near`
- **AND** `Player_3`/`Player_4` 的 `team` SHALL 为 `far`
- **AND** 任何遍历顺序变化都 SHALL NOT 改变该赋值

#### Scenario: 单打 markers 按编号分侧

- **WHEN** 单打分析产出 `Player_1`、`Player_2` 两条轨迹
- **THEN** `Player_1` 的 `team` SHALL 为 `near`
- **AND** `Player_2` 的 `team` SHALL 为 `far`

#### Scenario: 非 canonical track_id 不猜侧

- **WHEN** `playerMarkers` 输入中存在无法解析为 `Player_N` 的 track_id（如 `global_player_1` 或 `candidate_3`）
- **THEN** 该 marker 的 `team` SHALL 回退为按 `court_point.y`（近半场 `y < 22ft` → near）推断或 `unknown`
- **AND** SHALL NOT 抛出异常或产出错误的 near/far

### Requirement: playerMarkers 与 A-D 标签按数字序稳定

`playerMarkers` 数组 SHALL 按 canonical `Player_N` 数字升序排列，使 label A-D 稳定对应 P1-P4（A=Player_1, B=Player_2, C=Player_3, D=Player_4）。该排序 SHALL 在前后端（`src/services/pipelineReportAdapter.ts` 与 `backend/app/services/mock_analysis.py`）一致实现。

#### Scenario: 后端 tracks 顺序变化不影响 markers 顺序

- **WHEN** 后端 `tracks` 数组顺序为 `Player_2, Player_4, Player_1, Player_3`
- **THEN** 生成的 `playerMarkers` SHALL 仍按 `Player_1, Player_2, Player_3, Player_4` 排序
- **AND** label SHALL 依次为 A、B、C、D

