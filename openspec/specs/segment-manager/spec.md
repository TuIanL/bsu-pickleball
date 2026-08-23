# segment-manager Specification

## Purpose

定义片段管理页（SegmentManagerPage）的前端行为：单摄/双摄视频回放源解析、数据加载的独立兜底与错误/空态反馈，确保片段页可加载、可播放、可操作。
## Requirements
### Requirement: 片段页视频回放源解析

系统 MUST 使用可播放的 `video_id` 构造视频流地址，MUST NOT 使用 `source_session_id`（采集会话 ID）作为视频流 ID。

#### Scenario: 单摄素材播放原视频

- **WHEN** CaptureTake 的 `video_ids` 恰好包含一个元素
- **THEN** 播放器源 SHALL 指向 `/api/videos/{video_ids[0]}/stream`
- **AND** 播放器 SHALL 展示单个视频轨道选项

#### Scenario: 双摄素材多机位切换

- **WHEN** CaptureTake 的 `video_ids` 包含多个元素（如 cam_1、cam_2）
- **THEN** 播放器 SHALL 提供机位切换下拉
- **AND** 每个机位 SHALL 指向各自 `/api/videos/{video_id}/stream`
- **AND** 默认选中第一个机位

#### Scenario: 不使用采集会话 ID 拼流地址

- **WHEN** 页面构造视频流 URL
- **THEN** SHALL NOT 使用 `source_session_id` 作为 `video_id`

### Requirement: 片段页视频不可用反馈

系统 MUST 在视频源缺失或不可播放时提供稳定的可见反馈，MUST NOT 静默黑屏。

#### Scenario: 无可用视频源

- **WHEN** `video_ids` 为空或全部不可播放
- **THEN** 页面 SHALL 显示「暂无可用视频回放」类稳定空态
- **AND** 页面 SHALL 保留片段列表与时间轴等其余功能

#### Scenario: 视频流请求失败

- **WHEN** 播放器请求 `/api/videos/{video_id}/stream` 返回 404 或解码失败
- **THEN** 页面 SHALL 显示播放失败/不可用状态

### Requirement: 片段页数据加载独立兜底

系统 MUST 将 take 详情、片段列表、时间轴事件三个数据源独立加载、独立兜底，任一失败不得瘫痪整页。

#### Scenario: 单一数据源失败

- **WHEN** take 详情、segments、timeline-events 中某一个请求失败
- **THEN** 其余成功的数据源 SHALL 正常展示
- **AND** 页面 SHALL 显示明确错误信息

#### Scenario: 关键数据源失败展示错误态

- **WHEN** take 详情（页面渲染必需）请求失败
- **THEN** 页面 SHALL 展示错误态与重试入口
- **AND** 页面 SHALL NOT 永久停留在「加载中...」

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

