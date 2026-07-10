## Why

`add-capture-take-and-live-coding-console` 完成了现场实时编码控制台——录制中打点、盘/局/分区间自动创建、层级状态管理。赛后需要独立的片段管理页面，支持精细编辑边界、筛选、批量操作，并将选定的片段直接提交分析流水线（无需先生成裁切 MP4）。

## What Changes

- **独立 SegmentManagerPage**：路由 `/capture/{field_session_id}/takes/{capture_take_id}/segments`
- **SegmentVideoPlayer 组件**：封装原生 `<video>`，支持 seek、区间播放、步进、轨道切换
- **可编辑时间线**：拖动边界、插入分界点、open 区间动画
- **片段编辑**：重命名、调整 effective_start_ms/end_ms（人工修正不覆盖原始推导值）
- **Rally 拆分/合并**：相邻同一父 game 的 rally 支持拆分和合并
- **批量选择**：多选片段，批量创建分析任务
- **AnalysisBatch**：每个 Segment 生成独立 AnalysisJob，Batch 汇总
- **Pipeline 适配**：支持 clip_start_ms / clip_end_ms 参数

## Capabilities

### New Capabilities

- `segment-editing`: 非破坏式片段编辑（corrected 边界、supersede/archive、乐观锁、层级约束）、Rally 拆分/合并、编辑审计记录
- `segment-analysis-integration`: AnalysisBatch + BatchItem（快照式任务创建）、AnalysisJob clip 参数、Pipeline 预热区间

### Modified Capabilities

- `analysis-job-orchestration`: AnalysisJob JSON Schema 增加 clip 参数、签名包含 clip 范围、Pipeline 半开区间裁剪 + pre-roll

## Impact

- **后端新增**：SegmentEditOperation、AnalysisBatch/BatchItem 模型、Segment 编辑/archive/split/merge API、Batch API
- **后端修改**：AnalysisJobCreate/Summary Schema、analysis_signature、Pipeline 裁剪+预热、视频 HTTP Range
- **前端新增**：SegmentManagerPage、SegmentVideoPlayer、EditableSegmentTimeline
- **前端修改**：CaptureConsolePage 停止后入口调整
- **数据库**：capture_segments 增加 corrected_*/edit_version/edit_status，新增 segment_edit_operations、analysis_batches、analysis_batch_items

## Non-Goals（本轮不做）

- FFmpeg 裁切导出 MP4
- 双摄同步双窗口播放
- 严格编码帧级定位
- 任意盘/局拆分合并
- 多段离散范围合并成一个 AnalysisJob
