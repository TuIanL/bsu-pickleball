## 1. 后端类型扩展

- [x] 1.1 在 `court_track_types.py` 中新增 `RenderSlot` 类型（`Literal["slot_1", "slot_2", "slot_3", "slot_4"]`）
- [x] 1.2 新增 `SegmentBreakReason` 类型（`start`, `identity_reset`, `identity_reassigned`, `visible_gap`, `distance_jump`, `projection_gap`——首批保留 `projection_gap` 但不触发）
- [x] 1.3 新增 `RenderPlayerMetadata` dataclass（player_id, render_slot, initial_side, dominant_side, first_frame_index, source_track_ids）
- [x] 1.4 新增 `RenderSegmentMetadata` dataclass（segment_id, player_id, identity_epoch, start_frame_index, end_frame_index, start_timestamp_seconds, end_timestamp_seconds, break_before, sample_count）。不包含 `start_sequence_index`/`end_sequence_index`（扁平 interleaved 数组无法用连续范围索引）
- [x] 1.5 扩展 `RenderFrame` dataclass，新增字段（sequence_index, render_slot, side, segment_id, identity_epoch, source_track_id, projection_status, projection_confidence, footpoint_method）。全部字段设有默认值以兼容旧调用方
- [x] 1.6 新增 `CourtTrackPostProcessResult` dataclass（players: list[RenderPlayerMetadata], segments: list[RenderSegmentMetadata], samples: list[RenderFrame]）
- [x] 1.7 在 `visualization_schemas.py` 中新增 `CourtVisualizationStyleProfile` dataclass
- [x] 1.8 新增 `CourtTrackSegmentationProfile` dataclass

## 2. 视觉主题与分段配置资源文件

- [x] 2.1 新建 `backend/app/resources/court_render_profile.v1.json`（包含 `style_profile` 和 `segmentation_profile` 两部分）
- [x] 2.2 `style_profile` 定义 slot_1~4 颜色、球颜色、弹跳颜色、界外点颜色、player_trail_seconds、ball_trail_seconds、bounce_display_seconds、radius.min_px/max_px
- [x] 2.3 `segmentation_profile` 定义 jump_threshold_ft、max_visible_gap_seconds
- [x] 2.4 确保 `importlib.resources.files("app.resources")` 可读取该文件
- [x] 2.5 Python 加载器在资源文件不可用时使用内置默认 profile

## 3. PostProcessor 扩展

- [x] 3.1 新增 `process()` 方法，返回 `CourtTrackPostProcessResult`；现有 `build_tracks()` 委托给 `process()` 并返回 `.samples，`保证向后兼容
- [x] 3.2 `process()` 入口调用 `canonical_player_id()` 规范化所有 player_id
- [x] 3.3 实现 `_build_roster()`：收集唯一 player_id，执行 natural sort
- [x] 3.4 实现 `_assign_render_slots()`：`observed_player_count > MAX_RENDER_SLOTS` 时抛出 `RenderSlotOverflowError`，否则按 roster 排序分配 slot_1 至 slot_N
- [x] 3.5 渲染槽位在 pipeline/visualization 层 catch `RenderSlotOverflowError`，仅标记 `player-render-trajectories` artifact `failed`，不传播到 tracking/ball/report
- [x] 3.6 读取上游 `identity_epoch`（不自行递增）：identity_epoch 变化时创建新 segment（break_before = identity_reset）
- [x] 3.7 实现 `_build_segments()`：在 (player_id, identity_epoch) 分组内，按 visible_gap → distance_jump 顺序判断连续性，生成 segment
- [x] 3.8 segment break_before 优先级：identity_reset > identity_reassigned > visible_gap > distance_jump > start
- [x] 3.9 `projection_gap` 暂不触发：仅在 `CourtTrackEvent` 明确提供 projection failure/recovery 事件时才生成，无事件时统一为 `visible_gap`
- [x] 3.10 定义 `CourtTrackEvent` 到 `SegmentBreakReason` 的映射表（首批：`player_reset_after_prolonged_loss` → `identity_reset`；投影事件暂无，后续添加）
- [x] 3.11 每个 sample 写入 `segment_id`（格式 `{player_id}:e{epoch}:s{segment_index}`）
- [x] 3.12 每个 sample 写入 `render_slot`（从 roster 查找）
- [x] 3.13 `side` 赋值：原始 observation 有 side 时透传；插值点继承当前 segment 最近的 detected sample 的 side；缺失时调用 `classify_court_side(y_ft)` 推导。不重新硬编码 y>22
- [x] 3.14 `initial_side` = 第一个 source=detected 的 sample 的 side；`dominant_side` = near/far 占比统计（相等→mixed，无可靠→unknown）
- [x] 3.15 在插值后的 sample 上保留 `source_track_id`（来自原始观测，插值帧为 null）
- [x] 3.16 在检测帧上保留 `projection_status`、`projection_confidence`、`footpoint_method`
- [x] 3.17 返回 `CourtTrackPostProcessResult(players, segments, samples)`

