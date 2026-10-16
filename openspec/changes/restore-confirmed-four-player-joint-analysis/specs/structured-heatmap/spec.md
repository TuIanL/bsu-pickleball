## MODIFIED Requirements

### Requirement: 系统暴露结构化热力图数据

后端 SHALL 在 `/api/analysis/jobs/{job_id}/visualization-data` 端点中返回热力图结构化数据，包含 22 行 × 10 列的合并网格计数、最大计数值、球场几何信息，以及已由冻结名册审计确认的每名球员独立网格与展示标签。每个 `heatmaps.players` 元素的 `id` SHALL 为已确认的 canonical `Player_N`，`label` SHALL 为对应 P1..P4；未确认观测 MUST NOT 归入带 P 标签的个人网格。双打 Job SHALL 另提供四个冻结槽位的 `identity_slots` 状态、可用样本数和缺失/未确认原因，使页面能区分“没有识别到人”和“看到了人但无法确认是谁”。匿名有效观测可用于明确标注来源的合并图，MUST NOT 伪装成四人正式热力图。

#### Scenario: 四人均已确认且有有效轨迹

- **WHEN** 分析任务完成，四个 P 身份均通过审计，且 `PositionVisualizer` 已生成 22×10 网格数据
- **THEN** `/visualization-data` 的 `heatmaps.visual_grid` SHALL 包含 `rows: 22`、`cols: 10`、`max_count` 与 `cells: [{row, col, count}]`
- **AND** `heatmaps.players` SHALL 含四名球员各自的 `id`、`label`、`color` 与独立 `grid`
- **AND** `identity_slots` SHALL 显示四人已确认及各自覆盖情况

#### Scenario: 只有两条未确认轨迹

- **WHEN** 双打任务只有两条 metric-eligible 轨迹且其 P 映射均未确认
- **THEN** `heatmaps.players` SHALL 不把它们命名为 P2/P3
- **AND** `identity_slots` SHALL 列出 P1–P4 的未确认或缺失原因及感知样本情况
- **AND** 页面 SHALL 显示四人识别质量不足

#### Scenario: 无可用坐标点时返回空网格

- **WHEN** 球员轨迹数据中无有效坐标点
- **THEN** `heatmaps.visual_grid.cells` 为空数组、`max_count` 为 0，`heatmaps.players` 为空数组
- **AND** 已冻结的身份槽位 SHALL 仍以缺失状态返回

#### Scenario: 球员网格各自归一化计数

- **WHEN** 构建已确认球员的独立网格
- **THEN** 每名球员的 `grid.max_count` SHALL 使用该球员自身的最大格计数，而非合并网格的全局峰值

#### Scenario: 覆盖率门槛与身份状态口径冲突

- **WHEN** 某 P 槽位的覆盖率门槛判定为通过，而身份审计对同一槽位给出未确认结论
- **THEN** 该球员 SHALL NOT 出现在 `heatmaps.players` 的个人图层中
- **AND** `identity_slots` SHALL 显示其未确认及原因，且已确认有效点为 0
- **AND** 页面 MUST NOT 同时呈现该 P 的个人热力图与「未确认」状态卡

#### Scenario: 个人图层与状态卡共用同一映射

- **WHEN** 页面渲染个人热力图、散点图、位置指标与逐槽位状态卡
- **THEN** 四者 SHALL 消费同一份 `global_player_id → frozen P` 确认映射
- **AND** 任一处判定未确认时，其他各处 SHALL NOT 呈现该 P 的个人图层或 Team 指标
- **AND** 映射来源 SHALL 在产物中标明，冲突时以身份审计为准
