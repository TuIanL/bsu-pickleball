## Why

视频分析结果界面（`VisionPage` 的 `VideoAnalysisCard`）存在三处面向用户的无效/误导信息，偏离"视频优先、状态辅助"的产品定位：位置热力图把内部网格坐标（第几行第几列、次数、`max_count` 数值）直接暴露给用户；真实任务的视频标题右侧比分胶囊显示占位符 "MVP"；视频下方四张检测信息卡把后端 artifact 的 detail 文案（检测计数、骨架数、球轨迹、弹跳候选）堆给用户。这些都是开发期诊断信息，不是服务球员的数据。

## What Changes

- **位置热力图清理开发向信息**（`StructuredHeatmap.tsx`）：移除 hover tooltip「第X行第Y列: Z 次」及 hover 高亮交互；移除颜色图例（含右侧 `max_count` 数字刻度，如 181）。保留格点热力图本体（22×10 网格），`max_count` 仍仅用于内部配色归一化，后端数据契约不变。
- **标题去除 MVP 占位**（`VideoAnalysisCard.tsx` 的 `VideoCardHeader`）：比分胶囊仅在存在真实比分时显示（demo 为 "11 - 8"），真实任务中的占位符 "MVP" 不再渲染。
- **移除视频下方四张检测信息卡**（`RealVideoFooter` 组件）：删除 YOLO 人体框 / RTMPose 骨架 / 球轨迹 / 弹跳候选 四张卡片及其 status/detail 文案，删除整个 `RealVideoFooter` 组件并清理失效的 props。视频播放层仍保留球轨迹、弹跳、骨架、人体框的 artifact 叠加数据，仅移除 footer 的展示层。

## Capabilities

### New Capabilities

无（本次为 UI 清理，不引入新能力）。

### Modified Capabilities

- `structured-heatmap`: 删除「Hover 时显示网格计数」与「显示颜色标尺」两个需求场景；热力图仍按 `count / max_count` 配色渲染格点，数据契约、空网格与 PNG 降级行为不变。
- `visual-analysis-workspace`: 完成态真实任务视频视图不再渲染四张 artifact 可用性卡片，标题头不再显示 MVP 占位比分胶囊；图层状态仍通过视频内状态徽章与图层开关呈现。

## Impact

- **前端代码**：
  - `src/components/platform/StructuredHeatmap.tsx` —— 删除 hover 状态/tooltip/高亮与 `ColorLegend` 组件。
  - `src/components/platform/VideoAnalysisCard.tsx` —— 删除 `RealVideoFooter` 组件、`VideoCardHeader` 的 MVP 占位胶囊渲染逻辑。
  - `src/pages/VisionPage.tsx` —— 清理传给 `VideoAnalysisCard` 的四张卡片相关 props（`*Detail` / `*Status` / `*LoadState`）以及 `RealVideoFooter` 的移除。
- **后端**：零改动。`visual_grid` / `max_count` 数据契约不变，`analysis_pipeline.py` 的 detail 文案保留（仍作为 artifact detail 供调试，只是不再在 UI 展示）。
- **测试**：`VideoAnalysisCard.test.tsx` 现有断言不涉及四张卡片与 MVP 胶囊（仅弹跳图层开关），预计无破坏；`StructuredHeatmap` 无现有测试文件。若删除后类型校验报错需顺带修引用。
