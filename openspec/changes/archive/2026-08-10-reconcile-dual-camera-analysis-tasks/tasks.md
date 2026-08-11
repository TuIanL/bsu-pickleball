## 1. 归属解析与任务分组

- [x] 1.1 定义双摄任务分组 view model，区分 multiview Parent、A 机位单摄、B 机位单摄和无法可靠映射的公开任务。
- [x] 1.2 实现统一的录制归属解析函数，按 `recordingSessionId`、`metadata.recording_session_id` 和 `metadata.capture_take_id` 匹配双摄会话。
- [x] 1.3 实现按 `updatedAt`、`createdAt` 和 job id 的稳定排序，并为每组计算当前任务与历史任务列表。
- [x] 1.4 为历史任务的机位映射保留 `cameraSlot`、`metadata.camera_slot` 和登记视频 ID 的兼容兜底，Parent 判断优先于机位判断。

## 2. 任务列表接入

- [x] 2.1 使用统一归属解析函数重构 `AnalysisTasksPage` 的双摄派生任务集合和上传任务排除逻辑。
- [x] 2.2 将按 session id 的双摄卡片任务传递改为按 session/take 归属解析结果传递，消除页面展示范围与录制级删除范围的不一致。
- [x] 2.3 重构 `SyncRecordingTaskCard` 的分析状态区域，按双摄协同、A 机位和 B 机位分区展示每组最新任务，并提供历史任务展开入口。
- [x] 2.4 将查看报告、查看进度、重试、取消和任务级删除操作绑定到具体 `job.id`；保持 Parent 删除时由后端级联清理 internal child。
- [x] 2.5 保持录制级“清除本录制全部分析任务”独立于任务行删除，并确认其继续保留双摄录制资产。
- [x] 2.6 处理空任务、无法映射任务、多个 Parent、合并未完成和任务刷新中的稳定展示状态。

## 3. 测试与验证

- [x] 3.1 为归属解析函数增加 session id 命中、capture take 命中、无归属和双摄会话隔离测试。
- [x] 3.2 为任务分组增加 Parent 优先级、A/B 机位映射、最新任务排序、缺少更新时间和历史任务保留测试。
- [x] 3.3 为 `SyncRecordingTaskCard` 增加多次同机位/多 Parent 场景测试，验证默认任务、历史展开和操作使用正确 job id。
- [x] 3.4 增加任务页回归测试，验证 capture take 归属的双摄任务不会出现在上传任务 Tab，且 internal child 不会显示。
- [x] 3.5 运行前端 TypeScript、相关 Vitest 测试和 OpenSpec 校验，修复回归后更新任务状态。
