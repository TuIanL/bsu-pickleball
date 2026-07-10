## MODIFIED Requirements

### Requirement: Session Timeline Event 数据模型

系统 MUST 为 Field Session 保存可对齐视频的时间线事件。

#### Scenario: 保存完整事件字段

- **WHEN** 系统持久化一个 Session Timeline Event
- **THEN** 事件 SHALL 包含 `id`、`field_session_id`、`capture_take_id`、`recording_session_id`、`timestamp_ms`、`occurred_at`、`event_type`、`source`、`label`、`note`、`payload_json`、`is_undone`、`created_at` 和 `updated_at`
- **AND** `is_undone` SHALL 默认为 false
- **AND** `field_session_id` SHALL 引用已存在的 Field Session
- **AND** `capture_take_id` SHALL 允许为空（兼容旧数据）
- **AND** `recording_session_id` SHALL 允许为空

#### Scenario: 限制事件枚举值

- **WHEN** 用户提交 Session Timeline Event
- **THEN** `event_type` SHALL 限制为 `session_note`、`non_play_start`、`non_play_end`、`game_start`、`game_end`、`set_start`、`set_end`、`rally_start`、`rally_end`、`score_update`、`score_correction`、`side_change`、`timeout_start`、`timeout_end`、`drill_start`、`drill_end` 或 `custom_marker`
- **AND** `source` SHALL 限制为 `manual`、`algorithm` 或 `corrected`

#### Scenario: 保存结构化 payload

- **WHEN** 用户提交包含比分、局数、发球方、换边原因或备注文本的事件
- **THEN** 系统 SHALL 将这些扩展信息保存到 `payload_json`
- **AND** 系统 SHALL 在读取事件时原样返回 `payload_json`

### Requirement: 创建时间线事件

系统 MUST 允许用户在 Field Session 下创建时间线事件。

#### Scenario: 为存在的 Field Session 创建人工事件

- **WHEN** 用户请求 `POST /api/field-sessions/{field_session_id}/timeline-events`，并提交合法的事件类型、source、时间戳和 payload
- **THEN** 系统 SHALL 创建关联该 Field Session 的 Session Timeline Event
- **AND** 响应 SHALL 包含事件 id、Field Session id、时间戳、事件类型、source、label、note、payload 和时间字段

#### Scenario: 拒绝不存在的 Field Session

- **WHEN** 用户请求为不存在的 Field Session 创建时间线事件
- **THEN** 系统 SHALL 返回 404
- **AND** 系统 SHALL 不创建 Session Timeline Event

#### Scenario: 校验录制归属

- **WHEN** 用户创建事件时提供 `recording_session_id`
- **THEN** 系统 SHALL 校验该 RecordingSession 存在
- **AND** 系统 SHALL 校验该 RecordingSession 的 `field_session_id` 等于请求路径中的 Field Session id
- **AND** 如果校验失败，系统 SHALL 返回 400 或 404

#### Scenario: 校验 CaptureTake 归属

- **WHEN** 用户创建事件时提供 `capture_take_id`
- **THEN** 系统 SHALL 校验该 CaptureTake 存在
- **AND** 系统 SHALL 校验该 CaptureTake 的 `field_session_id` 等于请求路径中的 Field Session id
- **AND** 如果校验失败，系统 SHALL 返回 400 或 404

### Requirement: 时间戳计算策略

系统 MUST 为时间线事件保存可用于视频分析的 `timestamp_ms`。

#### Scenario: 使用前端提交的时间戳

- **WHEN** 用户创建或更新事件时显式提交 `timestamp_ms`
- **THEN** 系统 SHALL 使用该 `timestamp_ms`
- **AND** `timestamp_ms` SHALL 大于或等于 0

#### Scenario: 录制中事件缺省时间戳兜底

- **WHEN** 用户创建事件时未提交 `timestamp_ms`，但提供了有效的 `capture_take_id`
- **THEN** 系统 SHALL 根据 CaptureTake 的 `started_at` 和当前时间计算 `timestamp_ms`
- **AND** 响应 SHALL 返回最终保存的 `timestamp_ms`

#### Scenario: 兼容旧录制会话时间戳

