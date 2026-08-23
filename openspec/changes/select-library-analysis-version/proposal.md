## Why

同一素材可以产生多个公开分析任务，但当前素材工作区只能管理历史任务，结果视图始终强制读取最新 completed 任务。用户无法回看某次分析的数据分析、球路、报告和技术详情，也无法对比算法迭代前后的真实结果。

## What Changes

- 在素材工作区的历史分析任务列表中增加结果版本选择能力，并显示当前选中态、创建时间、分析类型、执行模式、分析窗口和任务状态等可用摘要。
- 以 `analysisJob=<jobId>` URL query 作为素材工作区的 canonical 历史版本选择状态；刷新、工作区 Tab 切换和结果内部跳转均保留该选择。
- 将“数据分析 / 球路 / 报告 / 技术详情”统一绑定到当前 selected result Job，避免不同 Tab 读取不同版本。
- 保留 `primaryResultAnalysisJobId` 作为未显式选择时的最新 completed 默认值；active Job 继续只驱动进度，不覆盖用户已选历史结果。
- 按 selected Job 的状态与 `AnalysisResult` manifest 计算结果视图 capability；已完成任务可浏览真实产物，失败/取消任务只提供状态与可用技术诊断，不借用其他版本产物。
- 对不存在、不属于当前素材、internal child 或已删除的 `analysisJob` 安全回退到最新 completed 结果，并规范化 URL，防止跨素材读取。
- 调整 Progress 完成后的 Library Workspace CTA，显式携带新完成 Job，确保点击后查看的就是该次分析。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `library-item-workspace`: 新增历史结果版本选择、选中态与全结果 Tab 联动要求。
- `library-analysis-recreate`: 将历史任务从仅删除/取消管理扩展为可选择、可回看的分析版本。
- `analysis-flow-navigation`: 新增 `analysisJob` URL 选择语义、工作区内保留规则与 Progress 完成 CTA 的精确 Job 定向。
- `workspace-content-composition`: 将结果 view capability 与 Content 组件数据源从 primary Job 改为当前 selected Job。

## Impact

- 前端路由与状态：`LibraryItemWorkspace`、Library URL query 解析/构造、workspace view 切换和 Progress 完成 CTA。
- 素材投影：`LibraryItemViewModel.analysisJobs` 需提供选择器展示和归属校验所需的轻量任务摘要。
- 结果加载：Vision、BallTrajectory、Report、MultiviewObservability/AnalysisDetails Content 统一接收 selected Job ID。
- capability 门控：需按 selected Job 加载轻量 `AnalysisResult` manifest，不得逐 view 拉取重产物。
- 测试：新增路由纯函数、归属校验、默认/失效回退、Tab 联动、刷新保留和 active/selected 解耦的回归覆盖。
- 不需要新后端 API、数据库迁移或 artifact schema 变更；继续使用现有 Job/Result/Report/artifact API。
