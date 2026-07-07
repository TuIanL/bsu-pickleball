## Why

当前分析流水线已经可以产出 tracking、pose、球轨迹、弹跳候选和球员轨迹等事实 artifact，但 visualization 阶段仍然是 skipped，占位说明为“MVP 暂不生成叠加视频文件”。这使 Good-Pickleball 迁移的最后一段能力还没有落地：用户无法直接看到小地图、叠加视频、热力图、散点图等教练友好的可视化输出。

现在已有 `analysis-overlay-video`、`position-heatmaps`、`position-scatter-plots` 的存储路径、API 名称、`AnalysisArtifacts` 字段和配置开关，因此可以在不替换主分析 pipeline 的前提下补齐可视化产物生成与前端消费。

## What Changes

- 新增 Good-Pickleball 可视化输出迁移层，消费现有 tracking、pose、ball trajectory、bounce events 和 player trajectory artifact。
- 生成可选 `analysis_overlay.mp4`，在源视频上绘制人物框、姿态骨架、球轨迹、弹跳候选和小地图面板。
- 生成基于现有标准匹克球场几何的小地图，可绘制球员位置、球轨迹和弹跳点。
- 生成位置热力图和散点图图片，并写入前端可读取的 heatmap / scatter manifest。
- 复用现有 `enable_analysis_overlay_video`、`enable_position_visualizations` 和 `visualization_language` 配置。
- 在 `AnalysisPipeline` 中把 visualization 阶段从固定 skipped 改为可配置、可降级的真实阶段。
- 前端分析结果页读取并展示分析叠加视频、热力图 manifest 和散点图 manifest，并保留禁用或缺失时的稳定不可用状态。
- 增加中英文 overlay label 配置，覆盖 player、ball、bounce、speed、distance 和 frame time 等显示文案。
- 补充 Good-Pickleball 迁移说明，明确本项目使用现有 CourtVision / bsu-pickleball 的 20 ft × 44 ft 球场坐标，不直接照搬 Good-Pickleball 米制常量。

本 change 不做 Kinovea、不做 annotation file persistence、不做 normalized annotation schema、不做 annotation import API、不做人工标注报告、不做 PDF 导出，也不替换现有 `AnalysisPipeline` 主体。

## Capabilities

### New Capabilities

- `visualization-reporting-outputs`: 定义可视化阶段如何从现有分析 artifact 生成叠加视频、小地图、热力图、散点图，以及前端如何展示这些可选输出。

### Modified Capabilities

- `analysis-artifacts`: 扩展位置可视化 manifest item 的字段要求，使每个图像条目能表达标题、描述、文件路径、artifact URL 和来源 artifact 引用。

## Impact

- 后端 vision 层：新增 `backend/app/vision/pickleball_game_analysis/` 下的 minimap、overlay video、position visualization 和 visualization schema 模块。
- 后端 pipeline：更新 `backend/app/services/analysis_pipeline.py` 的 visualization 阶段，设置 `AnalysisArtifacts` 中 overlay video、heatmap manifest、scatter manifest 的 path、url、status 和 detail。
- 后端存储与 API：复用现有 `StorageService` 路径和 `/api/analysis/jobs/{job_id}/artifacts/{artifact_name}` artifact route；必要时补足 manifest image URL 解析约定。
- 前端：更新 `src/types/report.ts`、`src/services/analysisClient.ts` 和分析结果页/视觉工作台组件，以加载和展示可视化 artifact。
- 测试：增加 minimap 坐标映射、overlay writer 降级行为、position visualization manifest、pipeline 配置开关、artifact API 和前端 artifact 状态测试。
- 依赖：优先使用现有 OpenCV / Python 图像栈；若图片图表需要 matplotlib，应保持后端依赖可选或在缺失时优雅降级。
