# dual-camera-sync-recording Specification

## Purpose

定义双摄录制停止后的双路视频合并、失败状态、视频可用性和后续分析入口行为，并明确任务状态、产物登记和失败恢复的测试边界。

## Requirements

### Requirement: 双摄停止后合并两路 MP4

双摄正常停止时，系统 MUST 先完成两路 TS 分段的安全收尾、CaptureTake 终态化和任务元数据持久化，且 MUST NOT 在停止请求中自动执行 MP4 合并。系统 MUST 允许用户通过任务管理中的一个任务级操作，异步为 cam_1 和 cam_2 分别合并有效 Fragment，并在两路都成功后登记视频。

#### Scenario: 双摄正常停止不自动合并

- **WHEN** 双摄录制正常停止
- **THEN** 系统 MUST 停止两路录制进程并保存有效 TS 分段
- **AND** 系统 MUST 持久化双摄会话和 CaptureTake 的终态信息
- **AND** 停止 API MUST NOT 调用 MP4 合并或 Video 登记流程
- **AND** 双摄任务 MUST 进入"待合并"状态

#### Scenario: 用户显式触发双路合并

- **WHEN** 用户在任务管理中对一个已停止的双摄任务点击"合并视频"
- **THEN** 系统 MUST 异步提交该任务的合并操作
- **AND** 系统 MUST 为 cam_1 和 cam_2 分别合并有效 Fragment
- **AND** 系统 MUST 持久化合并中的状态和每路处理结果
- **AND** 两路均成功后 cam_1 MUST 登记为 `default_analysis_video_id`

#### Scenario: 合并前任务不可用作视频

- **WHEN** 双摄任务尚未完成两路 MP4 合并
- **THEN** 系统 MUST NOT 提供可用的播放视频 ID
- **AND** 系统 MUST NOT 允许基于该任务创建视频分析任务

#### Scenario: 任一路合并失败

- **WHEN** cam_1 或 cam_2 合并、校验或登记失败
- **THEN** 系统 MUST 保留两路原始 TS 分段
- **AND** 任务总体状态 MUST 为失败或可重试状态
- **AND** 系统 MUST 保存可展示的失败原因
- **AND** 用户 MUST 能再次触发合并

#### Scenario: 合并后 cam_2 可参与分析

- **WHEN** 双路合并成功且 `registered_video_ids` 包含 cam_1 与 cam_2 的 video ID
- **THEN** 系统 SHALL 允许 cam_2 的 `registered_video_id` 作为分析任务的 `videoId` 被提交
- **AND** 录制任务卡片 SHALL 为 cam_1 和 cam_2 各显式一个分析入口按钮
- **AND** 分析按钮 SHALL 根据各机位分析状态自动切换文案（分析 → 分析中 → 查看报告 → 重新分析）
