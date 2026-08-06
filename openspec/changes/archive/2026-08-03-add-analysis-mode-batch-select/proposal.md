## Why

分析任务管理页现有「全选 / 逐卡勾选 + 批量删除」只能整体或逐卡片选择任务，无法按分析模式（样例任务 / 有限真实分析 / 真实视频分析）一键圈定同一类的全部任务后删除。任务列表混有多种模式时，用户需要逐卡勾选或全选后手动排除，效率低且容易误选。

## What Changes

- 在「上传视频任务」tab 的工具栏新增「按类型选择」入口（按钮 + 弹出的小选项卡）。
- 选项卡内提供三个多选复选框：样例任务、有限真实分析、真实视频分析，每个复选框显示当前该类可删除任务的数量。
- 勾选某模式 = 将该模式全部**可删除**（非运行中）任务加入选择集；取消勾选 = 同步从选择集移除该模式全部任务；模式勾选状态与任务卡片选择集实时联动，部分选中时显示半选态。
- 选择集与现有选择状态、卡片级复选框、全选、已选计数共用；删除仍复用现有「批量删除」按钮与删除确认/反馈流程。
- 仅对「上传视频任务」tab 生效；录制视频任务与双摄录制 tab 无分析模式概念，不受影响。
- 无后端改动：复用现有批量删除 API（`POST /api/analysis/jobs/delete`）与本地样例任务（localStorage）兜底删除路径。

## Capabilities

### New Capabilities

（无新增能力）

### Modified Capabilities

- `analysis-task-management`: 在既有批量选择与删除需求之上，新增「按分析模式批量选择」的交互需求（上传任务 tab），包括模式选项卡入口、各类可删任务计数、模式勾选与选择集的联动、半选态表示。

## Impact

- 前端：
  - `src/pages/AnalysisTasksPage.tsx`：工具栏新增「按类型选择」按钮与弹层、模式选择状态与现有选择集联动逻辑。
  - 新增轻量 popover/弹层组件（如 `src/components/platform/` 下），支持点击外部关闭；若与现有卡片勾选状态合并逻辑复杂，可抽公共选择辅助函数到 `src/utils/`。
  - 复用 `analysisModeLabel`（`src/utils/analysisHelpers.ts`）展示模式标签，复用 `deleteAnalysisJobs` 批量删除。
- 类型：复用 `AnalysisJobSummary.analysisMode`（`"demo" | "real" | "limited"`），无需新增字段。
- 后端：无改动。
- 测试：`src/pages/AnalysisTasksPage` 相关交互逻辑可补充单元测试；手工验证三种模式选择/取消/半选态与批量删除联动。