- **WHEN** 用户创建事件时未提交 `timestamp_ms`，且未提供 `capture_take_id`，但提供了 `recording_session_id`
- **THEN** 系统 SHALL 根据 RecordingSession 的 `started_at` 和当前时间计算 `timestamp_ms`
- **AND** 系统 SHALL 尝试适配对应的 CaptureTake

#### Scenario: 无录制事件缺省为任务级备注

- **WHEN** 用户创建事件时未提交 `timestamp_ms` 且未提供 `capture_take_id` 和 `recording_session_id`
- **THEN** 系统 SHALL 将 `timestamp_ms` 保存为 0

#### Scenario: 拒绝负时间戳

- **WHEN** 用户提交小于 0 的 `timestamp_ms`
- **THEN** 系统 SHALL 返回校验错误
- **AND** 系统 SHALL 不创建或更新该事件

### Requirement: 查询时间线事件

系统 MUST 允许用户查询 Field Session 下的时间线事件。

#### Scenario: 列出 Field Session 事件

- **WHEN** 用户请求 `GET /api/field-sessions/{field_session_id}/timeline-events`
- **THEN** 系统 SHALL 返回该 Field Session 的事件列表
- **AND** 列表 SHALL 按 `timestamp_ms ASC`、`created_at ASC` 排序

#### Scenario: 按类型和来源筛选

- **WHEN** 用户请求事件列表时提供 `event_type` 或 `source` 查询参数
- **THEN** 系统 SHALL 只返回匹配类型或来源的事件

#### Scenario: 按 CaptureTake 筛选

- **WHEN** 用户请求事件列表时提供 `capture_take_id` 查询参数
- **THEN** 系统 SHALL 只返回关联该 CaptureTake 的事件

#### Scenario: 按录制会话筛选（兼容）

- **WHEN** 用户请求事件列表时提供 `recording_session_id` 查询参数
- **THEN** 系统 SHALL 只返回关联该 RecordingSession 的事件
- **AND** 系统 SHALL 同时返回通过 CaptureTake 适配的事件

#### Scenario: 按时间范围筛选

- **WHEN** 用户请求事件列表时提供 `from_ms` 或 `to_ms` 查询参数
- **THEN** 系统 SHALL 只返回 `timestamp_ms` 位于指定范围内的事件

#### Scenario: 查询不存在的 Field Session

- **WHEN** 用户请求不存在 Field Session 的时间线事件
- **THEN** 系统 SHALL 返回 404

### Requirement: 更新时间线事件

系统 MUST 允许用户编辑已存在的时间线事件。

#### Scenario: 更新事件内容

- **WHEN** 用户请求 `PATCH /api/timeline-events/{event_id}`，并提交新的 `timestamp_ms`、`event_type`、`source`、`label`、`note` 或 `payload_json`
- **THEN** 系统 SHALL 更新该事件的可编辑字段
- **AND** 系统 SHALL 更新 `updated_at`
- **AND** 响应 SHALL 返回更新后的事件

#### Scenario: 不允许变更事件归属

- **WHEN** 用户更新事件时提交 `field_session_id`、`capture_take_id`、`recording_session_id`、`id`、`created_at` 或 `updated_at`
- **THEN** 系统 SHALL 忽略这些归属和系统字段，或返回校验错误
- **AND** 已存在事件的 Field Session 归属 SHALL 保持不变

#### Scenario: 更新不存在的事件

- **WHEN** 用户请求更新不存在的事件 id
- **THEN** 系统 SHALL 返回 404

### Requirement: 删除时间线事件

系统 MUST 允许用户删除已存在的时间线事件。

#### Scenario: 删除存在的事件

- **WHEN** 用户请求 `DELETE /api/timeline-events/{event_id}`
- **THEN** 系统 SHALL 删除该 Session Timeline Event
- **AND** 后续读取该 Field Session 的事件列表 SHALL 不再包含该事件

#### Scenario: 删除不存在的事件

- **WHEN** 用户请求删除不存在的事件 id
- **THEN** 系统 SHALL 返回 404

### Requirement: Field Session 控制台人工打点体验

