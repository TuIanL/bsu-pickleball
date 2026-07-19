## Why

双摄录制停止时，系统会同步将两路 TS 分段合并为 MP4、校验并登记视频，导致停止操作长时间阻塞。用户需要在短时间内连续录制多个任务，因此应先快速保存原始 TS，让视频合并成为任务管理中的可延后操作。

## What Changes

- 双摄正常停止后只完成 TS 分段收尾、元数据保存和录制任务终态化，不再自动执行 MP4 合并。
- 双摄任务列表为每个待合并任务提供一个“合并视频”操作，一次处理 A、B 两路。
- 增加持久且可查询的合并状态：待合并、合并中、已完成、失败。
- 合并前任务不可播放、不可创建分析任务；两路均成功后恢复播放和分析入口。
- 合并失败时保留原始 TS，任务卡片提供重新合并入口；已成功的机位合并必须可幂等复用。
- 单摄录制行为保持不变，不纳入本次改造。

## Capabilities

### New Capabilities

无。该变更修改现有双摄录制和任务管理能力。

### Modified Capabilities

- `dual-camera-sync-recording`：双摄停止不再自动合并，改为保存 TS 并进入待合并状态；通过显式任务操作触发两路 MP4 生成。
- `sync-recording-task-listing`：双摄任务卡片展示合并状态，并提供合并、处理中、重试及合并完成后的播放/分析入口。
- `capture-finalizer`：Finalizer 从停止流程中解耦，支持由任务管理操作显式触发、持久记录状态、两路任务级合并和幂等重试。

## Impact

- 后端双摄停止流程：`backend/app/camera/sync_recorder_service.py`、`backend/app/api/routes_sync_recording.py`。
- 后端合并状态与显式合并 API：`backend/app/camera/capture_finalizer.py` 及相关模型/服务。
- 前端 API、双摄任务卡片和状态展示：`src/services/analysisClient.ts`、`src/pages/AnalysisTasksPage.tsx`、相关类型定义。
- 播放和分析入口需要继续以已成功登记的 MP4 为准，避免在 TS 尚未合并时暴露不可用操作。
- 需要补充后端合并状态持久化、并发保护和前后端测试；不改变单摄停止和单摄 MP4 录制流程。
