# analysis-job-orchestration Specification

## Purpose
TBD - created by archiving change add-analysis-job-orchestration-foundation. Update Purpose after archive.
## Requirements
### Requirement: Durable analysis job lifecycle

`canonicalStatus` SHALL 管理 `queued / running / succeeded / failed / canceled / interrupted` 六态任务生命周期；`interrupted` 表示本次 Worker 执行失联或被进程中断，不等价于 Pipeline 算法失败。系统 MUST 使用独立维度 `orchestrationStatus` 表达多视角 Parent 编排，不得将 `waiting_sources` 等编排状态塞入 `canonicalStatus`。任务摘要 SHALL 持久化 Worker lease、heartbeat 和 interruption 字段，并兼容读取没有这些字段的历史任务。

#### Scenario: Job is created

- **WHEN** 有效的真实分析请求被接受
- **THEN** 系统 SHALL 在返回前持久化 queued job、创建时间、排队时间、输入引用、分析配置、当前阶段、初始进度和初始 Worker liveness 字段

#### Scenario: Worker starts a job

- **WHEN** Worker 领取 queued job
- **THEN** 系统 SHALL 原子地标记 job 为 running，记录开始时间、Worker 身份、运行实例 ID、领取时间和首次 heartbeat
- **AND** SHALL 防止另一个 Worker 领取同一个 job

#### Scenario: Job is interrupted

- **WHEN** running job 的 Worker heartbeat 超时或服务启动确认其执行进程已中断
- **THEN** 系统 SHALL 将 job 标记为 `interrupted`
- **AND** SHALL 持久化中断时间、稳定中断原因和最后已知阶段/进度

#### Scenario: Job succeeds

- **WHEN** 所有必需分析阶段和报告生成完成
- **THEN** 系统 SHALL 标记 job 为 succeeded，记录完成时间，保存结果/报告 artifact 引用，并保留阶段遥测

#### Scenario: Job fails

- **WHEN** 不可恢复的阶段错误发生
- **THEN** 系统 SHALL 标记 job 为 failed，记录完成时间、稳定错误码、用户错误信息和分离的内部诊断信息

#### Scenario: Job is canceled

- **WHEN** queued 或 running job 接收到有效取消请求
- **THEN** 系统最终 SHALL 标记 job 为 canceled，记录取消时间，停止或跳过剩余分析阶段，并在安全时清理临时文件

### Requirement: Stage telemetry

阶段遥测 MUST 保持既有 `AnalysisStage` 结构，并由当前分析模式的规范化阶段图生成。`single_view` MUST 继续使用既有单摄稳定阶段；`late_fusion_v1` 的 `AnalysisPipelineResult.stages` MUST 按“素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 可视化输出 / 报告生成”顺序表达聚合阶段；`joint_tracking_v2` MUST 按“素材与同步检查 / 双摄协同跟踪 / 指标重算 / 可视化输出 / 报告生成”顺序表达聚合阶段。双摄子阶段进度 MUST 经 `viewRuns` 暴露，运行中应反映最近可用的 child 或内部 `ViewRun` 状态；双摄专用阶段 MUST NOT 被追加到单摄阶段列表末尾。

总体进度 MUST 使用当前阶段图的稳定权重和阶段进度聚合，保持单调递增；MUST NOT 通过包含未来 `pending` 阶段的数量平均值覆盖真实的当前阶段进度。报告阶段 MUST 只能在前置分析和后处理阶段完成后开始。

#### Scenario: Parent 聚合阶段

- **WHEN** 前端轮询 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示与 `executionMode` 对应的聚合阶段和真实顺序
- **AND** `viewRuns`（`cam_1` / `cam_2` 各自的 `status / stage / progress`）在有子运行时 SHALL 提供两路子进度，运行中也反映 child 或内部 `ViewRun` 的最近状态

#### Scenario: joint tracking 不显示报告先于协同跟踪

- **WHEN** `joint_tracking_v2` 的协同跟踪阶段上报进度 95
- **THEN** `multiview-joint` SHALL 为 active，指标、可视化和报告 SHALL 仍按图保持 pending
- **AND** 总体进度 SHALL 按 joint 阶段权重聚合，而不是按单摄阶段数量平均

