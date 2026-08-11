## Why

双摄录制任务当前按 `recording_session_id` 归类，而后端还支持通过 `capture_take_id` 识别同一录制派生的分析任务，导致页面展示范围与删除范围可能不一致。同一机位或同一双摄录制存在多次分析时，页面使用 `.find()` 只展示一条任务，用户无法判断历史任务、结果版本和实际可删除范围。

需要统一双摄任务的归属判定，并让页面按任务类型展示最新任务与历史任务，避免任务丢失、错误操作和删除后状态难以理解。

## What Changes

- 双摄录制任务归类同时支持 `recording_session_id` 和对应 `capture_take_id`，使页面展示范围与后端录制级删除范围一致。
- 为每条双摄录制建立结构化任务分组：双摄协同 Parent、A 机位单摄任务、B 机位单摄任务。
- 每个任务分组默认展示最新任务；同类型历史任务以可展开方式保留，不再被 `.find()` 静默隐藏。
- 任务操作绑定具体任务 ID，查看报告、查看进度、重试、取消和删除不再依赖被隐式选中的第一条任务。
- 双摄协同 Parent 继续作为主任务展示，internal child 不直接暴露；Parent 与其 child 的级联删除语义保持不变。
- 补充前端分组、归属兜底、最新任务选择和历史任务展示测试。

## Capabilities

### New Capabilities

### Modified Capabilities

- `analysis-task-management`: 修改双摄录制任务的归属判定、任务分组展示和多版本任务管理要求。
- `sync-recording-task-listing`: 修改双摄录制卡片中分析任务的分组、最新任务和历史任务展示要求。

## Impact

- 前端主要影响 `src/pages/AnalysisTasksPage.tsx`、双摄任务卡片及其测试。
- 前端可能新增或调整任务分组 view model/helper，统一 session/take 归属判定和按类型排序。
- 后端 API 与分析任务删除级联契约保持不变；只需验证前端使用的归属规则与后端 `DELETE /api/sync-recordings/{session_id}/analysis` 一致。
- 不改变分析执行、融合算法、录制视频资产和 internal child 的公开性。
