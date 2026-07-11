## ADDED Requirements

### Requirement: 统一录制资源清理

系统 MUST 提供 `CaptureCleanupService` 服务，被单摄和双摄 session 删除操作共同调用，完成 CaptureTake、CaptureTrack、CaptureSegment、TimelineEvent、Video 资产和物理媒体文件的级联清理。

#### Scenario: 级联清理顺序

- **WHEN** 删除操作被触发
- **THEN** 系统 MUST 按以下顺序清理
- **AND** 检查是否仍处于 recording/starting（拒绝删除活跃会话）
- **AND** CaptureTake 标记 deleting
- **AND** 处理 AnalysisJob 引用（anonymize 或阻止删除）
- **AND** 删除或归档 TimelineEvent
- **AND** 删除 CaptureSegment
- **AND** 删除 CaptureTrack / Fragment 元数据
- **AND** 删除 Video 资产登记
- **AND** 删除物理媒体文件
- **AND** 删除 source session JSON
- **AND** 释放 CameraLease
- **AND** 删除或保留 CaptureTake tombstone

#### Scenario: 每步幂等

- **WHEN** 清理过程中某一步失败后重试
- **THEN** 已成功的步骤 MUST 不报错（幂等）
- **AND** 系统 MUST 从失败步骤继续执行，不从头开始

#### Scenario: 被分析任务引用的录制阻止删除

- **WHEN** 录制关联的视频已被 AnalysisJob 引用
- **THEN** 系统 MUST 阻止物理删除视频文件
- **AND** 系统 MUST 返回阻止原因
- **AND** 系统 MAY 允许删除其他非视频资产

#### Scenario: 活跃录制拒绝删除

- **WHEN** 录制 session 仍处于 recording 或 starting 状态
- **THEN** 系统 MUST 拒绝删除请求
- **AND** 系统 MUST 返回错误信息提示先停止录制

#### Scenario: 单摄和双摄删除调用同一服务

- **WHEN** 单摄 session 被删除
- **THEN** 系统 MUST 通过 CaptureCleanupService 完成清理
- **WHEN** 双摄 session 被删除
- **THEN** 系统 MUST 通过同一 CaptureCleanupService 完成清理（清理两个 Track 的文件和视频）
