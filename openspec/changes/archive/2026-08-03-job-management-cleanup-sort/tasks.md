## 1. 一键清除失败/取消任务

- [x] 1.1 在 `AnalysisTasksPage.tsx` 中基于 `uploadJobs` 计算终端任务集合（`status === "failed" || status === "canceled"`），导出其 job_id 列表与数量
- [x] 1.2 在批量删除工具栏行新增「清除失败/取消任务」按钮（红色系、垃圾桶图标），无终端任务或删除进行中时 disabled
- [x] 1.3 实现 `handleClearTerminal`：confirm 确认（文案含将删除任务数量）→ 调用现有 `deleteAnalysisJobs(terminalJobIds)` → 复用 `summarizeDeleteResults` 展示结果，并清除已选中/相关状态
- [x] 1.4 验证浏览器本地兜底路径：后端成功删除后 demo 任务同样从本地兜底存储移除（`deleteAnalysisJobs` 已覆盖，确认接入即可）

## 2. 任务排序

- [x] 2.1 新增排序状态 `sortKey`（默认 `"updatedAt"`）与 `sortDir`（默认 `"desc"`）
- [x] 2.2 在批量删除工具栏行新增排序下拉控件，四个选项：创建时间 新→旧 / 创建时间 旧→新 / 更新时间 新→旧 / 更新时间 旧→新，默认「更新时间 新→旧」
- [x] 2.3 实现排序 `useMemo`：按 `sortKey`（`updatedAt` 缺失时回退 `createdAt`）与 `sortDir` 对上传任务列表排序，替换渲染数据源
- [x] 2.4 确认排序同时作用于后端 API 与浏览器本地兜底两条数据路径

## 3. 测试与验收

- [x] 3.1 为清除筛选逻辑（终端任务判定、空集合禁用、confirm 取消无副作用）补充 vitest 用例
- [x] 3.2 为排序逻辑（createdAt/updatedAt × asc/desc、updatedAt 缺失回退、默认排序）补充 vitest 用例
- [x] 3.3 运行 `npm test` 与 `npm run build`，确认无类型错误、既有用例不回归
- [x] 3.4 本地运行验证：构造 failed/canceled 任务后点击一键清除，确认任务从列表消失且 `backend/data/outputs/jobs/` 与关联产物（报告、overlay、共享资源）被清理；切换排序选项确认列表顺序正确
