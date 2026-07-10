## Why

分析视频右上角小地图的球员移动存在明显卡顿：位置停滞 300-500ms 后突然跳变，播放时球员标记呈"停一下→跳一下"的规律性冻结。根本原因是坐标平滑器将正常抽帧间隔误判为数据缺失进行冻结保持，且渲染路径缺乏逐帧位置生成。

## What Changes

- **新增** `CourtTrackPostProcessor`：独立于现有指标链路的轨迹后处理模块，消费原始投影坐标和稳定 player_id，生成逐帧渲染轨迹
- **新增** `CourtTrackObservation` / `CourtTrackEvent` 数据结构：显式传递分段所需状态，不污染 `ProjectedTrackPoint`，不让 PostProcessor 直接读取三个 Manager
- **新增** `player_render_trajectory.json` artifact：独立于现有 `player_trajectory.json`，Overlay 优先消费，指标和静态可视化完全不使用
- **新增** Artifact API 路由 `GET /api/analysis/jobs/{job_id}/artifacts/player-render-trajectories`
- **修改** `analysis_pipeline.py`：在 smoother 前保存原始坐标，通过 diagnostics cursor 收集身份事件，在 `_run_tracking` 末尾调用 PostProcessor
- **修改** `overlay_video_writer.py`：从帧索引表 + 逐帧 deque 读取渲染轨迹，停止使用 `_points_until_time`
- **修改** `_run_visualization`：将 `player_points` 拆分为 `metric_player_points` 和 `render_player_points`，静态可视化仅消费指标点
- **新增** `VisualizationConfig.minimap_player_trail_seconds`：球员拖尾改为时间定义，保留 `trail_length` 用于球轨迹

不修改 `court_position_smoother.py` 和 `player_identity.py` 的现有行为。不修改 `PlayerLockManager` 的 player_id 格式。指标链路和静态可视化完全不受影响。

## Future Work（不在本 Change 范围内）

- Kalman + RTS 离线平滑（替代线性插值）
- `PlayerLockManager` player_id 格式统一与 `track_identity_hints` 修复
- 前端 `StandardCourtPlan` 的 96 点采样限制调整
- 小地图超采样渲染

## Capabilities

### New Capabilities
- `render-trajectory`: 独立于指标计算的渲染轨迹生成管线。消费原始投影坐标，经过分段、异常点过滤、逐帧线性插值，输出用于小地图视频的逐帧位置序列

### Modified Capabilities
- `visualization-outputs`: Overlay 视频的小地图数据源从 `player_trajectory.json` 改为 `player_render_trajectory.json`；静态热力图/散点图不受影响
- `analysis-artifact-access`: 新增 artifact 类型 `player-render-trajectories` 及其 API 路由

## Impact

| 范围 | 影响 |
|------|------|
| `backend/app/vision/.../court_track_postprocessor.py` | 新增：轨迹后处理核心模块 |
| `backend/app/vision/.../court_track_types.py` | 新增：Observation / Event 数据结构 |
| `backend/app/services/analysis_pipeline.py` | 修改：保存原始坐标，收集观测与事件，在 `_run_tracking` 末尾调用 PostProcessor |
| `backend/app/vision/.../overlay_video_writer.py` | 修改：帧索引表 + deque 读取渲染轨迹 |
| `backend/app/vision/.../visualization_schemas.py` | 修改：新增 `minimap_player_trail_seconds`，新增 `player_render_points_from_artifact()` |
| `backend/app/services/routes_analysis.py` | 修改：新增 artifact 白名单和路由分支 |
| `backend/app/services/storage_service.py` | 修改：新增 artifact 路径 |
| `backend/app/schemas/` | 新增 render trajectory artifact schema |
| `backend/app/vision/.../player_identity.py` | 不修改行为 |
| `backend/app/vision/.../court_position_smoother.py` | 不修改行为 |
| `backend/app/vision/.../player_lock_manager.py` | 不修改行为 |
| `player_trajectory.json` / metrics / heatmaps | 完全不变 |
