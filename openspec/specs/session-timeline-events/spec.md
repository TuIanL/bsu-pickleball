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
