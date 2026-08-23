## ADDED Requirements

### Requirement: 片段列表提供明确的播放与编辑入口

片段管理页 SHALL 区分片段播放区域、选择框、标签编辑入口和管理操作，避免普通点击、双击编辑、选择分析片段之间互相误触发。

#### Scenario: 普通点击片段行

- **WHEN** 用户点击片段的播放区域
- **THEN** 页面 SHALL 播放该片段的有效区间
- **AND** 页面 SHALL 高亮对应片段行

#### Scenario: 选择分析片段

- **WHEN** 用户点击片段复选框
- **THEN** 页面 SHALL 只切换分析选择状态
- **AND** SHALL 不改变播放器时间或启动播放

#### Scenario: 编辑片段标签

- **WHEN** 用户通过标签编辑入口进入编辑
- **THEN** 页面 SHALL 只修改标签字段
- **AND** SHALL 不改变片段边界、关键事件或播放状态

### Requirement: 片段管理页保持播放头和列表高亮同步

片段管理页 SHALL 将播放器当前时间传给时间线，并在列表、时间线片段块和播放结束状态之间保持一致。

#### Scenario: 右侧点击片段后同步

- **WHEN** 用户点击右侧某一分
- **THEN** 播放器 SHALL 从该分起点播放
- **AND** 时间线播放头 SHALL 跳转到相同时间
- **AND** 右侧对应行与时间线对应块 SHALL 高亮

#### Scenario: 播放自动停止

- **WHEN** 播放到该分的有效终点
- **THEN** 播放器 SHALL 自动暂停
- **AND** 高亮 SHALL 保留在最后播放的片段上

### Requirement: 片段边界编辑明确影响范围

片段管理页 SHALL 明确提示边界拖拽修改的是片段的 corrected 边界，后续分析使用该有效边界，但不会直接修改下方关键事件。

#### Scenario: 拖拽边界

- **WHEN** 用户拖拽片段起点或终点
- **THEN** 页面 SHALL 先显示本地预览
- **AND** 释放后 SHALL 保存一次边界修改
- **AND** SHALL 在保存成功后刷新有效边界

#### Scenario: 关键事件保持不变

- **WHEN** 用户完成片段边界修改
- **THEN** 时间线中的 `SessionTimelineEvent` 标记 SHALL 保持原始时间和内容
- **AND** 页面 SHALL 不把边界拖拽解释为关键事件编辑

