> **优先级：Optional（可后置）** — 本 spec 中的需求不属于 MVP，可在核心数据链路完成后单独推进。不阻塞结构化热力图和散点图的交付。

## ADDED Requirements

### Requirement: SVG 球场轨迹图增加坐标参考网格

`ReportVisualization.tsx` 中的 SVG 球场图 SHALL 增加浅灰色虚线坐标参考网格，帮助用户直观判断球员在场上的位置区域。

#### Scenario: 球场图显示参考网格
- **WHEN** 球场轨迹图渲染
- **THEN** 在球场区域内绘制浅灰色虚线网格，纵向每 10% 一格、横向每 20% 一格，不超过 6 条线

### Requirement: 轨迹显示球员名称标签

SVG 球场轨迹图 SHALL 在起点和终点附近显示球员名称或编号标签。

#### Scenario: 球员标签显示
- **WHEN** 有 `movementPath` 数据
- **THEN** 在路径起点旁显示 "起点" 标签，终点旁显示 "终点" 标签

### Requirement: 轨迹折线显示方向

SVG 球场轨迹图的轨迹折线 SHALL 用箭头或渐变颜色指示运动方向。

#### Scenario: 方向指示
- **WHEN** 轨迹折线包含至少 2 个点
- **THEN** 折线从起点到终点颜色渐变（浅绿 → 深绿），或在关键转折点显示小箭头标记

### Requirement: 球场图增加图例

SVG 球场轨迹图 SHALL 在右下角或左上角显示图例，说明颜色、标记符号的含义。

#### Scenario: 图例显示
- **WHEN** 球场轨迹图渲染完成
- **THEN** 在图区域一角显示图例卡片，包含 "轨迹路径"、"起点"、"终点"、"球网" 等图例项

### Requirement: MetricCard sparkline 增加面积渐变填充

MetricCard 的 sparkline SHALL 在折线下方增加半透明面积渐变填充，提升视觉层次感。

#### Scenario: 面积填充显示
- **WHEN** MetricCard 渲染 sparkline
- **THEN** 折线下方区域用从当前颜色到透明的垂直渐变填充

### Requirement: MetricCard sparkline 增加平均值参考线

MetricCard 的 sparkline SHALL 显示一条浅灰色虚线标记历史平均值。

#### Scenario: 参考线显示
- **WHEN** sparkline 数据点数量 ≥ 3
- **THEN** 在平均值位置绘制一条浅灰色水平点线

### Requirement: ProgressChart 柱状图增加数值标签

ProgressChart 的每个柱状顶部 SHALL 显示对应的百分比数值。

#### Scenario: 数值标签显示
- **WHEN** ProgressChart 渲染柱状图
- **THEN** 每根柱子的顶部显示对应的整数值，字体加粗

### Requirement: ProgressChart 柱状图 hover 效果

ProgressChart 的柱子 SHALL 在鼠标悬停时放大宽度并显示更详细的数值信息。

#### Scenario: Hover 突出显示
- **WHEN** 用户鼠标悬停在某根柱子上
- **THEN** 该柱子宽度从 2.5 增加到 4，所有同组柱子同时略微突出
