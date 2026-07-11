# visualization-reporting-outputs Specification

## Purpose
Define the visualization and reporting output capabilities migrated from Good-Pickleball, including analysis overlay video generation, minimap rendering, position visualization manifests, and bilingual label support.

## Requirements
### Requirement: Generate analysis overlay video

系统 SHALL 在启用叠加视频并且源视频可用时，生成可选的 `analysis_overlay.mp4`，用于展示分析结果的可视化叠加。

#### Scenario: Overlay video generated from available artifacts

- **WHEN** 已完成的真实分析任务包含源视频和至少一个可渲染 overlay artifact
- **AND** `enable_analysis_overlay_video` 为启用
- **THEN** 系统 SHALL 写入 `outputs/{job_id}/analysis_overlay.mp4`
- **AND** `AnalysisPipelineResult.artifacts.analysis_overlay_video_url` SHALL 指向 `analysis-overlay-video` artifact route
- **AND** `analysis_overlay_video_status` SHALL 表达生成结果。

#### Scenario: Overlay video uses optional layers

- **WHEN** visualization 阶段读取 tracking、pose、ball trajectory、bounce events 或 player trajectory artifact
- **THEN** 系统 SHALL 渲染存在且格式有效的图层
- **AND** 系统 MUST 跳过缺失或不可用的可选图层
- **AND** 系统 MUST NOT 因单个可选图层缺失而使整个分析任务失败。

#### Scenario: Overlay video generation fails gracefully

- **WHEN** 叠加视频生成因视频编码、源视频读取或绘制异常失败
- **THEN** 系统 SHALL 将 `analysis_overlay_video_status` 标记为 `failed` 或 `unavailable`
- **AND** 系统 SHALL 在 `analysis_overlay_video_detail` 中记录可读说明
- **AND** 系统 MUST NOT 将整个分析任务标记为 failed。

### Requirement: Render minimap using standard court geometry

系统 SHALL 使用现有标准匹克球场几何渲染小地图，并将 court 坐标映射到小地图像素坐标。小地图 SHALL 使用 tracking_bounds（x=-4~24, y=-8~52）作为像素映射范围，以显示合理界外点（发球站位、救球出界等）。

#### Scenario: Minimap draws court structure

- **WHEN** 小地图被渲染
- **THEN** 系统 SHALL 绘制球场外边界、球网线、厨房线、中线和发球区结构
- **AND** 绘制 SHALL 基于项目标准 20 ft × 44 ft 球场几何
- **AND** 系统 SHALL 在球场周围绘制浅色 tracking buffer 底纹（x=-4~24, y=-8~52）

#### Scenario: Minimap draws available analysis points

- **WHEN** player trajectory、ball trajectory 或 bounce events 包含有效 court 坐标
- **THEN** 小地图 SHALL 能绘制球员位置、球轨迹和弹跳候选标记
- **AND** 界外但 tracking_bounds 内的点 SHALL 使用半透明/虚线样式显示
- **AND** 超出 tracking_bounds 的点 SHALL 不显示

#### Scenario: 裁切脚点在小地图中的显示

- **WHEN** player point 的 projection_confidence <= 0.35（如 bbox_bottom_clipped）
- **THEN** 小地图 SHALL 使用半透明样式绘制该球员点
- **AND** 轨迹通过该点段 SHALL 使用虚线连接

### Requirement: 前端 SVG 球场图使用 tracking viewBox

前端 SHALL 在 StructuredScatterPlot 和 StandardCourtPlan 组件中使用 tracking viewBox（`-4 -8 28 60`）渲染球场 SVG，确保界外发球/救球点可在前端图表中显示，并与后端 overlay 小地图坐标一致。

#### Scenario: StructuredScatterPlot 显示界外点

- **WHEN** scatter_plots 数据包含 tracking_bounds 内但 court_bounds 外的点坐标（如 x=-2, y=-5）
- **THEN** 该点 SHALL 在 SVG 中可见（不因超出 court viewBox 而被裁切）
- **AND** 该点 SHALL 使用 `trackingToSvg()` 进行坐标映射

#### Scenario: StandardCourtPlan 显示 tracking buffer

