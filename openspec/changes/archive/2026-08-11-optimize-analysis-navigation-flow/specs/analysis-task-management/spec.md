## ADDED Requirements

### Requirement: 任务列表来源上下文可恢复

分析任务管理页 SHALL 使用有限来源枚举表示当前任务视图，并在 URL 中保留来源 tab；双摄视图可以额外保留其录制 session id。页面重新挂载、刷新或从任务详情返回时 SHALL 恢复 URL 指定的来源视图。

#### Scenario: 返回双摄任务列表

- **WHEN** 用户从双摄任务卡片进入分析详情后点击返回任务管理
- **THEN** 页面 SHALL 回到双摄录制 tab
- **AND** SHALL NOT 默认显示上传视频任务 tab

#### Scenario: 直接打开带来源的任务列表

- **WHEN** 用户打开 `/analysis/tasks?source=sync_recording&session=<sessionId>`
- **THEN** 页面 SHALL 激活双摄录制 tab
- **AND** SHALL 使用 session id 作为当前录制上下文

#### Scenario: 非法来源参数

- **WHEN** URL 中的 `source` 不是受支持的来源枚举
- **THEN** 页面 SHALL 安全回退到上传视频任务 tab
- **AND** SHALL 不抛出路由解析异常

### Requirement: 任务页 tab 切换不污染浏览器历史

任务管理页来源 tab 切换 SHALL 更新可恢复的 URL 状态，但 SHALL 使用 replace 历史语义；从任务页进入详情或创建页 SHALL 使用新的业务历史项。

#### Scenario: 用户切换任务来源

- **WHEN** 用户在任务管理页从上传任务切换到双摄录制
- **THEN** 地址 SHALL 反映双摄来源
- **AND** 用户随后按浏览器后退 SHALL 不需要逐个经过任务页 tab 切换状态