## 4. Artifact 序列化（v2）

- [x] 4.1 在 `visualization_schemas.py` 中新增 `serialize_render_trajectory_v2()` 函数
- [x] 4.2 artifact 顶层写入 `schema_version: "player-render-trajectory.v2"`
- [x] 4.3 写入 `players` 数组
- [x] 4.4 写入 `segments` 数组
- [x] 4.5 写入 `samples` 扁平数组（samples 全局按 timestamp_seconds, frame_index, player_id 排序，sequence_index 单调递增）
- [x] 4.6 加载 `court_render_profile.v1.json`，分别写入 `style_profile` 和 `segmentation_profile` 两个独立字段
- [x] 4.7 确保 v1 已有字段保持兼容
- [x] 4.8 新增 `player_render_v2_points_from_artifact()` 解析函数（兼容 v2 字段）

## 5. Pipeline 集成

- [x] 5.1 在 `analysis_pipeline.py` 的 `_run_tracking()` 末尾调用 `process()` 获取 `CourtTrackPostProcessResult`，catch `RenderSlotOverflowError` 并标记 artifact failed
- [x] 5.2 扩展 `AnalysisPipeline.run()` 写出 v2 `player_render_trajectory.json`
- [x] 5.3 `AnalysisPipelineResult.artifacts` 中扩展（或确认已有）`player_render_trajectory_url`、`player_render_trajectory_status`、`player_render_trajectory_detail`
- [x] 5.4 确认 `storage_service.py` 中 `player_render_trajectory_path(job_id)` 已存在
- [x] 5.5 确认 `routes_analysis.py` 中 `player-render-trajectories` 已在 artifact 白名单和路由分支中

## 6. OverlayVideoWriter segment-aware 调整

- [x] 6.1 更新 player_trails deque 时比较新 sample 与队尾 sample 的 segment_id
- [x] 6.2 segment_id 不同时清空该球员的 deque 再追加
- [x] 6.3 frame_table 构建方式不变，回退路径不变
- [x] 6.4 v1 sample 无 segment_id 时不报错，保持旧拖尾行为（不清空 deque）
- [x] 6.5 确认不改变颜色、标记大小、线宽

## 7. 前端类型定义

- [x] 7.1 新增 `RawPlayerRenderTrajectoryV2` 接口（所有 sample 字段 `?` 可选）
- [x] 7.2 新增 `RawPlayerRenderFrame` 接口（字段可选，兼容 v1/v2）
- [x] 7.3 新增 `RenderPlayerMetadata` 接口
- [x] 7.4 新增 `RenderSegmentMetadata` 接口
- [x] 7.5 新增 `CourtVisualizationStyleProfile` 接口
- [x] 7.6 新增 `NormalizedPlayerRenderTrajectory` 接口（归一化输出）
- [x] 7.7 新增 `NormalizedRenderFrame` 接口（render_slot, segment_id, identity_epoch, side 全部必填）
- [x] 7.8 定义 `DEFAULT_COURT_VISUAL_THEME_V1` 常量（仅包含 style_profile 部分）

## 8. 前端 normalizer

- [x] 8.1 新建 `src/services/playerRenderTrajectory.ts`
- [x] 8.2 实现 `normalizePlayerRenderTrajectory(raw: RawPlayerRenderTrajectoryV1 | RawPlayerRenderTrajectoryV2): NormalizedPlayerRenderTrajectory`
- [x] 8.3 v2 artifact：直接透传 render_slot、segment_id、style_profile、segmentation_profile
- [x] 8.4 v1 artifact 降级：按 player_id natural sort 分配临时 render_slot（仅前端，不透传回后端）
- [x] 8.5 v1 artifact 降级：按 (player_id, identity_epoch ?? 0) 分组后，使用 continuity helper 按时间 gap 推导临时 segment（不假设一个 epoch 一个 segment）
- [x] 8.6 v1 segment_id 格式：`legacy:{player_id}:e{epoch}:s{segment_index}`
- [x] 8.7 v1 artifact 降级：无 style_profile 时使用 `DEFAULT_COURT_VISUAL_THEME_V1`
- [x] 8.8 归一化输出按 timestamp_seconds 排序
- [x] 8.9 归一化输出包含按 player_id 和 segment_id 建立的索引 map

## 9. 前端 API client

- [x] 9.1 在 `src/services/analysisClient.ts` 中新增 `getPlayerRenderTrajectory(jobId: string): Promise<NormalizedPlayerRenderTrajectory | null>` 方法
- [x] 9.2 请求 `/api/analysis/jobs/{job_id}/artifacts/player-render-trajectories`（复数，与现有路由一致）
- [x] 9.3 404 或无数据时返回 null
- [x] 9.4 500 或网络错误时正常抛出

## 10. 测试 Fixture

