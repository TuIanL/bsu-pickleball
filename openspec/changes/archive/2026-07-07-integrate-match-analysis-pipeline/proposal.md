## Why

球轨迹与弹跳检测的核心引擎（`BallTracker`、`BounceDetector`、`TrajectoryCleaner`）已在 Change 1 和 Change 2 中实现并迁移到 `pickleball_game_analysis/`，且 `AnalysisPipeline` 中已半嵌入式运行（球检测在 `_run_tracking()` 循环内执行、后处理在循环末尾完成、artifact 槽位已在 `StorageService` 和 `AnalysisArtifacts` 中预留）。当前状态约完成 70%，但存在三个结构性问题：**球逻辑与人体 tracking 耦合在同一个方法中**（`_run_tracking()` 超过 400 行）、**ball_overlay.json 产物缺失**（路径和 URL 字段已定义但从未写入）、**ball/bounce 阶段对前端不可观测**（无 progress callback、无完整 counters）。本次变更的目标不是"从零接入"，而是将已半嵌入的逻辑收敛为可测试、可通知进度、可完整产出 artifact 的正式 pipeline stage。

## What Changes

- 新增 `ball_overlay.json` 产物写入（帧级球检测叠加数据，**只包含有球分析记录的抽样帧**，不强行补全每一帧）
- 将 `_finalize_ball_analysis()` 中的三个阶段收敛为两个用户可见阶段：`ball-trajectory` 和 `bounce-detection`（移除独立的 `ball-detection` 阶段，将检测信息并入 `ball-trajectory` 的 counters）
- 为 `ball-trajectory` 和 `bounce-detection` 阶段增加完整的 counters 和 progress callback 通知
- 新增配置项 `PICKLEBALL_BALL_ANALYSIS_STRICT`（默认 `false`），控制球分析链路异常是否拖垮整个 pipeline
- 从 `_run_tracking()` 中提取 `_process_ball_frame()`（逐帧球检测逻辑）和 `_run_bounce_detection()`（轨迹清洗+弹跳检测后处理），保留单视频读取循环
- 引入局部 `_BallRunContext` 数据类替代分散的实例状态变量，避免跨任务复用时的隐性 bug
- 在 metrics summary 中增加球轨迹与弹跳点摘要字段
- 新增 `app/schemas/ball.py` 提供球分析产物的 Pydantic 模型
- 保持现有人体 tracking / pose / serve 流程不受影响（**BREAKING**: 无破坏性变更，现有 artifact schema 字段语义不变）

## Capabilities

### New Capabilities
- `ball-overlay-artifact`: 定义 `ball_overlay.json` 的 schema、写入逻辑和 API 读取路径，产出帧级球检测叠加数据（image-space bbox/center/confidence + court-space point），前端可通过 `/artifacts/ball-overlay` 读取

### Modified Capabilities
- `match-analysis-pipeline-capabilities`: 将 pipeline stages 从含 `ball-detection` 的三阶段收敛为 `ball-trajectory` + `bounce-detection` 两个用户可见阶段；增加 strict mode 失败行为要求；为每个新增阶段增加完整 counters 和 progress callback 要求
- `ball-tracking`: 更新球检测 artifact 要求，将 `ball_overlay.json` 纳入"球检测启用且有候选时的产物"清单；明确 `ball_overlay.json` 与 `ball_trajectory.json` 的职责边界（前者是逐帧叠加数据、后者是轨迹连续采样）
- `analysis-artifacts`: 将 `ball_overlay.json` 的 schema 结构、coverage 元数据和 API 读取路径写入 artifact 合同

## Impact

- **`backend/app/services/analysis_pipeline.py`**: 主要变更文件 —— 提取 `_process_ball_frame()`、`_run_bounce_detection()`，重构 `_finalize_ball_analysis()` 的阶段逻辑，新增 `_BallRunContext` 数据类，增加 progress callback 和 strict mode 逻辑
- **`backend/app/vision/pickleball_game_analysis/detection_writer.py`**: 新增 `build_ball_overlay_payload()`
- **`backend/app/schemas/ball.py`**: 新建 —— `BallOverlayFrame`、`BallOverlayArtifact` 等 Pydantic 模型
- **`backend/app/schemas/pipeline.py`**: `AnalysisArtifacts` 已含 `ball_overlay_*` 字段（无需修改）；`PipelineStageResult` 的 `counters` 字段将被填充（无需 schema 变更）
- **`backend/app/core/config.py`**: 新增 `ball_analysis_strict` 配置项
- **`backend/app/api/routes_analysis.py`**: `ball-overlay` 路由已存在（无需修改）
- **`backend/app/services/storage_service.py`**: `ball_overlay_json_path` 已存在（无需修改）
- **测试文件**: 新增 `test_analysis_pipeline_ball.py` 或等价测试，覆盖成功路径、球模型不可用、非 strict 失败、strict 失败四个场景
