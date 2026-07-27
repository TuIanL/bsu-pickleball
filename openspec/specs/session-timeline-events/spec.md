## MODIFIED Requirements

### Requirement: 查询时间线事件

**变更**：修复前端 `listTimelineEvents` 调用参数错误。

**修改前**：`useLiveCoding` 中两处调用为 `listTimelineEvents({ capture_take_id, limit: 200 } as any)`，将对象转为 URL 中的 `[object Object]`，导致初始化或刷新时无法正确恢复事件。

**修改后**：系统 SHALL 使用正确的双参数签名 `listTimelineEvents(fieldSessionId, params)` 调用。
- `capture_take_id` SHALL 作为 `params` 的字段传递，而非取代 `fieldSessionId` 位置
- `limit` 参数 SHALL 按实际 API 设计传递，不传递不支持的筛选字段

## ADDED Requirements

### Requirement: 比赛间歇原因元数据

系统 MUST 为由实时比赛编码创建的 `non_play_start` 和 `non_play_end` 事件保存结构化的间歇原因，以支持可重放状态和差异化时间线呈现。

#### Scenario: 创建赛间间歇事件
- **WHEN** `end_rally` action 关闭一个进行中的分
- **THEN** 系统 SHALL 创建 `non_play_start` 事件
- **AND** 事件的 `payload_json.intermission_kind` SHALL 为 `between_rallies`

#### Scenario: 创建暂停或换边间歇事件
- **WHEN** `start_timeout` 或 `change_side` action 开启间歇
- **THEN** 系统 SHALL 创建 `non_play_start` 事件
- **AND** 事件的 `payload_json.intermission_kind` SHALL 分别为 `timeout` 或 `side_change`

#### Scenario: 关闭间歇保留原因
- **WHEN** `start_next_rally`、开始新局或开始新盘关闭一个开启的间歇
- **THEN** 系统 SHALL 创建对应的 `non_play_end` 事件
- **AND** 事件 SHALL 携带与开启事件相同的 `intermission_kind`

#### Scenario: 兼容历史间歇事件
- **WHEN** 读取一个缺少 `payload_json.intermission_kind` 的历史 `non_play_start` 或 `non_play_end` 事件
- **THEN** 系统 SHALL 将其解释为 `between_rallies`
- **AND** 系统 SHALL 不修改该历史事件的持久化内容

### Requirement: rally_end 事件 payload schema

系统 MUST 为 `rally_result_a`、`rally_result_b`、`rally_replay` action 自动创建的 `rally_end` 事件写入结构化的回合结果数据，以支持后续统计分析和状态重放。

#### Scenario: A 方胜的 rally_end 事件
- **WHEN** 执行 `rally_result_a` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `"A"`
- **AND** `payload_json.validity` SHALL 为 `"valid"`
- **AND** `payload_json.reason` SHALL 为 `""`

#### Scenario: B 方胜的 rally_end 事件
- **WHEN** 执行 `rally_result_b` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `"B"`
- **AND** `payload_json.validity` SHALL 为 `"valid"`

#### Scenario: 重打的 rally_end 事件
- **WHEN** 执行 `rally_replay` action 后自动创建 `rally_end` 事件
- **THEN** 事件的 `payload_json.winner` SHALL 为 `null`
- **AND** `payload_json.validity` SHALL 为 `"replay"`

#### Scenario: 可选的备注字段
- **WHEN** 用户在结果 action 中通过 payload 提供了 `reason` 字段
- **THEN** 系统 SHALL 将 `reason` 写入 `rally_end` 事件的 `payload_json.reason`
- **WHEN** 未提供 `reason`
- **THEN** `payload_json.reason` SHALL 为 `""`

### Requirement: rally_end 事件不含比分

系统 MUST 确保 `rally_end` 事件不包含 `score_after` 或 `server_after` 字段。比分由 FSM 在重放时动态推演。

#### Scenario: 事件持久化不含比分
- **WHEN** `rally_end` 事件被持久化到数据库
- **THEN** `payload_json` SHALL 不包含 `score_a`、`score_b`、`score_after`、`server_after` 字段
- **AND** 这些字段 SHALL 仅存在于 `LiveCodingState` 快照中

### Requirement: score_correction 事件

系统 MUST 在用户执行 `correct_score` action 时创建一条 `score_correction` 类型的 TimelineEvent，记录修正前后的比分差值。

#### Scenario: 修正事件包含前后比分
- **WHEN** 执行 `correct_score` action
- **THEN** 系统 SHALL 创建 `event_type` 为 `score_correction` 的 `SessionTimelineEvent`
- **AND** `payload_json` SHALL 包含 `score_before`、`score_after`、`reason` 字段
- **AND** `score_before` SHALL 为修正前的 FSM 状态快照（`{a, b, server_team}`）
- **AND** `score_after` SHALL 为修正后的目标值

### Requirement: validity 合法值

系统 MUST 限制 `rally_end` 事件的 `validity` 字段值仅为 `"valid"` 和 `"replay"`。

#### Scenario: 合法值枚举
- **WHEN** `rally_end` 事件的 `validity` 不为 `"valid"` 或 `"replay"`
- **THEN** 系统 SHALL 拒绝该 action
- **AND** 系统 SHALL 返回校验错误

### Requirement: Vidat 导入事件溯源
系统 MUST 为已确认 Vidat 导入生成的时间线事件记录来源标识、标注包版本和导入版本，以支持审计和训练数据追溯。

#### Scenario: 查询导入事件
- **WHEN** 用户查询一个 CaptureTake 的时间线事件
- **THEN** 每个由 Vidat 导入生成的事件 SHALL 包含 `vidat_import` 来源和关联的标注包版本标识
- **AND** 非 Vidat 历史事件 SHALL 保持其原有来源和内容
