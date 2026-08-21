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