## Context

当前可视化管道：后端 `PositionVisualizer` 用 OpenCV 绘制 220×420 PNG → `AnalysisArtifacts` 记录 manifest URL → 前端 `<img>` 标签显示，图片被放大后模糊。

后端存在两套独立的热力图数据：`PositionVisualizer` 用 22×10 网格绘制 PNG，`heatmap_generator.py` 用 11×5 网格输出结构化 `Heatmap` 数据嵌入 `PerformanceMetrics`。两组数据粒度不一致，22×10 的数据从未暴露给前端。

`PositionVisualizer` 当前承担了"计算 22×10 网格 + 绘制 OpenCV PNG"两个职责。如果再叠加 JSON 序列化输出，它会变成"既算数据、又画图、又写文件"的大类，不利于后续扩展（如前端 SVG 渲染、新增可视化类型）。

前端已有 SVG 手绘球场轨迹图（`ReportVisualization.tsx`），但 viewBox 设计为 100×72，线条细弱，缺少图例、网格和标签。MetricCard sparkline 和 ProgressChart 同样缺乏视觉层次。

## Goals / Non-Goals

**Goals (MVP):**
- 后端构建 `StructuredVisualizationData`，与 `PositionVisualizer` 的 PNG 绘制职责分离
- 后端新增 `/visualization-data` API 暴露结构化数据
- 前端从结构化数据渲染热力图和散点图，达到矢量高清、可交互
- 旧 PNG 保留作为 fallback 降级方案
- 旧 job / 运行中 job / 数据缺失场景下前端不崩溃

**Future Goals (Optional，不纳入 MVP 验收):**
- SVG 球场轨迹图增加坐标网格、球员标签、方向箭头、图例
- MetricCard sparkline 增加面积渐变填充和参考基线
- ProgressChart 增加数值标签和 hover 效果

**Non-Goals:**
- 不替换后端视觉检测/跟踪算法
- 不涉及视频叠加层（overlay video）的改进
- 不引入 React 图表库（如 Recharts）—— 优先用 D3 辅助 SVG 手写

## Decisions

### 决策 1：D3.js 仅用于颜色插值和坐标映射，不用于 DOM 操作
- **选择**：安装 `d3-scale`、`d3-interpolate`、`d3-array` 三个子包，不安装全量 D3
- **理由**：热力图需要从 count 到颜色的连续插值（蓝→绿→黄→红），D3 的 `scaleQuantize` 和 `interpolateRgbBrewer` 是最成熟的方案。球场图、sparkline 等用原生 SVG 手写，不需要 D3 的 DOM 操作能力
- **替代方案**：纯 CSS 颜色映射（表达能力不足）；全量 D3（包体积 ~80KB gzipped 不必要）

### 决策 2：后端新增 `/visualization-data` 端点，不修改现有 manifest 端点
- **选择**：新增 `GET /api/analysis/jobs/{job_id}/visualization-data` 返回 `StructuredVisualizationData` JSON
- **理由**：现有 `GET .../position-heatmaps` 返回的是旧 manifest JSON（含 PNG URL），改动它会同时影响 PNG fallback 逻辑，风险较高。新增端点干净分离新旧两条数据流
- **格式**：前端通过 `getStructuredVizData(jobId)` 调用，返回 `{ court, heatmaps, scatter_plots, player_trajectories }`
- **失败处理**：旧 job 或无数据时返回 404（非空 JSON），前端据此判断降级

### 决策 3：热力图网格用 22×10，schema 中明确区分为 visual_grid
- **选择**：后端暴露的网格为 22 行 × 10 列，在 schema 中命名为 `heatmaps.visual_grid`
- **理由**：22×10 是当前 PNG 渲染使用的粒度，网格密度足以清晰展示位置分布模式。11×5 太粗，每格代表 2ft×4.4ft，无法区分精细的站位模式
- **约定**：`visual_grid`（22×10）只用于前端可视化渲染，不写入 `PerformanceMetrics` 指标层; `PerformanceMetrics.Heatmap`（11×5）继续用于报告粗粒度指标。任何新增方都不应混淆两套网格的用途
- **代价**：22×10 = 220 个网格 cell，JSON 体积约增长 4 倍，但对现代网络和前端渲染而言微不足道

### 决策 4：球场轨迹图 viewBox 从 100×72 改为 1000×720
- **选择**：放大 viewBox 10 倍，提高坐标精度、支持更细的线条宽度和圆角
- **理由**：当前 100×72 下线条宽度只能以 0.5-1.6 为单位，差异不明显。1000×720 下可以用 3-16 的整数宽度，精细控制视觉层次
- **注意**：此项属 Optional UI 美化，不纳入 MVP。核心是 `courtGeometry.ts` 坐标映射工具（20ft×44ft → SVG viewBox），这与 viewBox 具体值解耦

### 决策 5：新增 PositionVisualizationDataBuilder，与 PositionVisualizer 职责分离
- **选择**：不修改 `PositionVisualizer.generate()` 同时写 PNG 和 JSON，而是新建 `PositionVisualizationDataBuilder` 负责从检测/跟踪数据构建 `StructuredVisualizationData`
- **理由**：`PositionVisualizer` 当前已承担"计算 22×10 网格 + 绘制 PNG"两个职责。再加 JSON 序列化会让它变成"既算数据、又画图、又写文件"的大类。拆出 Builder 后：
  - `PositionVisualizationDataBuilder.build()` → 返回 `StructuredVisualizationData`
  - `PositionVisualizer.generate()` → 消费 `StructuredVisualizationData` 绘制 PNG
  - 前端同样消费 `StructuredVisualizationData` 渲染 SVG
  - 以后 PNG 只是一个消费者，不是唯一产出
- **替代方案**：在 `PositionVisualizer.generate()` 内新增 JSON 写入（可工作但让类职责更重）

## Risks / Trade-offs

- **[旧 job 无结构化数据]** 已存在的分析结果不包含 structured JSON。→ `GET /visualization-data` 返回 404，前端检测后降级显示 PNG
- **[运行时数据不可用]** 分析任务正在运行中，structured JSON 尚未生成。→ 同上，返回 404 或空，前端降级
- **[部分字段缺失]** structured JSON 某些字段损坏或缺失。→ 前端逐字段检查完整性，缺失字段对应组件局部 fallback，不崩溃整个报告页
- **[网格数据不一致]** 后端两套热力图网格（22×10 vs 11×5）可能让人困惑。→ schema 中明确命名为 `visual_grid` 和 `metrics_heatmap`，文档说明各自用途
- **[D3 版本兼容]** D3 v7 子包与 React 19 可能存在 ESM 兼容问题。→ 安装时指定 `d3-scale@4` `d3-interpolate@3` `d3-array@3`，并用 `import * as d3Scale from 'd3-scale'` 方式引用
- **[JSON 体积]** 完整 22×10 热力图 + 轨迹坐标可能达到数百 KB。→ 对坐标点精简序列化（`[x,y]` 元组而非对象数组），gzip 传输后体积可忽略
