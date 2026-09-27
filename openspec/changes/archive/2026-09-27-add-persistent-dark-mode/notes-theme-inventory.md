# 界面色 / 数据语义色 / 遮挡风险清点

实施 `add-persistent-dark-mode` 时对 `src/` 的实际清点与落地结果。用于逐页巡检（任务 5.2）对照。

## 1. 配色来源（`src/`，272 个 ts/tsx 文件）

| 来源 | 规模 | 处理方式 |
| --- | --- | --- |
| `--capture-*` CSS 变量（`src/index.css`） | 约 25 个文件 | 在 `[data-theme="dark"]` 中整体覆盖，业务代码零改动 |
| Tailwind 任意值硬编码 hex | 324 个不同色值 | 按「工具类前缀 + 原色值」精确映射到 `--ui-*` |
| Tailwind 默认中性色 `slate/gray` | `text-slate-*` 545、`bg-white` 181、`text-white` 85、`bg-slate-*` 73、`bg-black` 35 | `--color-slate-*` / `--color-gray-*` 改指 `--ui-neutral-*` / `--ui-gray-*`，业务代码零改动 |
| `.pb-vision-theme`（`--pb-*`） | 报告作用域 | 界面变量改为引用全局语义变量；维度浅底与米黄卡在暗色下换同色相深底 |
| JS 侧（ECharts / three.js） | ECharts 封装 1 处 + 三维视口 | ECharts 由 `withChartTheme()` 在封装层统一并入界面色；three.js 只改充当界面背景的清屏色 |
| `src/styles/app.css` | 全仓无引用（孤儿文件） | 不纳入 |

## 2. 迁移执行结果

| 步骤 | 结果 |
| --- | --- |
| codemod 第 1 轮（`--ui-*` 主映射 + `bg-white`） | 1319 处 / 68 个文件 |
| codemod 第 2 轮（低频表面、描边、强调色） | 84 处 / 24 个文件 |
| 中性色阶改指语义变量 | `--color-slate-*` / `--color-gray-*`，亮色沿用 Tailwind v4 oklch 原值 |
| 组件层（`.sport-card` / `.glass-panel` / `.green-button` / `.quiet-button` / `.danger-button` / `.field-input`） | 迁入语义色；因 `@apply` 不为 `var()` 生成 color-mix，半透明表面显式写 `color-mix` |
| 修复 codemod 缺陷 | `bg-white/70` 因零宽断言产生 `…/70/70`，共 66 处 / 28 个文件已修正（该写法会让整条类失效） |

保持不变：`text-white`（白字多落在彩色表面上）、`bg-black/*` 与 `<60%` 的半透明白色叠层。
剩余未迁移的硬编码 hex 约 343 处（工具类）+ 154 处（内联 style），集中在视频 HUD、球场绘制、时间轴语义色等舞台/数据表面，见 §3。

## 3. 视为「数据语义色」、暗色下保留含义的部分

- 6 维度专属色（`--pb-dim-*`：紫/蓝/青/橙/金/粉）与热力三段渐变（黄→可视化绿→粉）。
- 时间轴语义色（`--capture-timeline-*`：set/game/rally/highlight/playhead/side-change）。
- 录制与告警（`--capture-status-recording`、`--capture-status-warning`）。
- 场地线、球与球员轨迹、overlay 绘制色、视频 HUD（`#07131B`、`#091016` 等深底本就适合暗色）。
- 品牌装饰色 lime `#D9FF3F`（占比 < 5%）。
- `ShowcaseDisplayPage`（大屏展示）本来就是深色舞台，不受主题影响。

## 4. 遮挡风险与处理