- **WHEN** App.tsx 渲染标准球场平面图
- **THEN** SVG viewBox SHALL 为 `-4 -8 28 60`
- **AND** tracking buffer 区域 SHALL 显示浅色虚线背景

#### Scenario: 热力图继续使用 court_bounds

- **WHEN** StructuredHeatmap 渲染球员位置热力图
- **THEN** heatmap 数据 SHALL 只包含 court_bounds（0~20 × 0~44）内的点
- **AND** 界外点 SHALL NOT 计入 heatmap cell 计数

### Requirement: Generate position visualization manifests

系统 SHALL 在启用位置可视化时，从已有轨迹与弹跳 artifact 生成热力图和散点图图片，并写入 manifest。

#### Scenario: Heatmap manifest generated

- **WHEN** `enable_position_visualizations` 为启用
- **AND** player trajectory 中存在可用 court 坐标样本
- **THEN** 系统 SHALL 写入 `position_visualizations/heatmaps/manifest.json`
- **AND** 系统 SHALL 在 heatmap manifest 中列出已生成的 heatmap 图片条目
- **AND** `AnalysisPipelineResult.artifacts.heatmaps_url` SHALL 指向 `position-heatmaps` artifact route。

#### Scenario: Scatter manifest generated

- **WHEN** `enable_position_visualizations` 为启用
- **AND** player trajectory、ball trajectory 或 bounce events 中存在可用 court 坐标样本
- **THEN** 系统 SHALL 写入 `position_visualizations/scatter_plots/manifest.json`
- **AND** 系统 SHALL 在 scatter manifest 中列出已生成的 scatter 图片条目
- **AND** `AnalysisPipelineResult.artifacts.scatter_plots_url` SHALL 指向 `position-scatter-plots` artifact route。

#### Scenario: Position visualization has no valid points

- **WHEN** `enable_position_visualizations` 为启用
- **AND** 没有可转换到标准球场坐标的 player、ball 或 bounce 点
- **THEN** 系统 SHALL 写入 status 为 `unavailable` 或 `no_data` 的 manifest
- **AND** 系统 MUST NOT 将整个分析任务标记为 failed。

### Requirement: Visualization stage respects configuration

系统 SHALL 使用现有配置开关控制可视化输出生成。

#### Scenario: Visualization disabled

- **WHEN** `enable_analysis_overlay_video` 和 `enable_position_visualizations` 均未启用
- **THEN** visualization 阶段 SHALL 标记为 `skipped`
- **AND** 系统 MUST NOT 写入 `analysis_overlay.mp4`、heatmap manifest 或 scatter manifest。

#### Scenario: Partial visualization enabled

- **WHEN** 仅启用 `enable_analysis_overlay_video` 或仅启用 `enable_position_visualizations`
- **THEN** 系统 SHALL 只尝试生成对应类型的可视化输出
- **AND** 未启用的输出 SHALL 在 artifact 字段中保持 null 或 unavailable。

### Requirement: Overlay labels support Chinese and English

系统 SHALL 根据 `visualization_language` 为叠加视频和图片 manifest 提供中英文显示文案。

#### Scenario: Supported visualization language

- **WHEN** `visualization_language` 为 `zh-CN` 或 `en-US`
- **THEN** 系统 SHALL 使用对应语言输出 player、ball、bounce、speed、distance 和 frame time 等标签。

#### Scenario: Unsupported visualization language

- **WHEN** `visualization_language` 是不支持的值
- **THEN** 系统 SHALL 回退到默认语言
- **AND** 系统 MUST NOT 因语言值不支持而使可视化阶段失败。

#### Scenario: Text rendering dependency unavailable

- **WHEN** 中文字体或文字绘制依赖不可用
- **THEN** 系统 SHALL 继续生成非文字图形输出
- **AND** 系统 MAY 跳过相关 label 或使用可用 fallback 文案。

### Requirement: Frontend displays visualization artifacts

前端 SHALL 在分析结果页或视觉工作台读取并展示后端生成的可视化 artifact。

#### Scenario: Overlay video available

