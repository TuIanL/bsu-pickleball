## MODIFIED Requirements

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

## ADDED Requirements

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
