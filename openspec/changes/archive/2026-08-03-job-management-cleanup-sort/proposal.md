## Why

任务管理页已支持手动勾选批量删除，但失败/取消任务积累后只能逐个勾选清理，操作繁琐；任务列表顺序固定为更新时间倒序，无法按创建时间或升序方向查看，快速定位最早/最近创建的任务缺少手段。

## What Changes

- **新增「清除失败/取消任务」一键按钮**（仅作用于上传视频任务列表）：
  - 点击后弹确认，自动筛出状态为 `failed` / `canceled` 的分析任务并调用现有批量删除接口；
  - 复用现有删除流程与结果汇总反馈（已删除/受保护/未找到/失败）；
  - 列表中无失败/取消任务时按钮禁用；
  - **后端零改动**：复用 `POST /api/analysis/jobs/delete` 与 `delete_analysis_job`，内存、浏览器本地兜底、磁盘产物（job JSON、报告、结果、overlay、共享视频/标定引用计数）清理均已覆盖。
- **新增任务排序下拉控件**（作用于上传视频任务列表）：
  - 排序键：创建时间（`createdAt`）/ 更新时间（`updatedAt`）；
  - 方向：新→旧（desc）/ 旧→新（asc），共 4 个选项；
  - 默认「更新时间 新→旧」，与现有列表顺序一致；
  - 前端 `useMemo` 内存排序，同时覆盖后端 API 与浏览器本地兜底两条数据路径；**后端零改动**。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `analysis-task-management`: 新增「终端任务一键清除」与「任务列表排序」两个需求及其场景；既有删除、批量删除、刷新、反馈需求保持不变。

## Impact

- **前端**：`src/pages/AnalysisTasksPage.tsx`（新增按钮与排序控件、排序状态、筛选与排序逻辑）。
- **前端服务层**：`src/services/analysisClient.ts` 无需改动（`listAnalysisJobs` / `deleteAnalysisJobs` 已存在并覆盖本地兜底）。
- **后端**：无改动，无新增端点；复用 `POST /api/analysis/jobs/delete`。
- **磁盘存储**：无新增；删除路径已由 `delete_analysis_job`（`backend/app/services/mock_analysis.py`）完整覆盖。
- **测试**：前端 vitest 补充清除筛选与排序逻辑用例。
