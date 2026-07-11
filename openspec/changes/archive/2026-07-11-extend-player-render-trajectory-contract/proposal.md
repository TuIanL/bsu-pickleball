## Why

当前 `player_render_trajectory.json`（来自 `smooth-minimap-player-motion`）只包含逐帧坐标和基础元数据，缺少渲染所需的身份槽位（`render_slot`）、分段信息（`segment_id`）、投影质量字段和视觉主题快照。前端三个球场可视化组件各自独立推导颜色和断线规则，导致跨组件颜色不一致、轨迹分段不可靠、无法按时间窗口过滤。本变更将渲染轨迹 artifact 从 v1 升级为 v2，在不破坏现有 OverlayVideoWriter 消费者的情况下，为前端小地图、球场轨迹图和散点图提供统一的渲染数据契约。

## What Changes

- **扩展 `CourtTrackPostProcessor`**：新增全局 roster 建立、`render_slot` 一次性分配、`(player_id, identity_epoch)` 分段、`segment_id` 生成、segment metadata 构建、`style_profile` 快照注入
- **扩展 `player_render_trajectory.json`**：schema 升级为 `player-render-trajectory.v2`，新增 `players`（球员元数据列表）、`segments`（分段元数据列表）、`style_profile`（视觉主题快照）。`samples` 数组保持扁平结构作为唯一数据真源，新增 `sequence_index`、`render_slot`、`side`、`segment_id`、`identity_epoch`、投影质量字段。**BREAKING**：`samples[].render_slot` 为必填字段（v2 语义），但 v1 consumer 可通过 `?` 安全忽略
- **扩展前端 TypeScript 类型**：新增 `PlayerRenderTrajectoryV2`、`RenderPlayerMetadata`、`RenderSegmentMetadata`、`NormalizedPlayerRenderTrajectory`，提供 v1/v2 归一化函数
- **扩展前端 client**：新增 `getPlayerRenderTrajectory()` 方法，封装 artifact API 请求与归一化逻辑
- **保持 OverlayVideoWriter 兼容**：继续消费扁平 `samples` 数组，仅在 `segment_id` 变化时清空该球员 deque，不做结构性重写

## Capabilities

### New Capabilities
- `player-render-trajectory-v2`: 扩展的渲染轨迹契约，包含渲染身份槽位、分段元数据、投影质量字段和视觉主题快照

### Modified Capabilities
- `render-trajectory`: CourtTrackPostProcessor 新增 roster 建立与 render_slot 分配逻辑；artifact schema 从 v1 升级为 v2
- `analysis-artifacts`: 新增 `player-render-trajectory` artifact 类型注册（若尚未注册）；PipelineResult.artifacts 扩展渲染轨迹字段
- `visualization-reporting-outputs`: vision stage 输出新增 style_profile 快照

## Impact

**后端**：
- `backend/app/vision/pickleball_game_analysis/court_track_types.py` — 新增 RenderSlot、RenderPlayerMetadata、RenderSegmentMetadata、CourtTrackPostProcessResult；RenderFrame 新增字段
- `backend/app/vision/pickleball_game_analysis/court_track_postprocessor.py` — 新增 `_build_roster()`、`_assign_render_slots()`、`_build_segments()`；扩展现有 `build_tracks()` 流程
- `backend/app/vision/pickleball_game_analysis/visualization_schemas.py` — 新增 `player_render_v2_points_from_artifact()` 解析函数；CourTVisualizationStyleProfile dataclass
- `backend/app/services/analysis_pipeline.py` — `_run_tracking` 末尾调用 PostProcessor 新接口，写出 v2 artifact
- `backend/app/resources/court_visual_theme.v1.json` — 新增视觉主题资源文件
- `backend/app/vision/pickleball_game_analysis/overlay_video_writer.py` — segment_id 变化时清空 deque（微调）

**前端**：
- `src/types/report.ts` — 新增 PlayerRenderTrajectoryV2 等类型
- `src/services/analysisClient.ts` — 新增 `getPlayerRenderTrajectory()` 方法
- `src/test/fixtures/player-render-trajectory.v2.json` — 新增测试 fixture
