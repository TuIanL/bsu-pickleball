# recording-playback Specification

## Purpose
Define the recording playback capability — enabling users to play back completed recording sessions directly from the recording history list using the existing video streaming API.

## Requirements
### Requirement: 录制历史播放入口

系统 MUST 在录制历史中为可播放的录制会话提供视频播放入口。

#### Scenario: 已完成录制显示播放入口
- **WHEN** 录制 session 的 `status` 为 `completed`
- **AND** 录制 session 包含非空 `video_id`
- **THEN** 页面 SHALL 在该历史记录中显示播放入口
- **AND** 播放入口 SHALL 使用该 `video_id` 构造视频流 URL

#### Scenario: 不可播放录制不显示播放入口
- **WHEN** 录制 session 的 `status` 为 `recording`、`canceled` 或 `failed`
- **THEN** 页面 SHALL 不显示普通播放入口
- **AND** 页面 SHALL 保留该 session 的状态、时长、错误信息或分析任务入口

#### Scenario: 已完成但缺少 video_id
- **WHEN** 录制 session 的 `status` 为 `completed`
- **AND** 录制 session 的 `video_id` 为空
- **THEN** 页面 SHALL 不显示播放入口
- **AND** 页面 SHALL 显示稳定的不可播放状态或省略播放操作

### Requirement: 录制视频播放器

系统 MUST 允许用户在球场采集页面打开并播放录制视频。

#### Scenario: 打开录制视频
- **WHEN** 用户点击录制历史中的播放入口
- **THEN** 页面 SHALL 打开播放器视图
- **AND** 播放器 SHALL 使用浏览器原生视频控件
- **AND** 播放器源 SHALL 指向 `/api/videos/{video_id}/stream`

#### Scenario: 关闭播放器
- **WHEN** 用户关闭播放器视图
- **THEN** 页面 SHALL 停止展示该视频播放器
- **AND** 用户 SHALL 返回录制历史上下文

#### Scenario: 切换播放目标
- **WHEN** 用户在播放器打开时选择另一条可播放录制
- **THEN** 页面 SHALL 将播放器源切换到新录制的 `video_id`
- **AND** 页面 SHALL 不改变任何录制 session 状态

### Requirement: 回放失败处理

系统 MUST 对录制视频回放失败提供稳定反馈。

#### Scenario: 视频流返回 404
- **WHEN** 播放器请求 `/api/videos/{video_id}/stream` 但后端返回 404
- **THEN** 页面 SHALL 显示视频不可用状态
- **AND** 页面 SHALL 保留录制历史记录

#### Scenario: 浏览器无法播放视频
- **WHEN** 视频文件存在但浏览器无法解码或播放
- **THEN** 页面 SHALL 显示播放失败状态
- **AND** 页面 SHALL 不删除录制 session 或视频元数据

### Requirement: 回放复用视频服务

系统 MUST 复用现有视频服务播放录制文件。

#### Scenario: 使用 VideoService stream
- **WHEN** 页面播放录制视频
- **THEN** 页面 SHALL 通过 `video_id` 请求现有视频 stream API
- **AND** 页面 SHALL 不直接暴露或请求服务器本地 `video_path`
