## 1. 数据库迁移

- [x] 1.1 ALTER capture_segments 增加 corrected_start_ms/end_ms
- [x] 1.2 ALTER capture_segments 增加 edit_version（默认 0）
- [x] 1.3 ALTER capture_segments 增加 corrected_at
- [x] 1.4 ALTER capture_segments 增加 edit_status（默认 'active'）
- [x] 1.5 ALTER capture_segments 增加 superseded_by_operation_id
- [x] 1.6 ALTER capture_segments 增加 created_by_operation_id
- [x] 1.7 创建 segment_edit_operations 表
- [x] 1.8 创建 analysis_batches 表
- [x] 1.9 创建 analysis_batch_items 表（含 snapshot 字段）
- [x] 1.10 编写 Alembic migration 脚本（含回滚）

## 2. Segment 编辑后端服务

- [x] 2.1 实现 effective_start_ms/end_ms ORM property（is not None）
- [x] 2.2 实现 Segment PATCH API（重命名、corrected 边界、is_highlight、expected_version）
- [x] 2.3 实现 reset-boundary-correction API
- [x] 2.4 实现非破坏式 Rally 拆分（superseded + 两个新 active + edit operation 记录）
- [x] 2.5 实现非破坏式 Rally 合并（superseded + 一个新 active + edit operation 记录）
- [x] 2.6 实现 archive/restore API
- [x] 2.7 实现硬删除（仅无子节点、无分析引用、无编辑历史的临时 Segment）
- [x] 2.8 实现层级时间约束校验（父包含子、相邻不重叠、拆合点最小间隔）
- [x] 2.9 查询默认排除 superseded/archived
- [x] 2.10 编写 Segment 编辑单元测试

## 3. AnalysisBatch 后端

- [x] 3.1 实现 AnalysisBatch + AnalysisBatchItem ORM 模型
- [x] 3.2 实现 POST /api/capture-takes/{id}/analysis-batches API
- [x] 3.3 创建 BatchItem 时保存快照（snapshot_start_ms/end_ms、segment_version、video_id）
- [x] 3.4 校验同类型、无父子关系、上限 ≤ 可配置值
- [x] 3.5 每个 Item → 独立 AnalysisJob（扩展 AnalysisJobCreate JSON Schema）
- [x] 3.6 修改 analysis_signature() 包含 clip 参数
- [x] 3.7 实现 GET /api/analysis-batches/{batch_id} 查询
- [x] 3.8 编写 AnalysisBatch 单元测试

## 4. AnalysisJob Schema 扩展（JSON 字段，非 ORM 列）

- [x] 4.1 AnalysisJobCreate 增加 clipStartMs/clipEndMs/captureSegmentId/segmentVersion
- [x] 4.2 AnalysisJobSummary 增加对应字段
- [x] 4.3 analysis_signature() 输入 signature 包含 clip 范围
- [x] 4.4 JobStore.create_job() 保存 clip 参数到 JSON
- [x] 4.5 Worker run_kwargs 传递 clip_start_ms/clip_end_ms
- [x] 4.6 前端 AnalysisJob 类型增加 clip 字段
- [x] 4.7 编写 Schema 扩展单元测试

## 5. Pipeline 时间裁剪 + 预热区间

- [x] 5.1 Pipeline entry 接收 clip_start_ms/clip_end_ms 参数
- [x] 5.2 实现 pre-roll/post-roll 解码范围计算（默认 1500/500）
- [x] 5.3 帧读取循环：解码预热帧，指标只统计 clip 范围
- [x] 5.4 区间语义统一为半开 [start, end)
- [x] 5.5 Pipeline 结果记录 requested_clip 和 decoded_range
- [x] 5.6 所有子阶段（tracking、ball、metrics）裁剪到 clip 范围
- [x] 5.7 编写 Pipeline 裁剪集成测试

## 6. 视频 HTTP Range 支持

- [x] 6.1 验证 /api/videos/{id}/stream 端点支持 Range 请求
- [x] 6.2 验证响应头 Accept-Ranges: bytes
- [x] 6.3 验证 Safari / Chrome 长视频 seek 正常
- [x] 6.4 如不支持则修改 stream 端点

## 7. 前端 SegmentVideoPlayer

- [x] 7.1 实现 SegmentVideoPlayer 组件（原生 video 封装）
- [x] 7.2 实现 seekToTakeTime / playSegment API
- [x] 7.3 实现逐帧步进（方向键 + 1/fps）
- [x] 7.4 实现主/辅轨道切换（track_offset_ms 公式：track_local = take_time - offset）
- [x] 7.5 越界提示（track_local < 0 或 > duration）
- [x] 7.6 sync_quality=degraded 时 UI 警告
- [x] 7.7 实现 loopSegment 模式（到 end_ms 暂停）
- [x] 7.8 编写 SegmentVideoPlayer 单元测试

## 8. 前端 SegmentManagerPage

- [x] 8.1 创建 SegmentManagerPage 组件
- [x] 8.2 注册路由 /capture/:fieldSessionId/takes/:takeId/segments
- [x] 8.3 三区布局（播放器 | 列表 | 时间线）
- [x] 8.4 片段列表 + 盘/局/分筛选 Tab
- [x] 8.5 列表、播放器、时间线三向联动
- [x] 8.6 重命名行内编辑（带保存状态）
- [x] 8.7 批量选择（同类型、无父子关系）+ 已选计数
- [x] 8.8 「创建分析任务」→ AnalysisBatch API → 结果反馈
- [x] 8.9 「合并片段」按钮（选择 2 个相邻 Rally）
- [x] 8.10 「在播放头处分割」按钮（替代双击）
- [x] 8.11 「恢复原边界」按钮
- [x] 8.12 编辑状态提示（保存中/已保存/失败/版本冲突）
- [x] 8.13 CaptureConsolePage 停止后增加「进入片段管理」入口
- [x] 8.14 编写 SegmentManagerPage 集成测试

## 9. 前端 EditableSegmentTimeline

- [x] 9.1 实现 EditableSegmentTimeline 组件
- [x] 9.2 三轨道（盘/局/分）+ 事件标记
- [x] 9.3 拖动边界（pointerdown 预览 → pointerup 一次 PATCH + expected_version）
- [x] 9.4 拖动失败后恢复服务器边界
- [x] 9.5 播放头联动（双向，拖动播放头更新视频时间）
- [x] 9.6 显示 superseded 区间（半透明/虚线）
- [x] 9.7 编写 EditableSegmentTimeline 单元测试

## 10. 前端 API 客户端

- [x] 10.1 实现 Segment PATCH API（含 expected_version）
- [x] 10.2 实现 reset-boundary-correction API
- [x] 10.3 实现 Rally split/merge API
- [x] 10.4 实现 archive/restore API
- [x] 10.5 实现 AnalysisBatch API
- [x] 10.6 更新前端类型（Segment、Batch、BatchItem、clip 字段）
