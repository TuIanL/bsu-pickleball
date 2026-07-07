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

系统 SHALL 使用现有标准匹克球场几何渲染小地图，并将 court 坐标映射到小地图像素坐标。

#### Scenario: Minimap draws court structure

- **WHEN** 小地图被渲染
- **THEN** 系统 SHALL 绘制球场外边界、球网线、厨房线、中线和发球区结构
- **AND** 绘制 SHALL 基于项目标准 20 ft × 44 ft 球场几何。

#### Scenario: Minimap draws available analysis points

- **WHEN** player trajectory、ball trajectory 或 bounce events 包含有效 court 坐标
- **THEN** 小地图 SHALL 能绘制球员位置、球轨迹和弹跳候选标记
- **AND** 小地图 MUST 跳过无法转换到标准球场坐标的点。

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
