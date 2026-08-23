## Context

当前 LibraryItemWorkspace 通过 primaryResultAnalysisJobId 将分析、球路、报告和技术详情全部绑定到最新 completed 公开 Job。概览虽列出历史任务，却只提供进度、取消和删除操作。工作区 URL 只保存 view，不能表达“当前查看哪次分析”。

本变更涉及 Library 素材投影、URL 状态、工作区 capability 门控、多个结果 Content 组件和 Progress 完成导航。已有 Job、AnalysisResult、Report 和 artifact API 均可按 Job ID 读取，因此无需新后端 API 或数据迁移。

## Goals / Non-Goals

**Goals:**

- 允许用户从当前素材所属的公开历史 Job 中选择一个版本，并在所有结果 Tab 中持续查看该 Job。
- 以 URL 作为选择的唯一 canonical state，支持刷新、深链与 Tab 切换。
- 保留“最新 completed 默认结果”和“active Job 独立驱动进度”的现有契约。
- 按 selected Job 自身的类型、状态和 AnalysisResult manifest 门控内容，禁止跨版本借用产物。
- 对跨素材、internal child、已删除或不存在的 Job ID 做 fail-closed 归属校验。

**Non-Goals:**

- 不实现两个版本并排对比或指标 diff。
- 不修改分析算法、Job 生命周期、artifact schema 或报告内容。
- 不允许选择 internal multiview child Job 作为用户结果版本。
- 不将 selected Job 持久化到数据库、localStorage 或全局 store。

## Decisions

### D1: analysisJob query 是唯一 canonical selection state

工作区 URL 采用 /library/:kind/:sourceId?view=:view&analysisJob=:jobId。组件不维护第二份可变 selected state，而是从 URL 与当前素材的 Job 摘要推导 SelectedAnalysisContext。

- 有合法 analysisJob：使用显式选择，后续新 Job 完成也不自动切换。
- 无 analysisJob：使用 primaryResultAnalysisJobId 作为动态默认值。
- 用户即使点击当前最新版本，也写入显式 analysisJob，使该次查看保持稳定。

component state 无法支持刷新和深链，localStorage 会产生过期 Job ID，因此均不采用。

### D2: 选择解析与 URL 构造使用纯函数

新增纯函数契约（命名可在实现时调整）：

- resolveSelectedAnalysisJob(item, requestedJobId)：校验归属、visibility 和状态，返回 selected Job 与 fallback reason。
- buildLibraryWorkspacePath(item, view, selectedJobId, extraQuery)：合并并保留 view、analysisJob、t 等 query。

归属权威来自 LibraryItemViewModel.analysisJobs；它已经按 recording/session/take/video ownership 过滤并排除 internal child。不得仅凭可猜测的 Job ID 跨素材选中。

### D3: primary、selected 和 active 保持正交

```text
primaryResultAnalysisJobId = 最新 completed，默认值
selectedAnalysisJobId      = URL 显式选择，驱动结果内容
activeAnalysisJobId        = 当前运行任务，只驱动进度
```

active Job 完成后继续定向 reconciliation：URL 未显式选择时默认结果随 primary 更新；已显式选择时当前内容不变，概览仅提示有新版本。

### D4: 所有 Job-bound 结果视图共享 SelectedAnalysisContext

Workspace 在上层解析一次，并将同一 Job ID 传给 Vision、BallTrajectory、Report 和 Technical Content。Technical 根据 selected Job 的 analysisKind 选择 MultiviewObservability 或 AnalysisDetails，而不按素材类型猜测。

视频和片段属于素材级视图，不受 selected Job 数据源限制，但 Tab 切换仍保留 analysisJob，便于返回结果视图。

### D5: capability 按 selected Job manifest 计算并按 Job ID 缓存

computeLibraryViewCapabilities 不再隐式假定 primary Job。Workspace 对 selected Job 加载一次轻量 Job/AnalysisResult manifest，产生 SelectedAnalysisCapabilities，供 Tab 门控和 Content 共用。缓存 key 必须包含 Job ID，切换版本时不得沿用上一个版本的 manifest。

completed Job 按真实 artifact metadata 决定各视图；failed/canceled Job 不呈现其他 Job 的分析、球路或报告，技术详情只在该 Job 有可用诊断时开放。

### D6: 历史选择器保持轻量

LibraryAnalysisJobView 扩展选择所需摘要：Job ID、status、analysisKind、createdAt、executionMode、analysis window 与可用标签。列表不预加载报告、球路、热力图或 observability 重产物。

completed 提供“查看结果”；failed/canceled 提供“查看详情”；active 保持“查看进度”，不作为稳定结果版本。

### D7: 失效选择安全回退并规范化 URL

若 analysisJob 不存在、已删除、不属于当前素材或为 internal child：

1. 不请求该 Job 的结果产物。
2. 回退到 primaryResultAnalysisJobId；若无 primary，显示无结果态。
3. 使用 replace 移除失效 analysisJob，保留 view 和其他合法 query。
4. 显示非阻塞提示，说明原版本不可用且已回到最新结果。

### D8: Progress 完成 CTA 精确锁定新 Job

Library origin 的 Progress 完成 CTA 指向 view 与 analysisJob=completedJobId，而不是只指向 view，避免 reconciliation 延迟或并列任务导致用户看到另一 Job。

## Risks / Trade-offs

- [切换版本需要加载 manifest] → 仅读轻量 Job/AnalysisResult，按 Job ID 缓存并忽略过期请求。
- [旧 Job 产物 schema 不完整] → 按该 Job 自身 manifest 显式降级，不从最新 Job 借产物。
- [显式选择可能使用户错过新结果] → 显示“有新版本”和“查看最新”，但不打断当前回看。
- [选中任务被删除] → 删除后立即重投影并执行安全 fallback。
- [sync_recording 混合 multiview 与 A/B 单摄 Job] → Technical 和 capability 依据 selected Job analysisKind。
- [URL 构造分散导致丢参数] → 收敛为单一纯函数并做表驱动测试。

## Migration Plan

1. 扩展轻量历史 Job ViewModel 和 URL/selection 纯函数，保留旧 URL 默认语义。
2. 将 capability 计算改为显式接收 selected Job context。
3. 将四个 Job-bound Content 及内部 Tab 导航切换到 selected Job。
4. 开放历史列表查看操作和 Progress 精确 CTA。
5. 长期兼容无 analysisJob 的旧 URL，无需重写历史链接。

回滚时可移除选择器与 query 消费，无 analysisJob 的 primary-result 路径仍保持现有行为；本变更无持久化数据需要回滚。

## Open Questions

无阻塞实现的开放问题。首版不提供并排比较；若后续需要双 Job 对比，应另建 change 设计双 Job 上下文。