| 位置 | 风险 | 处理 |
| --- | --- | --- |
| landing 顶栏右侧 | 已有「任务历史」按钮 | 主题按钮插入按钮组左侧，同一行，无遮挡 |
| standard / capture 主区域 | 无顶栏；采集控制台标题行右侧已有「存储位置 / 设置」 | 主题按钮固定右上角（`z-[60]`）；`CaptureWorkspaceHeader` 操作区加 `pr-12 sm:pr-14` 预留空间 |
| 弹窗 / 抽屉 | z-index 竞争 | 按钮 `z-[60]` 高于 Modal 遮罩 `z-50`；按钮在右上、弹窗居中，互不遮挡 |
| 窄屏 | 右侧空间紧张 | 按钮 `right-4 sm:right-6`、`size-10`；采集页预留随断点放大 |
| 视频全屏 | 浏览器原生全屏覆盖 | 未处理；退出全屏后按钮恢复可见 |

## 5. 首帧与持久化

- `index.html` 内联启动脚本在样式与 React 首次绘制前写 `data-theme`，缺失／无效／存储不可用一律 `light`。
- React 侧以同一个 `data-theme` 为唯一初始来源，切换时同步 DOM + `localStorage` + 自定义事件；`storage` 事件跟随同源其他标签页。
- 切换瞬间在 `<html>` 挂 `.theme-transition`，切换后移除；系统「减少动态效果」下不加过渡。
- **过渡的性能约束（首版在组件多的页面上点切换会卡，已改）**：
  - 只过渡 `background-color` / `border-color` / `color` 三个属性。**刻意不含 `box-shadow` / `fill` / `stroke`**——这三项要在每个节点上重新光栅化，是卡顿主因；图标走 `currentColor`，父级 `color` 过渡即可，观感无差别。
  - 选择器排除 SVG 子树与媒体元素：`html.theme-transition :where(:not(svg, svg *, img, video, canvas, picture, source))`。
  - CSS 时长 140ms，JS 在 180ms 后摘类（略长于动画，避免元素停在中间色）。
  - 兜底：`theme.ts` 的 `TRANSITION_NODE_BUDGET = 2500`，文档节点数超过即改为瞬时切换，保证重页面不卡；想在所有页面都保留过渡就调大该常量。

## 6. 验证结果（本轮）

- `tsc -b`：通过。
- `npm run build`：通过（含落地页预算检查）。
- 前端全量 `vitest run --maxWorkers=2`：**无新增失败**。失败用例为既有项——`MultiViewAnalysisSetupPage.test.tsx` 3 个（向导走不到提交，既有）。另有 2 个测试文件因沙箱 worker 起不来被跳过（`MultiviewObservabilityPage.test.tsx`、`SyncCalibrationWorkbenchPage.test.tsx`，报 `Timeout waiting for worker to respond`），`AnalysisJobPage.test.tsx` 单个用例 5s 超时，单独复跑通过。
- 因迁移导致的 2 类断言失效已修正（属于预期内，行为未变）：`border-[#2F80ED]` → `border-[var(--ui-info)]`（2 处）、`accent-[#22C55E]` → `accent-[var(--ui-brand)]`（5 处）。
- ESLint：17 个 error，**与 HEAD 版逐文件计数完全一致**（`SegmentManagerPage.tsx` 14、`AnalysisRosterConfirmation.tsx` 2、`SegmentVideoPlayer.test.tsx` 1），均为既有问题。
- `openspec validate --all`：201 passed / 0 failed。

## 7. 亮色基线截图（待人工完成）

任务 1.1 要求保存首页、比赛库、采集、分析、报告的亮色基线截图。这一步属于视觉回归，按项目约定由人工验证，未在本轮自动执行。建议核对入口：

- `/`（首页，landing 壳）
- `/library`（比赛库，standard 壳）
- `/capture`（现场采集，standard 壳）
- `/analysis/tasks`（分析任务，standard 壳）
- `/reports/movement`（报告，standard 壳 + `.pb-vision-theme`）

核对方式：亮色模式下逐页对比迁移前外观（背景、卡片、文字、边框、阴影、交互色应一致，仅新增右上角主题按钮），再切到暗色逐页检查可读性与层级。
