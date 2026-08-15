# collapse-calibration-diagnostics — Tasks

## 1. 折叠状态与 Info 图标

- [x] 1.1 在 `src/components/platform/CourtCornerCalibrator.tsx` 新增 `showCalibrationDetails` state（默认 `false`），并在组件随 videoId/initialPoints 重置的 effect 中一并重置为折叠态
- [x] 1.2 从 lucide-react 导入 `Info` 图标，在 h2 标题（「自动识别球场边线」）旁渲染 `button` + `Info`，带 `aria-label="查看自动识别详细数据"` 与 `aria-expanded`，点击 toggle state

## 2. 诊断区条件渲染

- [x] 2.1 就绪态（status 为 `ready`）的 `DiagnosticNoticeCard` 及其 detailItems 移入展开区：仅 `showCalibrationDetails` 为 true 时渲染
- [x] 2.2 `confidence_breakdown` 4 张置信度卡片移入展开区：仅展开时渲染
- [x] 2.3 检测预览图 `automaticPreviewUrl` 移入展开区：仅展开时渲染
- [x] 2.4 保留默认可见（不进折叠）：识别中/上传中进度文本、manualMode 提示、失败/拒绝/不可用（status 为 `error` / `rejected` / `unavailable`）的 `DiagnosticNoticeCard`
- [x] 2.5 无任何诊断数据（`automaticCalibration` 为 null 且无错误）时不渲染 Info 图标

## 3. 验证

- [x] 3.1 `npx tsc -b`（或 `npm run build` 类型检查部分）通过，无类型错误
- [x] 3.2 三入口（NewAnalysisPage / RecordingAnalyzePage / MultiViewAnalysisSetupPage）手动验证：自动识别成功后主画面仅显示可拖拽四边形与标题行，点 (i) 展开全部诊断指标，再点收起；识别中进度与失败提示默认可见（**由用户人工验证**）
