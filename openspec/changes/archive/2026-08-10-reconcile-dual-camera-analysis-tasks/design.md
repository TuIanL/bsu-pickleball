## Context

双摄录制任务页面同时消费 `SyncRecordingSession` 和公开的 `AnalysisJobSummary`。后端双摄录制级删除逻辑会按 `recordingSessionId`、`metadata.recording_session_id` 或 `metadata.capture_take_id` 查找归属任务，但前端当前只按 session id 过滤。双摄卡片内部又通过 `find()` 为每个机位和 Parent 选一条任务，导致同一机位的重试或版本任务无法在页面中被识别和管理。

现有任务模型已经包含 `analysisKind`、`cameraSlot`、`recordingSessionId`、`metadata.capture_take_id`、`createdAt` 和 `updatedAt`，无需新增后端字段。`GET /api/analysis/jobs` 默认隐藏 internal child，Parent 级联删除也已经由现有删除接口负责。

## Goals / Non-Goals

**Goals:**

- 统一双摄录制派生任务的前端归属判定，使展示、上传任务排除和录制级删除的范围一致。
- 将公开任务按双摄协同 Parent、A 机位单摄、B 机位单摄分组。
- 每组默认展示最新任务，同时保留历史任务及其明确的 job id 和操作入口。
- 保持 Parent 与 internal child 的既有公开性和级联删除语义。
- 为归属解析、任务分组、最新任务选择和历史任务展示建立可测试的边界。

**Non-Goals:**

- 不修改分析任务后端 API、任务持久化结构或多视角执行算法。
- 不将 internal child 暴露到普通任务列表。
- 不改变双摄录制视频、CaptureTake、同步校准或录制会话的删除语义。
- 不重新设计上传任务 Tab 的通用列表，只修正其对双摄派生任务的排除判断。

## Decisions

### D1: 使用统一的录制归属解析器

新增前端纯函数，用于判断一个公开分析任务是否属于某个双摄录制会话。匹配顺序为：

1. `job.recordingSessionId` 或 `job.metadata.recording_session_id` 等于 `session.session_id`；
2. `job.metadata.capture_take_id` 等于 `session.capture_take_id`。

该函数同时用于：

- 计算 `recordingDerivedJobs`；
- 计算上传 Tab 中应排除的双摄派生任务；
- 将任务传入对应的 `SyncRecordingTaskCard`。

选择集中解析器而不是在页面不同位置重复条件，是为了避免展示和删除范围再次漂移。`capture_take_id` 只作为当前双摄会话已有的唯一 CaptureTake 标识参与匹配，不根据视频文件名或摄像头名称猜测归属。

### D2: 先归类，再选择当前任务

新增或抽取双摄任务分组 view model，至少包含：

- `multiview`: `analysisKind === "multiview"` 的公开 Parent 列表；
- `singleView.cam_1`: A 机位任务列表；
- `singleView.cam_2`: B 机位任务列表；
- `unassigned`: 无法可靠映射到 A/B 的公开任务，供诊断展示而不静默丢弃。

Parent 优先于机位判断。单摄任务优先使用 `cameraSlot` 和 `metadata.camera_slot`，再使用已登记视频 ID作为历史任务兜底。每组按 `updatedAt` 降序排序，缺少更新时间时回退到 `createdAt`，再以 job id 作为稳定的最终排序键。第一条作为当前任务，其余任务作为历史任务。

选择按组排序而不是依赖 API 返回顺序，是为了避免后端排序变化或刷新竞态改变页面当前任务。

### D3: 当前任务和历史任务采用不同展示密度

双摄卡片只在主视图展示每组的当前任务。若一组存在历史任务，显示历史数量和展开入口；展开后按时间顺序展示历史任务的状态、更新时间、job id 和可用的详情/删除操作。

当前 Parent 仍是主 CTA：完成时查看报告，失败或取消时重新分析，活跃时查看进度。A/B 单摄任务作为次级任务行展示。每个操作都接收具体 `job.id`，不再由卡片内部重新 `.find()` 决定操作对象。

### D4: 删除分为任务级和录制级

任务行上的删除只针对对应的公开任务，并复用现有 `deleteAnalysisJob(job.id)`；删除 Parent 时继续由后端级联清理 internal child。录制级“清除本录制全部分析任务”继续使用 `deleteRecordingAnalysis(sessionId)`，并保留录制资产。

活跃任务沿用现有状态约束：显示查看进度或取消入口，不显示任务级删除。历史任务展开后不提供会误指向当前任务的主 CTA。

### D5: 测试以纯函数和卡片行为为主

归属解析和分组排序使用单元测试覆盖 session id、capture take id、A/B 映射、Parent 优先级、更新时间缺省和稳定排序。`SyncRecordingTaskCard` 使用组件测试覆盖多次同机位任务、最新任务操作绑定、历史任务展开和 internal child 不显示。页面测试覆盖双摄派生任务不会错误出现在上传 Tab。

## Risks / Trade-offs

- **[Risk] 历史任务缺少 session id 和 capture take id，无法归属双摄会话** → **Mitigation**：保留为未归属公开任务，不静默放入某个会话；后续由任务详情或数据修复处理。
- **[Risk] `updatedAt` 被重试状态更新后改变，用户理解的“最新版本”与时间排序不同** → **Mitigation**：界面明确使用“最近更新”排序；历史任务仍全部可见，且显示创建时间/更新时间。
- **[Risk] Parent 与单摄任务同时存在时任务数量增加，卡片高度变大** → **Mitigation**：默认只显示每组当前任务，历史任务折叠；单摄分析保持次级密度。
- **[Risk] 任务级删除与录制级删除入口语义相近** → **Mitigation**：任务行明确显示“删除此任务”，录制级操作明确显示“清除本录制全部分析”，并在确认文案中标明是否保留录制视频。
- **[Risk] API 刷新期间任务列表与 session 列表到达顺序不同** → **Mitigation**：归属计算对空 session/take 做安全回退，并在两套数据刷新完成后由现有轮询重新计算列表。

## Migration Plan

- 仅发布前端逻辑和组件测试，无数据迁移。
- 首先替换双摄派生任务归属和分组 view model，再替换卡片渲染和操作绑定。
- 若出现 UI 回归，可回退前端 change；后端任务和录制资产不受影响。

## Open Questions

- 暂无阻塞性问题。当前设计将“最新”定义为最近更新时间，缺省时使用创建时间。