#### Scenario: 报告生成是终末阶段

- **WHEN** 双摄任务进入报告生成
- **THEN** 只有在融合或协同跟踪、指标重算和可视化输出完成后，报告阶段才 SHALL 变为 active
- **AND** 报告完成后总体进度 SHALL 为 100

### Requirement: API and worker execution separation

系统 SHALL 将任务创建/查询/取消 API 与重型分析执行彻底分离。真实分析请求 SHALL 只在控制面创建 queued job 并通知或等待 external Worker 领取，不得在 Web 请求处理器或 FastAPI lifespan thread 中运行完整 Pipeline。

#### Scenario: API creates a job

- **WHEN** 客户端创建真实分析任务
- **THEN** API SHALL 校验请求、持久化 queued job、通知或等待 external Worker，并在完整分析执行前返回

#### Scenario: Worker executes a job

- **WHEN** external Worker 找到可执行 queued job
- **THEN** Worker SHALL 执行 Pipeline，通过 JobStore 写入 heartbeat/阶段进度，并持久化 terminal job/result/report 状态

#### Scenario: API reads status during execution

- **WHEN** 客户端查询 queued、running 或 interrupted job
- **THEN** API SHALL 返回控制面中最新的持久化任务和阶段遥测
- **AND** API SHALL 不依赖 Web 进程内存中是否存在 Worker 或任务缓存

### Requirement: Local queue and priority execution

系统 SHALL 按优先级和创建顺序调度可领取的 queued job，并在进程重启后恢复队列。running job 的恢复 SHALL 由 heartbeat liveness 对账决定；失联运行任务标记为 interrupted，不得重新伪装成仍在 processing。

#### Scenario: Jobs have the same priority

- **WHEN** 多个 queued job 优先级相同
- **THEN** Worker SHALL 优先领取排队时间最早的可执行 job

#### Scenario: Jobs have different priorities

- **WHEN** 多个 queued job 可执行且优先级不同
- **THEN** Worker SHALL 在没有公平性策略阻止饥饿时优先领取高优先级 job

#### Scenario: Queue survives process restart

- **WHEN** 服务重启后存在 queued job 和 running job
- **THEN** queued job SHALL 保持可领取
- **AND** heartbeat 新鲜的 running job SHALL 保持 running
- **AND** heartbeat 过期的 running job SHALL 进入 interrupted，并可通过显式重新分析恢复

### Requirement: Resource-limited execution
The system SHALL limit local concurrent analysis work according to configured CPU and GPU resource settings.

#### Scenario: CPU limit is reached
- **WHEN** the configured maximum number of CPU jobs is already running
- **THEN** additional CPU-bound jobs remain queued until capacity is available

#### Scenario: GPU limit is reached
- **WHEN** the configured maximum number of GPU jobs is already running
- **THEN** additional GPU-bound jobs remain queued until GPU capacity is available

#### Scenario: Default local configuration is used
- **WHEN** no explicit resource configuration is provided
- **THEN** the system runs heavy analysis conservatively so one long or model-backed job cannot start unbounded concurrent analysis jobs

### Requirement: Cancellation

系统 SHALL 支持 Web API 对 external Worker 执行的 queued/running job 发起协作式取消。取消请求必须通过跨进程控制面可见，terminal job（包括 interrupted）不得被普通取消修改。

#### Scenario: Queued job is canceled

- **WHEN** 客户端取消 queued job
- **THEN** 系统 SHALL 在不运行 Pipeline 的情况下将其标记为 canceled

#### Scenario: Running external job is canceled

- **WHEN** 客户端取消 running job
- **THEN** API SHALL 持久化取消请求
- **AND** external Worker SHALL 在下一个安全检查点读取该请求并终止任务

#### Scenario: Interrupted job is not canceled

- **WHEN** 客户端对 interrupted job 发起普通取消
- **THEN** API SHALL 返回稳定的 terminal 状态响应
- **AND** SHALL 不改变 interrupted 的中断原因或删除其任务记录

