## MODIFIED Requirements

### Requirement: Field Session 数据模型

系统 MUST 为 Field Session 保存采集任务上下文字段。

#### Scenario: 保存完整上下文

- **WHEN** 系统保存 Field Session
- **THEN** Field Session SHALL 包含 `id`、`title`、`venue`、`court_name`、`capture_mode`、`match_format`、`camera_setup`、`display_mode`、`status`、`notes`、`started_at`、`ended_at`、`created_at` 和 `updated_at`
- **AND** `display_mode` SHALL 使用 `standard` 或 `showcase`
- **AND** 缺失历史值时 SHALL 按 `standard` 兼容读取

#### Scenario: 限制枚举值

- **WHEN** 用户提交 Field Session
- **THEN** `capture_mode` SHALL 限制为 `practice`、`match` 或 `engineering`
- **AND** `match_format` SHALL 限制为 `singles` 或 `doubles`
- **AND** `camera_setup` SHALL 限制为 `single`、`dual` 或 `debug_single`
- **AND** `display_mode` SHALL 限制为 `standard` 或 `showcase`

## ADDED Requirements

### Requirement: 创建展示采集任务

系统 SHALL 允许用户在创建 Field Session 时显式选择展示模式，并 SHALL 默认创建标准模式任务。

#### Scenario: 创建标准模式任务

- **WHEN** 用户创建 Field Session 且省略 `display_mode`
- **THEN** 系统 SHALL 将 `display_mode` 持久化为 `standard`
- **AND** 任务 SHALL 保持现有采集、预览和录制行为

#### Scenario: 创建双摄展示任务

- **WHEN** 用户创建 Field Session，设置 `display_mode=showcase` 且 `camera_setup=dual`
- **THEN** 系统 SHALL 持久化展示模式
- **AND** Field Session 详情和列表 SHALL 回显该模式

#### Scenario: 拒绝非双摄展示任务

- **WHEN** 用户创建或更新 Field Session，设置 `display_mode=showcase` 且 `camera_setup` 不是 `dual`
- **THEN** 系统 SHALL 返回可识别的校验错误
- **AND** 系统 SHALL 不创建或不保存该不一致配置

### Requirement: 展示配置在采集期间锁定

系统 SHALL 在 Field Session 进入 `live` 后锁定 `display_mode` 和 `camera_setup`，并 SHALL 将本次配置快照传递给关联 CaptureTake 或录制会话。

#### Scenario: 录制前修改展示配置

- **WHEN** Field Session 尚未进入 `live` 且用户更新 `display_mode`
- **THEN** 系统 SHALL 持久化更新后的配置
- **AND** 后续录制 SHALL 使用更新后的配置

#### Scenario: 录制期间修改展示配置

- **WHEN** Field Session 已进入 `live` 且用户尝试修改 `display_mode` 或 `camera_setup`
- **THEN** 系统 SHALL 拒绝修改
- **AND** 当前录制会话 SHALL 保持原配置

### Requirement: 控制台展示模式可见

系统 SHALL 在采集向导和采集控制台中显示当前 Field Session 的 `display_mode`，并 SHALL 在展示模式下提供展示预览入口或展示屏 URL。

#### Scenario: 展示任务进入控制台

- **WHEN** 用户打开 `display_mode=showcase` 的双摄 Field Session 控制台
- **THEN** 控制台 SHALL 显示展示模式状态
- **AND** 控制台 SHALL 提供启动录制后打开或复制展示屏入口的操作

#### Scenario: 标准任务进入控制台

- **WHEN** 用户打开 `display_mode=standard` 的 Field Session 控制台
- **THEN** 控制台 SHALL 保留现有普通预览和录制操作
- **AND** 控制台 SHALL 不请求展示专用流