系统 MUST 在 Field Session 采集控制台提供人工记录时间线事件的操作界面。

#### Scenario: 录制中快捷打点

- **WHEN** 用户选择 Field Session 且存在关联该 Field Session 的录制中 CaptureTake
- **THEN** 前端 SHALL 展示人工事件快捷按钮
- **AND** 用户点击快捷按钮后前端 SHALL 创建包含当前 `capture_take_id` 和当前 `timestamp_ms` 的时间线事件

#### Scenario: 比赛模式快捷动作

- **WHEN** Field Session 的 `capture_mode` 为 `match`
- **THEN** 前端 SHALL 提供盘开始/结束、局开始/结束、下一分、比分更新、比分修正、换边、非比赛开始/结束、暂停和备注相关操作

#### Scenario: 练习模式快捷动作

- **WHEN** Field Session 的 `capture_mode` 为 `practice`
- **THEN** 前端 SHALL 提供练习开始/结束、非练习时间开始/结束、重点片段和备注相关操作

#### Scenario: 工程模式快捷动作

- **WHEN** Field Session 的 `capture_mode` 为 `engineering`
- **THEN** 前端 SHALL 提供画面异常、模型误检、遮挡严重、重点调试片段和备注相关操作

#### Scenario: 展示和编辑事件列表

- **WHEN** 用户选择 Field Session
- **THEN** 前端 SHALL 展示该 Field Session 的时间线事件列表
- **AND** 用户 SHALL 能编辑事件备注、label、时间戳和 payload
- **AND** 用户 SHALL 能删除事件

## ADDED Requirements

### Requirement: 事件通过 coding-actions 创建

系统 MUST 支持通过 coding-actions 语义命令创建事件。

#### Scenario: coding-actions 创建事件

- **WHEN** 用户通过 `POST /api/capture-takes/{id}/coding-actions` 执行操作
- **THEN** 系统 SHALL 在事务中创建事件
- **AND** 事件 SHALL 自动关联 CaptureTake
- **AND** 事件 SHALL 自动计算 timestamp_ms

#### Scenario: 事件携带 client_action_id

- **WHEN** 通过 coding-actions 创建事件
- **THEN** 事件 SHALL 携带 `client_action_id`
- **AND** 系统 SHALL 使用该 ID 实现幂等性

### Requirement: 事件标记 is_undone 状态

系统 MUST 支持通过 `is_undone` 字段标记被撤销的事件。

#### Scenario: 撤销事件设置 is_undone

- **WHEN** 执行 undo 操作
- **THEN** 系统 SHALL 将被撤销的事件 `is_undone` 设置为 true
- **AND** 系统 SHALL 保留 undo action 对应的 CaptureCodingAction 记录
- **AND** 系统 SHALL 不删除被撤销的事件
- **AND** 后续查询 SHALL 默认不返回 is_undone 事件

#### Scenario: 查询包含 is_undone 事件

- **WHEN** 用户请求事件列表时提供 `include_undone=true` 参数
- **THEN** 系统 SHALL 返回包含 is_undone 事件的列表

### Requirement: Event Service 事务边界重构

系统 MUST 将 timeline_event_service 重构为内部方法 + 外部事务控制两层结构。

#### Scenario: 内部方法不提交事务

- **WHEN** 通过 coding-actions 内部调用事件创建方法
- **THEN** 系统 SHALL 提供 `_add_timeline_event()` 内部方法
- **AND** 该方法 SHALL 执行 `db.add()` 和 `db.flush()`，但不执行 `db.commit()`

#### Scenario: 外部 API 方法负责事务

- **WHEN** 通过旧 API `POST /api/field-sessions/{id}/timeline-events` 创建事件
- **THEN** 系统 SHALL 在 `create_timeline_event()` 方法内使用 `with db.begin()` 管理事务
- **AND** 内部调用 `_add_timeline_event()`

#### Scenario: coding-actions 统一事务控制

- **WHEN** coding-actions handler 创建事件
- **THEN** 系统 SHALL 在一个 `with db.begin()` 内调用多个内部方法
- **AND** 所有操作（action log、events、segments、state）共享同一个事务
- **AND** 事务最外层只调用一次 `commit()`
