## Context

前一个 Change 已实现 CaptureTake、CaptureSegment 最小投影（创建/关闭/查询）。Segment 的 `start_ms`/`end_ms` 完全由 TimelineEvent 推导，用户无法修正。

当前需要：
- 赛后独立编辑页面
- 人工修正边界（不覆盖原始推导值）
- Rally 拆分/合并
- 按片段创建分析任务

**关键约束**：
- Segment 已有 ORM 模型（capture_segments 表）
- 视频文件已通过 VideoService 注册
- 双摄有 CaptureTrack.offset_ms 映射

## Goals / Non-Goals

**Goals:**
- 独立 SegmentManagerPage
- 原生 video 封装播放器，支持主/辅轨道切换
- 片段列表 + 盘/局/分筛选 + 与播放器双向定位
- 可编辑时间线（拖动边界、插入分界点）
- Rally 拆分/合并（仅相邻、同一父 game）
- 批量选择 + 按 Segment 创建独立 AnalysisJob
- AnalysisBatch 汇总批量任务
- Pipeline 支持 clip_start_ms / clip_end_ms

**Non-Goals:**
- FFmpeg 导出 MP4
- 双摄双窗口同步播放
- 严格编码帧级定位（MVP 精度：100ms 或 1/fps 较大者）
- 盘/局任意拆分合并
- 多段离散范围合并成一个 Job

## Decisions

### Decision 1: 边界修正不覆盖原始推导值（唯一边界真相）

不再新增 `derived_*` 字段。`start_ms`/`end_ms` 就是事件推导的原始值，人工修正存入 `corrected_*`。只有一套时间真相。

```sql
ALTER TABLE capture_segments ADD COLUMN corrected_start_ms INTEGER;
ALTER TABLE capture_segments ADD COLUMN corrected_end_ms INTEGER;
ALTER TABLE capture_segments ADD COLUMN edit_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE capture_segments ADD COLUMN corrected_at DATETIME;
```

effective 值通过 ORM property 计算（**不存数据库**）：

```python
@property
def effective_start_ms(self) -> int:
    return self.corrected_start_ms if self.corrected_start_ms is not None else self.start_ms

@property
def effective_end_ms(self) -> int | None:
    return self.corrected_end_ms if self.corrected_end_ms is not None else self.end_ms
```

**注意**：必须用 `is not None` 而非 `or`，否则 `corrected_start_ms = 0` 会被当作假值跳过。

提供恢复原边界 API：

```http
POST /api/capture-segments/{id}/reset-boundary-correction
```

或允许 PATCH `corrected_start_ms: null`。

### Decision 2: 独立页面路由

路由：`/capture/{field_session_id}/takes/{capture_take_id}/segments`

页面三区布局：左侧播放器 + 右侧片段列表 + 底部可编辑时间线。

录制停止后，CaptureConsolePage 显示结果摘要 + 「进入片段管理」按钮。

### Decision 3: SegmentVideoPlayer 封装原生 video

封装为项目内组件，对外暴露命令式 handle：

```ts
interface SegmentVideoPlayerHandle {
  seekToTakeTime(timestampMs: number): void;
  play(): void;
  pause(): void;
  playSegment(startMs: number, endMs: number): void;
  stepForward(): void;
  stepBackward(): void;
}
```

双摄切换通过 dropdown 选择 track，组件内部计算 track 偏移。

### Decision 4: 逐帧步进

使用 `1/fps` 计算 frameDuration，直接设置 `video.currentTime`。不承诺编码帧级精度，目标精度 ≥ 100ms。

### Decision 5: 非破坏式拆分/合并/删除

所有编辑操作不直接修改或删除原 Segment。引入状态 + 编辑审计记录。

```sql
ALTER TABLE capture_segments ADD COLUMN edit_status TEXT NOT NULL DEFAULT 'active';
-- 'active' | 'superseded' | 'archived'
ALTER TABLE capture_segments ADD COLUMN superseded_by_operation_id TEXT;
ALTER TABLE capture_segments ADD COLUMN created_by_operation_id TEXT;
```

```sql
CREATE TABLE segment_edit_operations (
  id TEXT PRIMARY KEY,
  capture_take_id TEXT NOT NULL,
  operation_type TEXT NOT NULL,  -- 'boundary_correction' | 'rename' | 'split' | 'merge' | 'archive' | 'restore'
  input_segment_ids TEXT NOT NULL,  -- JSON array
  output_segment_ids TEXT NOT NULL, -- JSON array
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at DATETIME NOT NULL
);
```

拆分示例：
```
R5 (active)          10:00—10:50
  → R5   status = superseded
  → R5-A status = active  10:00—10:25
  → R5-B status = active  10:25—10:50
```

合并示例：
```
R8 (active)  12:00—12:20  → superseded
R9 (active)  12:20—12:42  → superseded
R8M          12:00—12:42  → active
```

**删除行为**：MVP 不提供硬删除。无子片段、无分析引用、无编辑历史的临时 Segment 可硬删除。其他情况仅 archive。

