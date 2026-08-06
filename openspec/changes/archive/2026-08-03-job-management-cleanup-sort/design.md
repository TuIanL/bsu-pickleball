## Context

任务管理页（`src/pages/AnalysisTasksPage.tsx`，路由 `/analysis/tasks`）已具备：任务卡片、来源 Tab（上传/录制/双摄）、单删、手动勾选批量删除、取消、删除结果汇总。后端 `POST /api/analysis/jobs/delete` 与 `delete_analysis_job`（`backend/app/services/mock_analysis.py:375`）已完整覆盖内存、磁盘产物（job JSON、报告、结果、overlay、输出目录）及共享视频/标定引用计数清理；前端 `deleteAnalysisJobs`（`src/services/analysisClient.ts:622`）在后端成功后同步清理浏览器本地兜底（demo 任务）。

列表接口 `list_analysis_jobs`（`backend/app/services/job_orchestration.py:397`）固定按 `updatedAt or createdAt` 倒序返回，无排序参数；前端无排序状态与 UI。

约束：本次改动后端零改动、不新增端点；排序需同时覆盖后端 API 与浏览器本地兜底两条数据路径；录制/双摄 Tab 是另一套数据结构（RecordingSession/FieldSession），不在本次范围。

## Goals / Non-Goals

**Goals:**
- 上传视频任务列表新增「清除失败/取消任务」一键按钮，自动筛选并批量删除 `failed` / `canceled` 任务，复用现有删除流程与结果汇总。
- 上传视频任务列表新增排序下拉控件，支持按创建时间/更新时间 × 新→旧/旧→新四种排序。
- 删除与排序均保持浏览器本地兜底数据一致。
- 后端、磁盘存储、类型定义零改动。

**Non-Goals:**
- 不新增后端端点（不加 `POST /jobs/purge` 或 `GET /jobs?sort_by=`）。
- 不扩展录制/双摄 Tab 的清除与排序（数据模型不同，后续独立变更处理）。
- 不改变既有删除、批量删除、取消、刷新行为。

## Decisions

### D1：一键清除采用纯前端方案，复用 `POST /api/analysis/jobs/delete`

前端按钮点击 → confirm → 从当前可见任务筛出 `status === "failed" || status === "canceled"` 的 job_id 列表 → 调用现有 `deleteAnalysisJobs(jobIds)` → 复用 `summarizeDeleteResults` 展示结果。删除后端已完整支持，本地兜底自动同步。

- **备选**：后端新增 `POST /jobs/purge?statuses=failed,canceled` 服务端过滤删除。
  - **否决理由**：前端列表即后端列表，传 job_id 与服务端过滤结果一致；新增端点需额外测试与文档，收益有限。若未来出现"前端列表过期、需删后端最新失败任务"的场景再引入。
- **风险**：前端列表过期导致漏删最新失败任务 → 可接受（刷新任务后再点击即可）；删除是终态任务，无活跃任务保护冲突（活跃任务天然不在 failed/canceled 集合，且后端仍会保护活跃任务）。

### D2：排序采用前端 `useMemo` 内存排序，后端零改动

新增状态 `sortKey: "createdAt" | "updatedAt"`（默认 `"updatedAt"`）与 `sortDir: "desc" | "asc"`（默认 `"desc"`），用 `useMemo` 对上传任务列表排序后渲染。排序键使用 `AnalysisJobSummary` 已有的 `createdAt` / `updatedAt` 字段，`updatedAt` 缺失时回退 `createdAt`。

- **备选**：后端 `GET /jobs` 加 `sort_by` / `order` 参数。
  - **否决理由**：两处排序逻辑重复（后端 + 本地兜底路径仍需前端排序）；任务量级小（个人使用场景），内存排序性能无忧；后端排序对 UI 无感知收益。
- **权衡**：排序是纯展示层状态，刷新列表后仍保持用户选择（state 常驻组件，页面刷新丢失——可接受，不持久化）。

### D3：UI 位置与交互

- 「清除失败/取消任务」按钮放在批量删除工具栏行（现有全选/清空选择/批量删除 所在行），红色系（danger 视觉），垃圾桶图标；无失败/取消任务时 disabled；删除进行中 disabled。
- 排序下拉（`<select>`）放在同一工具栏行右侧，选项文案：`创建时间 新→旧` / `创建时间 旧→新` / `更新时间 新→旧` / `更新时间 旧→新`，默认选中 `更新时间 新→旧`。

## Risks / Trade-offs

- [前端列表与后端实际任务不一致，一键清除可能漏掉最新失败任务] → 按钮执行前以当前已加载列表为准；用户可先手动刷新再清除。
- [删除中间态（deleted/blocked/not_found）结果不直观] → 复用现有 `summarizeDeleteResults` 汇总卡片（已删除/受保护/未找到/失败）。
- [排序逻辑与未来后端排序参数并存时可能双重排序] → 当前后端无排序参数，本次明确前端为唯一排序源；未来若加后端排序，需约定只启用其一。
- [按钮误触导致不可逆删除] → 删除前强制 confirm，确认文案列出将删除的任务数量。

## Migration Plan

- 前端改动集中在 `AnalysisTasksPage.tsx`，无数据迁移、无接口变更，可直接发布。
- 回滚：还原该文件即可；删除与排序均为增强功能，不影响既有删除/取消/刷新。
