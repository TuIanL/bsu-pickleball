# field-sessions Specification

## Purpose
Define Field Session as the top-level court-side capture task context for grouping venue, court, capture mode, match format, camera setup, recording sessions, and future capture artifacts.
## Requirements
### Requirement: 创建 Field Session

系统 MUST 允许用户创建 Field Session，作为一次真实球场采集任务的顶层容器。

#### Scenario: 创建自由练习双打采集任务
- **WHEN** 用户提交 Field Session，包含 `title`、`court_name`、`capture_mode` 为 `practice`、`match_format` 为 `doubles`、`camera_setup` 为 `single`
- **THEN** 系统 SHALL 持久化该 Field Session
- **AND** Field Session 的 `status` SHALL 为 `planned`
- **AND** 响应 SHALL 包含 Field Session id、上下文字段和时间戳

#### Scenario: 使用默认状态创建任务
- **WHEN** 用户创建 Field Session 且未提供状态
- **THEN** 系统 SHALL 将状态设置为 `planned`
- **AND** `started_at` 和 `ended_at` SHALL 为空

### Requirement: Field Session 数据模型

系统 MUST 为 Field Session 保存采集任务上下文字段。

#### Scenario: 保存完整上下文
- **WHEN** 系统保存 Field Session
- **THEN** Field Session SHALL 包含 `id`、`title`、`venue`、`court_name`、`capture_mode`、`match_format`、`camera_setup`、`status`、`notes`、`started_at`、`ended_at`、`created_at` 和 `updated_at`

#### Scenario: 限制枚举值
- **WHEN** 用户提交 Field Session
- **THEN** `capture_mode` SHALL 限制为 `practice`、`match` 或 `engineering`
- **AND** `match_format` SHALL 限制为 `singles` 或 `doubles`
- **AND** `camera_setup` SHALL 限制为 `single`、`dual` 或 `debug_single`

### Requirement: 查询 Field Session

系统 MUST 允许用户列出和读取 Field Session。

#### Scenario: 列出最近任务
- **WHEN** 用户请求 `GET /api/field-sessions`
- **THEN** 系统 SHALL 返回 Field Session 列表
- **AND** 列表 SHALL 按创建时间倒序排列

#### Scenario: 按状态筛选任务
- **WHEN** 用户请求 `GET /api/field-sessions?status=live`
- **THEN** 系统 SHALL 只返回 `status` 为 `live` 的 Field Session

#### Scenario: 读取单个任务
- **WHEN** 用户请求存在的 Field Session id
- **THEN** 系统 SHALL 返回该 Field Session 的上下文、状态、时间戳和备注

#### Scenario: 读取不存在的任务
- **WHEN** 用户请求不存在的 Field Session id
- **THEN** 系统 SHALL 返回 404

### Requirement: 更新 Field Session 元数据

系统 MUST 允许用户更新 Field Session 的可编辑元数据。

#### Scenario: 更新备注
- **WHEN** 用户更新 Field Session 的 `notes`
- **THEN** 系统 SHALL 持久化新的备注
- **AND** 系统 SHALL 更新 `updated_at`
- **AND** Field Session 状态 SHALL 保持不变

#### Scenario: 更新任务名称和场地
- **WHEN** 用户更新 Field Session 的 `title`、`venue` 或 `court_name`
- **THEN** 系统 SHALL 持久化新的元数据
- **AND** 系统 SHALL 不修改已存在 RecordingSession 的录制字段

### Requirement: Field Session 状态流转

系统 MUST 通过专门 API 控制 Field Session 的状态流转。

#### Scenario: 开始计划任务
- **WHEN** 用户请求开始 `status` 为 `planned` 的 Field Session
- **THEN** 系统 SHALL 将状态改为 `live`
- **AND** 系统 SHALL 设置 `started_at`

#### Scenario: 完成进行中任务
- **WHEN** 用户请求完成 `status` 为 `live` 的 Field Session
- **THEN** 系统 SHALL 将状态改为 `completed`
- **AND** 系统 SHALL 设置 `ended_at`

#### Scenario: 完成计划任务
- **WHEN** 用户请求完成 `status` 为 `planned` 的 Field Session
- **THEN** 系统 SHALL 将状态改为 `completed`
- **AND** 系统 SHALL 设置 `ended_at`

#### Scenario: 归档已完成任务
- **WHEN** 用户请求归档 `status` 为 `completed` 的 Field Session
- **THEN** 系统 SHALL 将状态改为 `archived`

#### Scenario: 拒绝非法状态流转
- **WHEN** 用户请求不被允许的 Field Session 状态流转
- **THEN** 系统 SHALL 返回 400
- **AND** Field Session SHALL 保持原状态

### Requirement: 删除 Field Session

系统 MUST 允许用户删除没有录制关联、没有时间线事件且不在进行中的 Field Session。

#### Scenario: 删除空采集任务
- **WHEN** 用户请求删除一个不存在录制关联、不存在时间线事件且 `status` 不是 `live` 的 Field Session
- **THEN** 系统 SHALL 删除该 Field Session
- **AND** 后续读取该 Field Session SHALL 返回 404