### Decision 6: AnalysisBatch + AnalysisBatchItem

不在 Segment 上保存单一 `analysis_job_id`。使用关联表保存任务输入快照。

```ysql
CREATE TABLE analysis_batches (
  id TEXT PRIMARY KEY,
  capture_take_id TEXT NOT NULL,
  status TEXT NOT NULL,  -- 'creating' | 'queued' | 'running' | 'partial' | 'completed' | 'failed'
  analysis_profile TEXT NOT NULL DEFAULT 'match_default',
  created_at DATETIME NOT NULL
);

CREATE TABLE analysis_batch_items (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES analysis_batches(id),
  segment_id TEXT NOT NULL,
  analysis_job_id TEXT,
  segment_version INTEGER NOT NULL,
  snapshot_start_ms INTEGER NOT NULL,
  snapshot_end_ms INTEGER NOT NULL,
  track_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  status TEXT NOT NULL,  -- 'pending' | 'queued' | 'running' | 'completed' | 'failed'
  error_message TEXT,
  created_at DATETIME NOT NULL
);
```

**关键**：BatchItem 保存创建任务时的 `snapshot_start_ms/end_ms` 和 `segment_version`。任务创建后用户修改 Segment 不影响已排队的 Job。

**批量约束**：
- 一次 Batch 只能选择同一种 segment_type（不允许混选 Game 和其下属 Rally）
- 后端校验不能存在 ancestor/descendant 同时被选中
- 硬上限 10 个/批（可配置）

### Decision 7: AnalysisJob 为 JSON 模型，非 ORM 列

当前 AnalysisJob 使用 `JobStore`（内存字典 + 磁盘 JSON），不是 SQLite ORM。clip 字段需扩展 Schema 而非数据库列：

```python
class AnalysisJobCreate(BaseModel):
    clipStartMs: int | None = None
    clipEndMs: int | None = None
    captureSegmentId: str | None = None
    segmentVersion: int | None = None
```

修改 `analysis_signature()` 将 clip 范围纳入签名，避免同一视频不同 Rally 被识别为同一任务。

### Decision 8: Pipeline 预热区间（pre-roll）

每个 Rally 独立分析时，球员跟踪器和球轨迹状态机没有前序上下文，开头几秒不稳定。

定义两级区间：
- **requested_range**：用户选择的片段 [start_ms, end_ms)
- **decode_range**：算法预热区间 [start_ms - pre_roll, end_ms + post_roll)

默认 pre_roll_ms=1500, post_roll_ms=500（可配置）。

**区间语义**：半开区间 `[start_ms, end_ms)`，相邻片段不会在边界重复处理同一帧。

规则：
- 跟踪/检测读取 decode_range
- 正式指标只统计 requested_range
- 报告产物显示 requested_range
- MVP 输出视频不包含预热帧

### Decision 9: Segment 编辑乐观锁

新增 `edit_version` 字段，PATCH 携带 `expected_version`：

```json
{ "expected_version": 3, "corrected_start_ms": 12000 }
```

成功后 `edit_version += 1`。不匹配返回 409。

前端拖动边界时：pointerdown 开始本地预览 → pointermove 只更新本地状态 → pointerup 发送一次 PATCH。不逐像素请求。

### Decision 10: 播放器轨道偏移公式

```text
track_local_time_ms = take_time_ms - track.offset_ms
```

若 `track_local_time_ms < 0` 或超出轨道时长，显示越界提示。

`sync_quality=degraded` 时 UI 显示警告。

### Decision 11: 层级时间约束

边界修改必须满足：
- `0 <= effective_start_ms < effective_end_ms <= take.duration_ms`
- Rally: `parent_game.effective_start <= rally.effective_start && rally.effective_end <= parent_game.effective_end`
- 相邻 Rally 默认不重叠
- 父片段边界调整后必须仍包含全部 active 子片段，否则拒绝

拆分约束：`split_ms - segment.start > 500ms && segment.end - split_ms > 500ms`

合并约束：同父 game + 相邻 + 无中间 active Rally + 间隔 < 500ms + 无进行中分析任务

## Risks / Trade-offs

### Risk 1: 原生 video seek 精度
**风险**: 浏览器 seek 受关键帧影响，可能不精确
**缓解**: MVP 精度目标 100ms；后续按需评估 WebCodecs

### Risk 2: 人工修正被事件重放覆盖
**风险**: 重建 segment 时不区分人工修正和事件推导
**缓解**: corrected_* 字段独立存储，重放不覆盖

### Risk 3: 双摄 offset 漂移
**风险**: 长时间录制后 offset 可能变化
**缓解**: offset 重建时不主动修改，用户可手动调整

## Open Questions

1. ~~Segment 删除行为~~：MVP 不硬删除，仅 archive/supersede；临时错误记录可硬删除
2. ~~批量任务数量上限~~：默认 10，配置 `segment_analysis_batch_limit`，UI 展示已选/上限
