## Why

当前工作区无法通过前端 TypeScript 构建，前端与后端测试也存在真实失败；失败主要集中在路由判别联合、录制到分析的任务字段、分析 artifact 状态、测试数据隔离和历史模型配置契约。与此同时，`/tasks` 与 `/analysis/tasks` 两套任务入口、demo/localStorage 降级和未清理的旧测试数据继续增加排查成本，导致后端异常可能被前端伪装成成功的 demo 结果。

现在需要先建立一个稳定的工程基线，统一已实现的行为契约，清理会掩盖真实故障的历史兼容逻辑，再继续叠加视觉分析功能。

## What Changes

- 修复前端路由元数据与 `RouteState` 判别联合不一致的问题，确保 `npm run build` 通过。
- 补齐录制分析任务的 TypeScript 数据契约，统一 `recording_session_id`、`camera_slot` 与 camelCase 摘要字段。
- 明确 ball overlay、球轨迹和可视化 artifact 在 skipped、unavailable、failed、available 状态下的返回语义，并保持 API 可兼容。
- 修复后端录制生命周期测试的数据库/mock 隔离，清除测试对本地运行数据的隐式依赖。
- 统一模型自动发现与默认配置测试，明确“仓库存在模型”与“用户显式启用模型”的边界。
- 将 `/analysis/tasks` 设为分析任务列表的规范入口，并保留 `/tasks` 作为兼容别名，避免历史链接失效。
- 收紧 demo/localStorage fallback：真实 API 请求失败时不得无提示地伪造已完成分析任务。
- 建立前端构建、测试、Lint 与后端 pytest 的质量门禁，清理现有未使用变量、`any`、React effect 规则和废弃 API 警告。
- 同步 README、OpenSpec 与实际路由/API，移除已删除页面和旧入口的错误描述。

## Capabilities

### New Capabilities

- `codebase-quality-gates`: 定义前后端构建、测试、Lint 和测试隔离的可验证质量基线。
- `legacy-analysis-workflow-consolidation`: 定义规范任务路由、兼容旧路由和真实 API 失败的可见降级行为。

### Modified Capabilities

- `frontend-architecture-boundaries`: 补充录制分析路由与任务路由的精确判别联合要求，并要求实现与表驱动测试一致。
- `recording-analysis-bridge`: 补充前后端任务归属字段的共享契约，确保录制来源信息能被任务列表和详情页读取。
- `analysis-artifacts`: 补充可选 artifact 在 skipped、unavailable、failed、available 状态下的稳定状态与 detail 语义。
- `sync-recording-task-listing`: 将 `/analysis/tasks` 设为规范入口，同时保留 `/tasks` 兼容别名，并统一任务列表跳转。

## Impact

- 前端：`src/app/router.ts`、`src/app/navigationTypes.ts`、`src/types/report.ts`、分析任务页、录制分析页、`analysisClient.ts` 及相关测试。
- 后端：`analysis_pipeline.py`、`config.py`、自动标定服务、录制会话/CaptureTake 服务、分析 schema、测试 fixtures 和可视化模块。
- 工程配置：`package.json`、ESLint 配置、pytest 配置、启动脚本和文档。
- API：分析任务摘要和 artifact 状态字段会被规范化；旧任务数据必须保持可读取，旧 `/tasks` 链接继续可用。
- 不包含新的视觉算法能力，不改变当前真实视频分析的核心算法，只修复契约、可观测性、测试稳定性和历史兼容边界。