#### Scenario: 拒绝删除进行中任务
- **WHEN** 用户请求删除 `status` 为 `live` 的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

#### Scenario: 拒绝删除已有录制的任务
- **WHEN** 用户请求删除已经被 RecordingSession 引用的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

#### Scenario: 拒绝删除已有时间线事件的任务
- **WHEN** 用户请求删除已经包含 Session Timeline Event 的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

### Requirement: Field Session 采集控制台

系统 MUST 提供字段采集控制台，通过 `/capture/:id` 路由访问，按照「左预览、右控制、下事件标记和时间线」的布局组织摄像头预览、录制控制、场边事件标记和时间线功能。

#### Scenario: 创建后进入控制台
- **WHEN** 用户在三步向导中成功创建 Field Session
- **THEN** 前端 SHALL 自动导航到 `/capture/:id` 采集控制台
- **AND** 控制台 SHALL 展示任务名称、状态、采集模式、比赛形式、摄像头方案和场地信息
- **AND** 控制台按「左预览、右控制、下事件标记和时间线」布局渲染

#### Scenario: 在控制台复用摄像头能力
- **WHEN** 用户进入 Field Session 采集控制台
- **THEN** 前端 SHALL 保留摄像头预览、录制控制能力
- **AND** 摄像头列表 SHALL 通过设备抽屉访问，不直接展示在主界面
- **AND** 控制台设备状态区 SHALL 仅显示当前采集方案使用的摄像头
- **AND** 开始录制时 SHALL 将当前 Field Session id 传给后端

#### Scenario: 在控制台操作时间线事件
- **WHEN** 用户进入 Field Session 采集控制台且录制状态为 recording
- **THEN** 前端 SHALL 加载并展示该 Field Session 的 Session Timeline Event 列表
- **AND** 控制台 SHALL 提供场边事件快捷标记按钮（按 capture_mode 分类）
- **AND** 新事件 SHALL 实时追加到时间线末尾

#### Scenario: 录制完成展示面板
- **WHEN** 用户停止录制
- **THEN** 前端 SHALL 展示录制完成面板
- **AND** 面板内容根据向导中的分析设置（自动分析 / 再决定 / 仅保存）展示对应操作选项
- **AND** 面板可关闭，关闭后恢复到控制台预览状态

### Requirement: CaptureHomePage 提供删除采集任务入口

系统 MUST 在 `/capture` 页面的每张采集任务卡片上提供删除按钮。

#### Scenario: 卡片上显示删除按钮

- **WHEN** 用户浏览采集任务列表
- **THEN** 每张采集任务卡片 MUST 包含一个删除按钮（图标 + 文字）
- **AND** 删除按钮点击时 MUST 弹出确认对话框

#### Scenario: 点击删除按钮弹出确认

- **WHEN** 用户点击采集任务卡片上的删除按钮
- **THEN** 前端 MUST 弹出 `window.confirm` 对话框，包含任务标题
- **AND** 点击取消 SHALL 不执行任何操作

#### Scenario: 确认删除并成功

- **WHEN** 用户在确认对话框中点击「确定」
- **AND** 后端返回 `{ status: "deleted" }`
- **THEN** 前端 SHALL 从列表中移除该任务
- **AND** 前端 SHALL 自动刷新列表

#### Scenario: 确认删除但被阻止

- **WHEN** 用户在确认对话框中点击「确定」
- **AND** 后端返回 `{ status: "blocked", detail: "..." }`
- **THEN** 前端 SHOULD 展示阻止原因提示

#### Scenario: 删除操作不触发导航

- **WHEN** 用户点击删除按钮
- **THEN** 点击事件 MUST NOT 触发卡片本身的导航行为

### Requirement: FieldSessionGroupCard 提供删除采集任务入口

系统 MUST 在 `/tasks` 页面的「录制视频」Tab 中，为每个 `FieldSessionGroupCard` 提供删除当前采集任务的入口。

#### Scenario: 分组卡片头部显示删除按钮

- **WHEN** 用户浏览「录制视频」任务列表
- **THEN** 每个 `FieldSessionGroupCard` 头部 SHOULD 包含一个删除按钮
- **AND** 删除按钮仅对非 `live` 状态的采集任务可见
- **AND** 点击删除按钮 MUST 弹出确认对话框

#### Scenario: 删除按钮点击确认

- **WHEN** 用户点击 `FieldSessionGroupCard` 头部的删除按钮
- **THEN** 前端 MUST 弹出 `window.confirm` 对话框
- **AND** 确认后调用 `deleteFieldSession(id)` API
- **AND** 成功后 MUST 刷新录制列表和采集任务列表

#### Scenario: 确认删除但被阻止

- **WHEN** 用户确认删除一个有录制关联的采集任务
- **AND** 后端返回 `{ status: "blocked", detail: "..." }`
- **THEN** 前端 SHOULD 展示阻止原因提示

### Requirement: 删除确认对话框

系统 MUST 在删除前弹出确认对话框，避免误操作。

#### Scenario: 确认对话框内容

- **WHEN** 前端弹出确认对话框
- **THEN** 对话框文本 MUST 包含采集任务标题或 ID
- **AND** 对话框文本 SHOULD 提示已有录制/事件的任务会被保护