#### Scenario: Terminal job cancellation is rejected

- **WHEN** 客户端取消 succeeded、failed、canceled 或 interrupted job
- **THEN** 系统 SHALL 返回稳定的非破坏性响应，不得改变 terminal 结果

### Requirement: Timeout and retry policy
The system SHALL support bounded timeout and retry behavior for explicitly configured stages.

#### Scenario: Stage exceeds timeout
- **WHEN** a stage exceeds its configured timeout
- **THEN** the system records a timeout error code and either retries the stage if it is retryable or fails the job with a user-facing timeout message

#### Scenario: Retryable stage fails
- **WHEN** a retryable stage fails with a retryable error and retry attempts remain
- **THEN** the system records the failed attempt, increments the retry count, and retries the stage according to the configured policy

#### Scenario: Non-retryable stage fails
- **WHEN** a non-retryable stage fails
- **THEN** the system fails the job without retrying and preserves the diagnostic context

### Requirement: Idempotent job submission
The system SHALL support idempotent real-analysis job submission based on stable input and configuration signatures.

#### Scenario: Duplicate submission is detected
- **WHEN** a client submits the same input video, calibration, analysis options, and model/runtime configuration without requesting a new version
- **THEN** the system returns or references the existing queued, running, or succeeded job rather than starting duplicate work

#### Scenario: New version is requested
- **WHEN** a client explicitly requests a new analysis version for an otherwise identical input signature
- **THEN** the system creates a new job version and records the relationship to the previous signature-compatible job

#### Scenario: Configuration changes
- **WHEN** the same video is submitted with materially different analysis options or model/runtime configuration
- **THEN** the system treats it as a distinct analysis signature and may create a separate job

### Requirement: Research-grade execution record
The system SHALL preserve enough execution metadata to support product debugging and research reproducibility.

#### Scenario: Completed job is inspected for research
- **WHEN** a developer or researcher reviews a completed real analysis job
- **THEN** the job record exposes the input references, analysis configuration signature, stage timings, model/runtime availability, artifact references, and terminal status needed to reproduce or compare the run

#### Scenario: Internal diagnostics are stored
- **WHEN** internal error details or environment diagnostics are recorded
- **THEN** the system separates them from user-facing messages so the UI does not expose stack traces or sensitive local paths unnecessarily

### Requirement: 任务调度保留并传递源 FPS
系统 SHALL 在分析任务创建、持久化、签名和 worker 执行过程中保留用户确认的源 FPS。

#### Scenario: 创建任务保存 FPS
- **WHEN** API 收到包含源 FPS 的分析任务创建请求
- **THEN** JobStore MUST 将该 FPS 保存到任务摘要或任务输入中
- **AND** 后续查询任务时 SHALL 能读取该 FPS

#### Scenario: Worker 传递 FPS 给 Pipeline
- **WHEN** AnalysisWorker 执行包含源 FPS 的任务
- **THEN** worker MUST 将源 FPS 传递给 AnalysisPipeline
- **AND** Pipeline MUST 使用该值计算 `effective_fps`

#### Scenario: FPS 纳入签名
- **WHEN** `analysis_signature()` 计算任务签名
- **THEN** 签名输入 MUST 包含源 FPS 或其规范化等价值
- **AND** 不同源 FPS 的任务 MUST 产生不同签名

### Requirement: 分析任务支持时间裁剪与预热区间

系统 MUST 在 AnalysisJob JSON Schema 中支持 clip 参数（非数据库列），并在所有实际执行和派生可视化阶段使用统一的窗口语义。Pipeline 执行时使用预热区间，但正式指标、融合统计和用户可见叠加视频 MUST 只对应请求窗口。

#### Scenario: Job Schema 包含 clip 字段

- **WHEN** 创建含裁剪参数的分析任务
- **THEN** `AnalysisJobCreate` SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** `AnalysisJobSummary` SHALL 包含对应字段

#### Scenario: 任务签名包含 clip 信息

