## Context

`MultiViewAnalysisSetupPage`（`src/pages/MultiViewAnalysisSetupPage.tsx`，929 行）当前把双摄分析的前置准备拆成 6 步线性流程（`SetupStep = 0..5`）：素材检查 / A 球场 / B 球场 / A 球网 / B 球网 / 名册确认。每完成一路标定即 `setStep(next)` 翻页，其中两次翻页（A 球场→B 球场、A 球网→B 球网）只是为了把同一件事换一路视频再做一遍。

两个标定组件都被单摄流程复用，不能改动其既有语义：

- `CourtCornerCalibrator`：元素级 `setPointerCapture`，无 window 级监听；自带 `section` 边框、双重标题、「确认并启动分析」提交按钮、`sm:grid-cols-4` 点位摘要；挂载即自动触发一次 `requestAutomaticCalibration`。
- `NetProfileCalibrator`：内部为 `lg:grid-cols-[minmax(0,1.35fr)_minmax(260px,0.65fr)]`（右侧参数面板最小 260px），拖拽用 window 级 `pointermove/pointerup`（靠各自 `dragRef` 互斥），`data-testid` / `aria-label` 已按 `viewId` 区分；profile 参数（`mode` / `endpointCm` / `centerCm` / `confirmed`）目前由每个实例自己持有。

页面容器为 `mx-auto max-w-5xl`；standard/capture shell 有 216px 固定侧边栏（`main` 为 `ml-16 sm:ml-[216px]`），因此并排宽度必须按「视口宽 − 侧边栏 − padding」估算。

数据层无需改动：四个标定结果 `calibrationA/B`、`netAnnotationA/B` 与 `saveMetricCourtSceneDraft` / `validateMetricCourtScene` / `publishMetricCourtScene` / `createMultiviewAnalysisJob` 的 payload 结构均保持原样。

## Goals / Non-Goals

**Goals:**

- 把首次进入新任务所需的「下一步」点击数从 5 次降到 2 次（6 步 → 3 步）。
- 球场标定与球网标定各自在**同一页**内完成 A/B 两路，宽屏并排、窄屏纵向堆叠。
- 球网高度 profile 收敛为唯一一份，消除 B 侧高度输入被静默丢弃的缺陷。
- 「机位朝向」在标定之前确定，使球网左右端的 canonical 语义在标注时已正确。
- 素材与同步前置信息变为常驻状态条，任何阶段都能看到阻断原因。
- 单摄流程（`NewAnalysisPage` / `RecordingAnalyzePage`）的组件行为与外观零变化。

**Non-Goals:**

- 不改后端契约、不使用新的 API、不改 `metric_court_scene.v1` 的字段结构。
- 不做摄像头安装角色自动推断（仍由用户人工确认朝向）。
- 不引入「两路镜像联动拖点」（两路图像坐标系不同，无法互相推算点位）。
- 不修本次触碰到的既有测试失败（如基线中 `MultiViewAnalysisSetupPage.test.tsx` 的既有 3 条），只报告。
- 不优化外接盘素材读取与后端自动标定推理性能。

## Decisions

### D1：三阶段划分 = 标定（球场）/ 标定（球网）/ 名册与确认

原「素材检查」不再是独立步骤，而是**页面顶部常驻状态条**（A/B 视频就绪、录制状态、同步锚点状态及阻断提示与「开始/继续标注」入口）。其「分析配置」三项（仅分析指定窗口、Debug Replay、分析流程选择）下移到「名册与确认」阶段。

新 `SetupStep = 0 | 1 | 2`：`球场标定` → `球网标定` → `名册与确认`。

- 选择理由：球网标定是「三点 + 两点」标注，与球场四角拖动是两种不同的交互范式，且球网左右端语义依赖朝向，保留为独立步骤比塞进同一屏可读性更好；而素材检查的信息天然适合常驻可见（它随时可能因为同步锚点失效而需要重新阻断）。
- 备选方案（否）：把球场与球网也压进同一屏（2 步）——一屏内同时容纳 2 个四角标定器与 2 个球网标定器，纵向过长且心智负担重。

