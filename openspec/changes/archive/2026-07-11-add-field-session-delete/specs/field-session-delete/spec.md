## ADDED Requirements

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