- **WHEN** `AnalysisPipelineResult.artifacts.analysis_overlay_video_url` 存在且状态可用
- **THEN** 前端 SHALL 能展示或链接 `analysis_overlay.mp4`
- **AND** 前端 MUST 保留源视频与 JSON overlay 展示路径的兼容性。

#### Scenario: Visualization manifests available

- **WHEN** heatmap manifest 或 scatter manifest URL 存在
- **THEN** 前端 SHALL 请求 manifest JSON
- **AND** 前端 SHALL 根据 manifest items 展示可视化图片及其标题或说明。

#### Scenario: Visualization artifact unavailable

- **WHEN** 叠加视频、heatmap manifest 或 scatter manifest 被禁用、缺失或生成失败
- **THEN** 前端 SHALL 显示稳定的 unavailable、skipped 或 failed 状态
- **AND** 前端 MUST NOT 渲染破损图片、空白视频或未处理异常。

### Requirement: Document Good-Pickleball visualization migration

系统 SHALL 提供迁移说明，记录 Good-Pickleball 可视化能力如何映射到当前项目。

#### Scenario: Migration mapping documented

- **WHEN** 开发者查看迁移文档
- **THEN** 文档 SHALL 说明小地图、叠加视频、热力图、散点图和中英文标签对应的本项目模块与 artifact
- **AND** 文档 SHALL 说明本项目使用 20 ft × 44 ft 标准球场坐标
- **AND** 文档 MUST 明确不包含 Kinovea、annotation import、人工标注报告或 PDF 导出。

### Requirement: style_profile 和 segmentation_profile 快照写入渲染轨迹 artifact

系统 SHALL 在生成 `player_render_trajectory.json` 时将当前渲染配置的 `style_profile` 和 `segmentation_profile` 快照分别写入两个独立字段。

#### Scenario: style_profile 快照包含颜色映射和渲染参数

- **WHEN** visualization 阶段生成 player render trajectory artifact
- **THEN** `style_profile.players` MUST 包含每个 render_slot 的 hex 颜色（slot_1~4）
- **AND** `style_profile` MUST 包含球和弹跳点颜色
- **AND** `style_profile` MUST 包含 `player_trail_seconds`、`ball_trail_seconds`、`bounce_display_seconds`
- **AND** `style_profile` MUST 包含 `radius.min_px` 和 `radius.max_px`

#### Scenario: segmentation_profile 快照包含分段算法参数

- **WHEN** visualization 阶段生成 player render trajectory artifact
- **THEN** `segmentation_profile` MUST 包含 `jump_threshold_ft`、`max_visible_gap_seconds`
- **AND** `segmentation_profile.version` MUST 独立于 `style_profile.version`

#### Scenario: 主题和分段参数独立演进

- **WHEN** 主题资源文件升级为 `court-visual-theme.v2`（仅颜色变更）
- **AND** artifact schema 仍为 `player-render-trajectory.v2`
- **THEN** `style_profile.version` MUST 为 `court-visual-theme.v2`
- **AND** `segmentation_profile.version` MUST 仍为 `court-track-segmentation.v1`
- **AND** `schema_version` MUST 仍为 `player-render-trajectory.v2`

#### Scenario: 资源文件不可用时 fallback

- **WHEN** 后端无法读取 `court_render_profile.v1.json` 资源文件
- **THEN** 系统 SHALL 使用内置默认 profile 生成 style_profile 和 segmentation_profile 快照
- **AND** 系统 MAY 记录警告日志
- **AND** 系统 MUST NOT 因资源文件缺失导致 artifact 生成失败

### Requirement: style_profile 不影响现有 OverlayVideoWriter 渲染行为

系统 SHALL 在 artifact 中携带 style_profile 快照，但在本 Change 中不得改变 OverlayVideoWriter 的颜色或标记渲染逻辑。

#### Scenario: OverlayVideoWriter 行为不变

- **WHEN** OverlayVideoWriter 消费 v2 artifact 渲染分析叠加视频
- **THEN** 颜色、标记大小、线宽 MUST 与消费 v1 artifact 时一致
- **AND** 仅 segment_id 变化时清空 deque（新增行为除外）