### D2：并排容器断点用 `xl:`，容器宽度放宽到 `max-w-7xl`

```
并排（≥1280px 视口）：容器 ≈ min(1280, 视口−216−padding) → 每侧 ≈ 500–620px
堆叠（<1280px 视口）：每侧全宽
```

- 关键约束：若并排断点取 `lg`（1024px），每侧仅约 470px，而 `NetProfileCalibrator` 内部**同样**在 `lg` 触发两列布局（视频 + 260px 参数面板），会在 470px 里塞两列而崩坏。取 `xl` 可让并排只在大屏发生，且每侧宽度足以容纳紧凑单列。
- 嵌入模式下**强制**组件内部为单列（忽略其 `lg:grid-cols-[...]`），由 `variant="embedded"` 控制。
- 容器由 `max-w-5xl` 改为 `max-w-7xl`，让大屏（1920）时每侧达到约 620px，保留拖点精度。

### D3：组件新增 `variant` / 文案 props，默认值保持单摄外观

- `CourtCornerCalibrator`：新增 `variant?: "standalone" | "embedded"`（默认 `standalone`）、`title?: string`、`submitLabel?: string`（默认沿用「确认并启动分析」）。
  - `embedded` 时：不渲染外层 `section` 边框与「四角标定」eyebrow + 大标题层级，改为一行 `A 视角 · 球场四角`；点位摘要由 `sm:grid-cols-4` 降为 `grid-cols-2`；提交按钮文案由调用方给出（「确认 A 视角四角」）。
- `NetProfileCalibrator`：新增 `variant?: "standalone" | "embedded"`、`hideProfilePanel?: boolean`。
  - `embedded` 时隐藏右侧参数面板与 `confirmed` 勾选，只保留视频 + 五点标注 + 完成按钮；`complete` 判定不再依赖内部 `confirmed`（改由调用方在放行时统一校验）。
- 所有新增 props 均可选，默认行为与现状逐字一致，`NewAnalysisPage` / `RecordingAnalyzePage` 不需改动。

### D4：球网高度 profile 提升为页面级唯一实例

- 从 `NetProfileCalibrator.tsx` 导出 `buildNetProfile(mode, endpointCm, centerCm, confirmed)`（现私有 `makeProfile`）与参数面板组件（现内联 JSX 抽为 `NetProfileSettings`）。
- 向导页持有 `netProfileSettings`（`mode` / `endpointCm` / `centerCm` / `confirmed`）一份，渲染在「球网标定」阶段顶部；两个嵌入实例只负责各自的 image-space 点位。
- 两个实例 `onComplete` 时，页面**用页面级 profile 覆盖** draft 的 profile 字段，再写入 `netAnnotationA/B`——即使组件内部仍持有一份 profile 也无法泄漏到提交载荷。
- 选择理由：这是同一张网，物理上只有一个高度模型；覆盖式组装让"唯一权威来源"成为**结构性保证**而非约定。同时顺带修掉 `handleStart` 中 `...netAnnotationA.profile` 造成的 B 侧静默丢弃。

### D5：机位朝向前移到「球场标定」阶段顶部

- 「A 机位位于球场 A 端 / B 端底线」radio 组从确认阶段移到标定阶段顶部，作为标定前置确认。
- 理由：`cam1Orientation` / `cam2Orientation` 决定 `NetProfileCalibrator` 的 `displayOrder`（`rotate_180` / `mirror_x` 时翻转「球网左端/右端」标签），在标定之后才询问属于顺序倒置。
- 确认阶段不再重复询问，只做只读回显（可点击「修改」跳回标定阶段）。

### D6：并排自动标定保持并发触发，但设观测点

