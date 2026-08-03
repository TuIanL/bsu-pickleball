## 1. 建立前端共享契约

- [x] 1.1 在 `AnalysisUploadMetadata`、`AnalysisJobSummary` 和相关 API response 类型中补齐 `recording_session_id`、`camera_slot`、`recordingSessionId`、`cameraSlot` 字段，并保持历史任务字段可选。
- [x] 1.2 在 `analysisClient` 中集中完成 snake_case 后端字段到 camelCase 前端字段的适配，移除页面内对任务字段的未声明访问。
- [x] 1.3 修复 `routeMeta` 与 `RouteState` 的字面量冲突，明确 `/capture`、`/capture/:id/analyze`、`/tasks` 和 `/analysis/tasks` 的页面入口、shellMode 与 navigationSection。
- [x] 1.4 为上述路由补齐表驱动测试，覆盖 query 参数、历史 `/tasks` 别名和录制分析页面分发。

## 2. 统一分析 artifact 状态

- [x] 2.1 在 pipeline 结果组装处使用统一状态表，确保可选 artifact 的 `status` 始终为 `available`、`skipped`、`unavailable` 或 `failed`，并保留对应 `detail`。
- [x] 2.2 修复 ball overlay、球轨迹、弹跳和位置可视化 artifact 在无文件时的序列化逻辑，避免由 `path` 是否存在清空状态。
- [x] 2.3 补充 artifact API 对已知缺失 artifact 返回 404、对已生成 artifact 返回正确内容类型的回归测试。
- [x] 2.4 验证历史任务缺少新增字段时仍能读取，并在前端显示有限/不可用状态而不是无关 demo 数据。

## 3. 隔离后端测试与模型配置

- [x] 3.1 为后端测试建立统一的临时数据库、上传目录、输出目录、录制目录和模型目录 fixture。
- [x] 3.2 修复录制生命周期测试的 fake session factory，使活跃 CaptureTake 查询结果显式可控，不被未配置的 `MagicMock` 解释成真值。
- [x] 3.3 增加测试后端默认 SQLite 不被读取或修改的验证，并覆盖孤儿/超时 CaptureTake 的恢复边界。
- [x] 3.4 统一模型自动发现和显式配置的语义，更新球模型、场地线模型和自动标定测试，使其不依赖仓库 `models/` 的实际文件。
- [x] 3.5 修复 Minimap court bounds 与 tracking bounds 的契约，补充边界点、界外点和渲染结果测试。

## 4. 收敛历史任务工作流

- [x] 4.1 将 `/analysis/tasks` 设为新代码生成的规范任务列表入口，保留 `/tasks` 到同一页面的兼容解析。
- [x] 4.2 清理对已删除 `TasksPage`、`UploadModePage` 的残余引用和过时页面描述，确保旧入口不再渲染旧组件。
- [x] 4.3 收紧 `analysisClient` 的 demo/localStorage fallback，仅允许明确的 demo 请求使用本地任务；真实视频或真实 API 失败必须抛出可识别错误。
- [x] 4.4 为网络错误、HTTP 错误、真实任务失败和明确 demo 任务分别补充前端服务层测试与页面状态测试。

## 5. 清理静态质量问题

- [x] 5.1 清理未使用 import、变量和表达式，优先处理 `CaptureConsolePage`、`useCaptureRuntime`、`CameraHubPage`、`SegmentManagerPage` 和 `AnalysisDetailsPage`。
- [x] 5.2 将生产代码和测试中的无约束 `any` 替换为共享类型、unknown narrowing 或专用 test double 类型。
- [x] 5.3 修复 React hooks 的 effect 依赖、set-state-in-effect、render purity、refs 和 manual memoization 问题，保持录制时钟、轮询和异步加载行为不回归。
- [x] 5.4 将 FastAPI `on_event` startup/shutdown 迁移到 lifespan，保留 worker 启停、数据库初始化和孤儿录制恢复顺序。
- [x] 5.5 修复规格文件的 whitespace 问题，并为必须保留的局部 Lint 例外添加原因注释。

## 6. 文档与全量验收

- [x] 6.1 更新 README、backend README、系统架构文档和相关 OpenSpec，使任务路由、视频上传 API、模型默认行为和 demo 边界与代码一致。
- [x] 6.2 执行 `npm run build`、`npm test`、`npm run lint` 和 `cd backend && python -m pytest -q`，确认无失败且测试不产生工作区业务数据。
- [x] 6.3 对前后端关键错误状态做一次手工冒烟验证：后端不可用、模型缺失、artifact 跳过、录制来源任务和历史 `/tasks` 链接。
- [x] 6.4 在完成实现后记录剩余可接受 warning、未覆盖的真实模型运行风险和后续独立变更建议。
