# collapse-calibration-diagnostics

## Why

自动识别场地的开发诊断指标（模型路径、置信度分解、Mask 统计、重投影误差等 13 项 detailItems + 4 张置信度卡片 + 检测预览图）对终端用户没有使用价值，只对开发阶段调试有用。当前每次进入标定步骤时这些数据都会完整展开，占据画面上方空间，干扰用户聚焦主画面（可拖拽四边形）。

## What Changes

- 在「自动识别球场边线」标题旁新增 Info (i) 圆圈图标（lucide-react），点击 toggle 展开/收起开发诊断区。
- 诊断区默认收起：`自动识别已就绪` 提示、13 项 detailItems、`confidence_breakdown` 4 张置信度卡片、检测预览图（`automaticPreviewUrl`）全部移入展开区。
- 保留默认可见的一行操作反馈（不进折叠）：识别中「正在自动识别球场边线…」、失败/拒绝「请手动拖动或调整标定帧」等指引。
- 展开/收起状态不持久化：每次进入标定步骤默认收起。
- 纯前端改动，后端 API 与数据契约不变；通用组件 `DiagnosticNoticeCard` 不改（避免影响 StatusState / AnalysisTasksPage / AnalysisJobPage / NewAnalysisPage 的错误展示）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `automatic-court-line-calibration`: "User-facing automatic calibration diagnostics" requirement 行为变更 —— 诊断指标由默认全部展开改为默认折叠，仅通过标题旁 Info 图标展开；只保留必要的操作反馈（识别中/失败/拒绝提示）默认可见。

## Impact

- 前端：`src/components/platform/CourtCornerCalibrator.tsx`（L499-578 渲染区）——新增折叠 state、Info 图标按钮、诊断区条件渲染。
- 三处入口页面（NewAnalysisPage / RecordingAnalyzePage / MultiViewAnalysisSetupPage）复用该组件，自动生效，无需改动。
- 无后端 API 变更、无数据契约变更、无新增依赖（lucide-react 已内置 `Info` 图标）。
- `src/services/analysisDiagnostics.ts` 及 `analysisDiagnostics.test.ts` 数据生成逻辑不变，不受影响。
