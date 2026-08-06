## 1. 位置热力图清理开发向信息

- [x] 1.1 在 `src/components/platform/StructuredHeatmap.tsx` 删除 hover 相关代码：`hovered` state、`onMouseEnter`/`onMouseLeave`、hover 高亮描边 rect 与「第X行第Y列: Z 次」tooltip div
- [x] 1.2 删除 `ColorLegend` 组件定义及其渲染调用，删除 `grid`/`cells` 不再使用的 `cursor-pointer`/`transition-opacity` 等 hover 样式
- [x] 1.3 保留格点渲染与内部 `colorScale`（仍用 `grid.max_count` 做 0→max 归一化配色），确认 `max_count` 不再作为展示信息

## 2. 视频标题去除 MVP 占位比分

- [x] 2.1 在 `src/components/platform/VideoAnalysisCard.tsx` 的 `VideoCardHeader` 中，仅在 `match.score` 非空且不等于 `"MVP"` 时渲染右侧比分胶囊，否则不渲染该胶囊

## 3. 删除视频下方四张检测信息卡

- [x] 3.1 删除真实视频分支中 `{!compact ? <RealVideoFooter …/> : null}` 渲染块（`VideoAnalysisCard.tsx` 约 136–155 行）
- [x] 3.2 删除 `RealVideoFooter` 组件定义（`VideoAnalysisCard.tsx` 约 917–986 行）及其四张卡片渲染
- [x] 3.3 确认 `VideoAnalysisCard` 的 props 签名与 `src/pages/VisionPage.tsx` 的传参保持不变（`*Detail`/`*Status`/`*LoadState` 仍被 `RealVideoOverlay` 的图层开关与视频内状态徽章使用）

## 4. 验证

- [x] 4.1 运行 `npm run build`（`tsc -b && vite build`）确认类型与构建通过
- [x] 4.2 运行 `npm run lint` 确认无 lint 报错（特别检查删除后是否残留未使用的 import/props）
- [x] 4.3 运行 `npm test` 确认 `VideoAnalysisCard.test.tsx` 等相关测试通过（图层开关、弹跳标记行为不受影响）
- [x] 4.4 手动验证：打开一个完成态真实任务（如 job-904ae682c1）的视频分析页，确认（a）热力图无 hover tooltip、无颜色刻度图例；（b）标题右侧无 "MVP" 胶囊；（c）视频下方无四张检测信息卡；（d）视频内图层叠加与状态徽章仍正常