- **WHEN** `analysis_signature()` 计算
- **THEN** 输入 payload SHALL 包含 `clipStartMs`、`clipEndMs`、`captureSegmentId`、`segmentVersion`
- **AND** 同一视频不同 Rally SHALL 产生不同签名

#### Scenario: Pipeline 预热区间

- **WHEN** 任务携带 clip 范围
- **THEN** 解码范围 SHALL = `[clip_start - pre_roll_ms, clip_end + post_roll_ms)`
- **AND** 默认 `pre_roll_ms=1500`、`post_roll_ms=500`
- **AND** 半开区间 `[start, end)`，相邻片段不会在边界重复处理
- **AND** 预热帧不纳入正式分析指标

#### Scenario: Pipeline 裁剪结果记录

- **WHEN** Pipeline 按 clip 范围执行
- **THEN** 结果 SHALL 记录 `requested_clip.start_ms/end_ms` 和 `decoded_range.start_ms/end_ms`
- **AND** SHALL 记录实际 `processed_frame_count` 与 `source_frame_count`

#### Scenario: 派生叠加视频遵守窗口

- **WHEN** 任务启用分析叠加视频且携带 clip 范围
- **THEN** 叠加视频 writer SHALL 只读取并写出请求窗口对应的帧
- **AND** 结果 SHALL 记录 `output_time_origin_ms`，使输出 artifact 能映射回源视频时间轴

#### Scenario: 无 clip 保持全场行为

- **WHEN** 任务未携带完整的 `clipStartMs/clipEndMs`
- **THEN** Pipeline、叠加视频和统计 SHALL 按完整源视频执行
- **AND** 结果 SHALL 将窗口字段标记为未启用或省略

### Requirement: 可执行判定统一为 is_runnable

`JobStore.claim_next()` / `claim` 的可执行判定 MUST 收口为 `is_runnable(job)`：`canonicalStatus != "queued"` → False；`analysisKind=single_view` → True；`analysisKind=multiview` → `orchestrationStatus ∈ {fusion_ready, fallback_ready}`。MUST NOT 再直接按 `canonicalStatus == "queued"` 领取。

#### Scenario: waiting_sources 不被领取

- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 被跳过，不占用 Worker（杜绝 Parent 占锁等待 child 的死锁）

#### Scenario: fusion_ready 正常领取

- **WHEN** Parent `orchestrationStatus=fusion_ready`
- **THEN** `claim_next()` SHALL 按既有优先级/排队规则领取

### Requirement: Worker 经 Executor registry 分发

`AnalysisWorkerRuntime._execute` MUST 通过 `executor_registry.resolve(job.analysisKind)` 解析执行体并调用 `execute(job, token, progress_callback)`，MUST NOT 在 Worker 主循环内按 `analysisKind` 硬编码分支。第一版 registry 仅含 SingleView / MultiView 两个执行体（不做插件框架）。取消/重试/超时兜底逻辑归属与行为保持不变。

#### Scenario: 单摄执行不变

- **WHEN** 执行 `analysisKind=single_view` 任务
- **THEN** 行为 SHALL 与改造前一致（SingleViewAnalysisExecutor 封装现有 Pipeline）
- **AND** 现有单摄回归测试 SHALL 通过

#### Scenario: 双摄执行链路

- **WHEN** 执行 `analysisKind=multiview` 的 Parent
- **THEN** MultiViewAnalysisExecutor SHALL 读 child 产物 → 执行 Fusion → Composer → 返回 Parent 结果

### Requirement: 新增编排字段兼容读取

`AnalysisJobSummary` MUST 支持新增字段（`analysisKind` / `visibility` / `parentJobId` / `analysisScope` / `orchestrationStatus` / `fusionRunId` / `sourceJobs` / `viewRuns` / `referenceViewId` / `clipStartMs` / `clipEndMs`）的历史兼容读取：缺省按 `single_view` / `public` / `none` 解析，不破坏既有任务。

#### Scenario: 历史任务读取

- **WHEN** 读取不含新字段的历史 job
- **THEN** 系统 SHALL 按缺省值解析并正常渲染