- [x] 10.1 新建 `src/test/fixtures/player-render-trajectory.v2.json`
- [x] 10.2 fixture 包含 2 个 player_id、≥2 个 segment（含 visible_gap 断开）、检测帧 + 插值帧
- [x] 10.3 fixture 包含 `players`、`segments`、`samples`、`style_profile`、`segmentation_profile` 完整字段

## 11. 后端单元测试

- [x] 11.1 测试 `_build_roster()` 正确收集并排序所有唯一 player_id
- [x] 11.2 测试 `_assign_render_slots()` 返回确定性映射
- [x] 11.3 测试 `observed_player_count > MAX_RENDER_SLOTS` 时抛出 `RenderSlotOverflowError`
- [x] 11.4 测试 `RenderSlotOverflowError` 被 catch 后仅使 render trajectory artifact failed，不传播
- [x] 11.5 测试 `canonical_player_id()` 规范化混合 case 输入
- [x] 11.6 测试 identity_epoch 变化（上游值不同）触发新 segment，break_before = identity_reset
- [x] 11.7 测试 visible_gap 触发新 segment 但不影响 identity_epoch
- [x] 11.8 测试普通 track ID 重连不产生新 segment（时空连续时）
- [x] 11.9 测试同一 epoch 内连续两个 visible_gap 生成 s0, s1, s2 三个 segment
- [x] 11.10 测试 segment_id 格式为 `{player_id}:e{epoch}:s{index}`
- [x] 11.11 测试 render_slot 在整段输出中一致（不受 epoch/segment 变化影响）
- [x] 11.12 测试 samples 多球员同帧交错，sequence_index 全局唯一
- [x] 11.13 测试同一输入重复执行产出结果一致（render_slot, segment_id, samples 排序均确定）
- [x] 11.14 测试 v2 artifact JSON 结构完整
- [x] 11.15 测试 v1 已有字段兼容
- [x] 11.16 测试无显式 projection 事件时不误判为 projection_gap
- [x] 11.17 测试后半程出现第四名 player_id 时全量 roster 仍稳定分配 slot_4
- [x] 11.18 测试 `process()` 返回完整 `CourtTrackPostProcessResult`
- [x] 11.19 测试 `build_tracks()` 仍返回 `ProcessedCourtTracks`（向后兼容）
- [x] 11.20 运行现有 `test_court_track_postprocessor.py` 全量测试，确认无回归（35/35 通过）

## 12. OverlayVideoWriter 测试

- [x] 12.1 测试 v2 sample segment_id 变化时 deque 被清空（不崩溃，视频正常生成）
- [x] 12.2 测试 v1 sample 无 segment_id 时不清空 deque（向后兼容）
- [x] 12.3 测试 v2 artifact 不存在时回退到 v1 逻辑不变

## 13. 前端测试

- [x] 13.1 测试 normalizer 正确解析 v2 fixture 并产出必填字段完整的 Normalized 输出
- [x] 13.2 测试 v1 降级路径：无 render_slot 时 normalizer 生成临时 slot
- [x] 13.3 测试 v1 降级路径：无 segment_id 时 normalizer 推导临时 segment（同 epoch 内按 gap 断线）
- [x] 13.4 测试 `getPlayerRenderTrajectory()` 404 返回 null
- [x] 13.5 测试 `getPlayerRenderTrajectory()` 500 正常抛出

## 14. 契约测试

- [x] 14.1 验证前端 `DEFAULT_COURT_VISUAL_THEME_V1` 与后端 fixture `style_profile` 内容一致
- [x] 14.2 验证 v2 fixture 通过 normalizer 后 `render_slot` 与原始后端分配一致（不重新排序）

## 15. 验收

- [x] 15.1 同一 player_id 跨 track ID render_slot 不变（11.11 覆盖）
- [x] 15.2 同一 player_id 从 near 换到 far 后 side 变化、render_slot 不变（11.11 覆盖 side 推导）
- [x] 15.3 identity_epoch 递增时 segment_id 变化、render_slot 不变（11.6 + 11.11 覆盖）
- [x] 15.4 visible_gap 产出的 segment 具有 break_before = visible_gap（11.7 覆盖）
- [x] 15.5 identity_epoch 变化产出的 segment 具有 break_before = identity_reset（11.6 覆盖）
- [x] 15.6 OverlayVideoWriter 在 segment_id 变化时清空 deque（12.1 覆盖）
- [x] 15.7 OverlayVideoWriter 在 v1 sample（无 segment_id）时不清空 deque（12.2 覆盖）
- [x] 15.8 前端 normalizer 正确解析 v2 fixture（13.1 覆盖）
- [x] 15.9 旧 v1 artifact 被 normalizer 降级处理（13.2 + 13.3 覆盖）
- [x] 15.10 RenderSlotOverflowError 不传播到 tracking/ball/report（11.4 覆盖）
- [x] 15.11 `build_tracks()` 向后兼容（现有调用方无报错）
- [x] 15.12 现有 `test_court_track_postprocessor.py` 全量测试通过