- 两个嵌入实例挂载后各自触发一次 `requestAutomaticCalibration`（`automatic-court-line-calibration` 的「自动标定进入即触发」语义不变）。本机推理 100% CPU，两次请求会在后端排队。
- 决策：**先按并发实现**，不引入串行门控——因为排队总耗时与串行基本相同，串行只会让第二路多一段空等。但 tasks 中安排一次实测：记录并排自动标定的两路总耗时，若明显劣于串行（如因外接盘重复 open 竞争），再改为「首路结束后触发次路」并在两路间显示等待态。
- 备选方案（暂否）：挂载即串行化。改动更大且会改变「进入即触发」的既有可观测行为。

### D7：状态提升与引用稳定

- 四个标定结果继续由向导页持有（`calibrationA/B`、`calibrationPointsA/B`、`netAnnotationA/B`），作为 `initialPoints` / `initial` 传入。
- **禁止**向两个嵌入实例传内联的新数组/新对象（如 `initialPoints={pointsA.filter(...)}`）——`CourtCornerCalibrator` 的 `useEffect` 依赖 `[initialPoints, videoId, videoSrc]`，`NetProfileCalibrator` 依赖 `initial`，引用每帧变化会在拖动中被重置。

### D8：提交失败就地高亮状态条，不回退步骤

原实现在提交失败且错误信息命中 `sync|同步|preflight|朝向|双摄素材|场景标定|球网` 时 `setStep(0)` 回到「素材检查」。素材检查不再是独立步骤后，改为把错误交给常驻状态条：状态条转危险配色并展开标题、详情与操作（「重新检查同步」打开同步锚点工作台、「改用 A 机位单摄分析」、「关闭提示」），页面停留在当前阶段，不跳步。

## Risks / Trade-offs

- [并排后每侧宽度下降，细粒度拖点精度变差] → 断点取 `xl:` 且容器放宽到 `max-w-7xl`；overlay 的 SVG `viewBox` 使用视频 natural size，**坐标精度不受显示宽度影响**，仅人眼定位变难；窄屏自动堆叠回全宽。
- [两路并排时挂载顺序或首个 `onComplete` 可能触发另一侧 `useEffect` 重置] → 两侧的 `initial*` 引用互不共享（A 的 state 更新不改变 B 的引用），逐项在 tasks 中加断言验证「拖动 A 不影响 B 的草稿」。
- [并发自动标定在 CPU-only 环境下互相竞争] → D6 的实测观测点；必要时降级为串行触发。
- [6 步改 3 步破坏既有测试与用户肌肉记忆] → **BREAKING**：`MultiViewAnalysisSetupPage.test.tsx` 的步骤驱动断言整体重整（改动面看起来大是因为 6 个用例都用旧步骤名按钮当"传送带"），重整后单个用例的点击次数反而减少。
- [隐藏参数面板后用户找不到高度设置] → 共享面板固定渲染在「球网标定」阶段顶部，且标注说明文案指明「两路共用同一高度模型」。
- [朝向提前后，用户在标定阶段中途改变朝向会导致已标球网的左右端语义翻转] → 改变朝向时清空该阶段已完成的球网点位（保留球场标定），并明确提示。

## Migration Plan

纯前端编排调整，无数据迁移、无 API 变更。

1. 先落地组件层（`variant` / 文案 props / `buildNetProfile` 与 `NetProfileSettings` 导出），跑 `CourtCornerCalibrator.test.tsx` + `NetProfileCalibrator.test.tsx` + 两个单摄页面测试确认零回归。
2. 再重排向导页（步骤机、状态条、并排容器、共享 profile 面板、朝向前置）。
3. 最后重整 `MultiViewAnalysisSetupPage.test.tsx` 的步骤驱动断言。

回滚：本 change 只动前端源码，`git revert` 对应提交即可，无需回滚数据。

## 已确认的决议（2026-09-27 用户确认）

- 并排断点取 `xl`（≥1280px 视口）：用户确认在其主力分辨率下合适。若实测偏窄，可下调容器 padding 或上移断点。
- 提交失败的回退方式：**就地高亮顶部素材状态条**，不新增任何「回到标定起点」入口（见 D8）。
