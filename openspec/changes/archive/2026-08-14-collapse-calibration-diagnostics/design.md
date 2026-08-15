# collapse-calibration-diagnostics — Design

## Context

`CourtCornerCalibrator.tsx` 是场地标定组件唯一实现，被 NewAnalysisPage（上传）、RecordingAnalyzePage（录制后）、MultiViewAnalysisSetupPage（双摄）三处入口复用。当前「自动标定状态面板」（L532-578）常驻渲染三块内容：

1. `DiagnosticNoticeCard`（L533-543）——title/body + 13 项 detailItems（后端说明、模型路径、Mask 统计、置信度分解、选中帧、重投影误差等）；
2. `confidence_breakdown` 4 张置信度卡片（L554-570）；
3. 检测预览图 `automaticPreviewUrl`（L571-577）。

这些开发诊断数据对终端用户无价值且占据空间；但识别中进度与失败/拒绝指引是必要的操作反馈，不能一并折叠。

`DiagnosticNoticeCard` 是通用组件（被 StatusState / AnalysisTasksPage / AnalysisJobPage / NewAnalysisPage 复用），折叠逻辑不能下沉到该组件，否则会误伤其他页面的错误展示。

## Goals / Non-Goals

**Goals:**
- 默认隐藏全部开发诊断数据，主画面（视频 + 可拖拽四边形）成为唯一焦点。
- 标题旁新增 Info (i) 图标，点击 toggle 展开/收起诊断区。
- 保留必要的操作反馈：识别中进度、失败/拒绝指引（一行文字，无指标）。
- 三入口行为一致，后端 API 与数据契约不变。

**Non-Goals:**
- 不修改 `analysisDiagnostics.ts` 的诊断数据生成逻辑与测试。
- 不修改 `DiagnosticNoticeCard` 通用组件。
- 不做展开状态持久化（localStorage）。
- 不调整后端自动标定请求/响应结构。
- 不改变 manualMode（自动标定失败后的人工兜底）标题与帧导航交互。

## Decisions

### D1: 折叠逻辑放组件内部，用组件级 state 控制

在 `CourtCornerCalibrator.tsx` 内新增 `const [showCalibrationDetails, setShowCalibrationDetails] = useState(false)`，仅在该组件渲染区做条件渲染。`DiagnosticNoticeCard` 保持通用不动。

**理由**：避免影响其他 4 处错误展示场景；改动收敛在单文件。
**备选**：给 `DiagnosticNoticeCard` 加 `collapsible` 属性 —— 被否决，会把折叠概念泄漏给非本场景的调用方。

### D2: Info 图标用 lucide-react 内置 `Info`，位于 h2 标题旁

h2（「自动识别球场边线」）旁渲染一个 `button` 包 `Info` 图标（圆圈 + i），`aria-label="查看自动识别详细数据"`、`aria-expanded` 标注展开态，点击 toggle D1 的 state。项目已依赖 lucide-react，无需新增依赖。

**理由**：图标语义准确（information）；button 保证键盘可达。
**备选**：自定义 SVG —— 无必要，lucide 已有现成图标。

### D3: 折叠范围与保留范围

**折叠（仅 i 点击后可见）**：
- `DiagnosticNoticeCard` 的「自动识别已就绪」提示及其全部 detailItems（L533-543 渲染块）；
- `confidence_breakdown` 4 张卡片（L554-570）；
- 检测预览图 `automaticPreviewUrl`（L571-577）。

**保留默认可见（不进折叠）**：
- 识别中/上传中：「正在自动识别球场边线…」（L544-548 分支）；
- manualMode 提示：「自动标定失败，已切换到人工标定…」（L549-553）；
- 失败/拒绝/不可用的 `DiagnosticNoticeCard`（status 为 error / rejected / unavailable 时）——这是操作指引，折叠会使用户困惑为什么角点未自动填入。

**理由**：把「成功态诊断」与「失败态指引」区分对待——成功态全部是开发数据，失败态首行是用户必需信息。实现上按 `automaticCalibrationStatus` 分支处理。

### D4: 展开状态不持久化

每次进入标定步骤默认收起（state 初始为 false，组件随 videoId 变化重置草稿时一并重置）。

**理由**：与「最终用户不看到」目标一致，实现最简；开发期需要时点一下即可。

### D5: 后端与数据层零改动

自动标定请求照常发起、响应照常消费，仅渲染层折叠。`analysisDiagnostics.ts` 的 `automaticCalibrationNotice` 与 `analysisDiagnostics.test.ts` 不变。

## Risks / Trade-offs

- [就绪态完全隐藏后，用户感知不到「自动识别成功」] → 角点自动填入本身就是反馈；主画面四边形默认已铺好，可拖动即代表成功。若有需求可后续追加一行精简提示，不阻塞本变更。
- [i 图标入口不直观，用户不知道可展开] → 图标为通用信息符号（圆圈 + i），符合平台其他位置的惯例；展开内容纯属开发诊断，即使无人点击也不损失产品功能。
- [失败态 DiagnosticNoticeCard 仍含 detailItems，若误折叠会丢排查信息] → D3 明确失败态整卡保留展开，含 detailItems，开发排查能力不降级。

## Migration Plan

纯前端渲染改动，无数据迁移。部署即生效，回滚 = revert 单文件改动。
