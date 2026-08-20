## MODIFIED Requirements

### Requirement: 热力图组件新增 PB Vision 亮色渐变配色能力
`StructuredHeatmap`、`displayHeatmap`、`StructuredZoneHeatmap` 等热力图渲染组件 SHALL 支持通过 prop `colorScheme` 或 CSS variable 指定色板；当传入 `"pb-vision"` 时，热力图的 visualMap 颜色梯度 SHALL 为「黄 (#FBBF24) → 绿 (#00FF41) → 粉 (#EC4899)」三段式渐变。

#### Scenario: 调用热力图时传入 pb-vision 色板
- **WHEN** 报告页的 Court Coverage 模块调用热力图组件，并传入 `colorScheme="pb-vision"`
- **THEN** 组件 SHALL 加载黄→绿→粉三色渐变色板
- **AND** 其余渲染行为（legend、坐标、球场底图）SHALL 保持与默认色板完全一致

#### Scenario: 不传 colorScheme 时保持旧配色
- **WHEN** 其他页面或组件调用热力图且未指定 colorScheme
- **THEN** 热力图 SHALL 保持改造前的默认深绿系渐变配色，视觉不得有变化

---

### Requirement: 全局 CSS 变量新增 PB Vision 主题集合
前端样式系统 SHALL 在不删除现有深绿主题变量的前提下，新增一套以 `--pb-` 前缀命名的 PB Vision 亮色主题 CSS 变量（含主色/次色/页面背景/卡片色/文字色 + 六维度紫/蓝/青/红橙/金/粉 + 热力图渐变三段）。报告页 PB 风格容器 SHALL 作用域化加载这些变量，其他页面 SHALL 不感知。

#### Scenario: 报告页加载时 PB 变量生效
- **WHEN** PbVisionReportLayout 组件挂载
- **THEN** 其根 DOM SHALL 有 class `pb-vision-theme`，并在该作用域下定义 `--pb-primary: #00FF41` 等全部 PB 变量
- **AND** 该 class 外部的任何 DOM 元素 SHALL 无法直接命中 `--pb-` 变量（保持无副作用）
