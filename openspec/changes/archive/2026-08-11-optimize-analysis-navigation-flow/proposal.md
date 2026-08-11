## Why

双摄任务管理、双摄分析向导和分析结果页面之间没有保留用户当前的业务上下文，返回操作经常把用户送回上传视频任务或视频管理页面。双摄向导还缺少一致的上一步/退出层级，且关键按钮使用了未定义的 CSS class，导致流程长、可逆性差、视觉反馈不完整。

## What Changes

- 将分析任务列表当前来源 tab 和可选的双摄录制上下文纳入 URL 或等价的稳定导航状态，进入任务详情后返回时恢复原来的任务列表视图。
- 统一双摄 Parent、双摄录制工作台、视觉分析、分析详情和报告页面的返回目标，避免使用与入口无关的固定 `/capture` 或默认上传任务路径。
- 为分析任务详情页补充统一的左上角返回入口，并根据任务来源返回上传任务、普通录制任务或双摄录制任务。
- 完善双摄分析四阶段向导的退出、上一步、下一步和确认启动操作；A/B 标定阶段可以返回上一步，确认阶段可以回到任一需要修正的前置阶段。
- 保留已完成的标定上下文或明确支持重新标定，避免用户返回前一步后无法继续或必须重新开始整个流程。
- 将双摄向导和标定组件的关键操作统一到应用已有的按钮样式，修复 `primary-button`、`sport-button` 未定义造成的默认浏览器按钮外观。
- 补充路由、任务列表上下文、向导步骤返回和按钮可用状态的前端回归测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `analysis-task-management`: 任务列表需要保留来源 tab 和录制上下文，任务详情返回时恢复正确的列表视图。
- `sync-recording-task-listing`: 双摄录制卡片及其任务操作需要把双摄上下文传递到创建页、任务详情和结果页。
- `multiview-analysis-setup-page`: 四阶段双摄向导需要提供一致的退出/上一步/下一步导航、可逆步骤和完整按钮样式。
- `analysis-details-page`: 双摄和单摄任务详情页需要提供与任务来源一致的顶部返回入口。
- `recording-analysis-bridge`: 录制到分析的创建、重试和返回流程需要区分双摄主流程与单摄工程入口，并保持来源上下文。

## Impact

- 前端路由与导航：`src/App.tsx`、`src/app/router.ts`、`src/app/navigationTypes.ts`、`src/app/AppRouter.tsx`。
- 任务列表和双摄任务卡片：`src/pages/AnalysisTasksPage.tsx` 及相关测试。
- 双摄分析创建和标定：`src/pages/MultiViewAnalysisSetupPage.tsx`、`src/components/platform/CourtCornerCalibrator.tsx` 及相关测试。
- 分析结果与录制页面：`src/pages/AnalysisJobPage.tsx`、`src/pages/AnalysisDetailsPage.tsx`、`src/pages/VisionPage.tsx`、`src/pages/ReportPage.tsx`、`src/pages/RecordingWorkspacePage.tsx`。
- 应用按钮样式：`src/index.css`，不涉及后端 API 或分析算法契约。
