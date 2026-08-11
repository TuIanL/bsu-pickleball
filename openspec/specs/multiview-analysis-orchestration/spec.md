# multiview-analysis-orchestration Specification

## Purpose
TBD - created by archiving change 2026-08-07-integrate-multiview-analysis-orchestration. Update Purpose after archive.
## Requirements
### Requirement: AnalysisJob 编排字段

系统 MUST 为 `AnalysisJobSummary` 增加编排字段：`analysisKind`（`single_view` / `multiview`，历史 job 缺省 `single_view`）、`visibility`（`public` / `internal`，缺省 `public`）、`parentJobId`（缺省 None）、`analysisScope`（`full` / `perception`，缺省 `full`；**Parent 不适用为 None**）、`orchestrationStatus`（独立编排维度）、`fusionRunId`（缺省 None）、`sourceJobs`（数组 `[{cameraSlot, jobId}]`，Parent 的所有权映射）、`viewRuns`（各机位 `status / stage / progress` 聚合）。`canonicalStatus` 五态 `queued / running / succeeded / failed / canceled` MUST 保持不变，等待 child 的 Parent 在 canonical 上仍属 `queued`。

#### Scenario: 历史任务读取兼容

- **WHEN** 读取不含新字段的历史 AnalysisJobSummary
- **THEN** 系统 SHALL 按 `analysisKind=single_view`、`visibility=public`、`orchestrationStatus=none` 缺省解析
- **AND** 不得因缺字段而解析失败或改变既有渲染

#### Scenario: 双摄任务创建

- **WHEN** 用户发起一次双摄协同分析
- **THEN** 系统 SHALL 创建一个 `analysisKind=multiview` 的 public Parent，初始 `canonicalStatus=queued, orchestrationStatus=waiting_sources`

### Requirement: 编排状态独立维度

系统 MUST 使用独立维度 `orchestrationStatus`（`none / waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed`）表达多视角编排，MUST NOT 塞入 `canonicalStatus`。业务状态与"是否可被 Worker claim"是两个正交维度。

#### Scenario: Parent 等待 child

- **WHEN** Parent 已创建但两个 child 未全部完成
- **THEN** Parent SHALL 处于 `canonicalStatus=queued, orchestrationStatus=waiting_sources`
- **AND** 该 Parent SHALL NOT 被 Worker claim（见 `is_runnable`）

### Requirement: `is_runnable()` 统一 claim 判定

系统 MUST 以 `is_runnable(job)` 作为唯一可执行判定：`canonicalStatus != "queued"` → False；`analysisKind=single_view` → True；`analysisKind=multiview` → `orchestrationStatus ∈ {fusion_ready, fallback_ready}`。`JobStore.claim_next()` MUST 使用该判定，不得再直接写 `canonicalStatus == "queued"`。

#### Scenario: waiting_sources 不可 claim

- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 被跳过（不占用 Worker）
- **AND** 若队列中只有该 Parent，`claim_next` SHALL 返回 None

#### Scenario: fusion_ready 可 claim

- **WHEN** Parent 两个 child 均 completed，`orchestrationStatus=fusion_ready`
- **THEN** `claim_next()` SHALL 按既有优先级/排队规则正常领取该 Parent

### Requirement: Child 恒 dedicated/owned

系统 MUST 保证一个 multiview Parent 拥有两个 dedicated internal child jobs（`child.parentJobId = parent.id`、`child.visibility = "internal"`、`child.analysisScope = "full"`）。即使两个 Parent 的输入签名相同，MUST NOT 复用另一个 Parent 的 child。Child 不跨 Parent 共享，使级联删除语义成为所有权清理而非引用计数。Parent 侧 MUST 以 `sourceJobs: [{cameraSlot, jobId}]` 数组记录所有权映射，MUST NOT 采用 `childJob1 / childJob2` 双字段（为三摄 / 训练辅助机位 / 球场侧机位扩展留位）。

#### Scenario: 双摄创建 child

- **WHEN** Coordinator 创建一个 multiview Parent
- **THEN** 系统 SHALL 同时创建两个 dedicated child（`cam_1` / `cam_2`）
- **AND** 每个 child SHALL 记录 `parentJobId=parent.id`、`visibility=internal`、`cameraSlot`
- **AND** Parent 的 `sourceJobs` SHALL 以数组记录 `[{cameraSlot: "cam_1", jobId}, {cameraSlot: "cam_2", jobId}]`

#### Scenario: 相同输入不复用

- **WHEN** 两个 multiview Parent 引用相同视频/标定输入
- **THEN** 第二个 Parent SHALL 仍创建自己的两个新 child
- **AND** SHALL NOT 复用第一个 Parent 的任何 child

### Requirement: MultiViewAnalysisCoordinator 事件驱动编排

系统 MUST 提供 `MultiViewAnalysisCoordinator` 负责 Parent ↔ Source Job A/B ↔ `MultiViewFusionRun` 的编排：创建 Parent + 两个 child、监听 child completion、推进 Parent 编排状态。Parent MUST NOT 持有"被 claim 后 while 等待 child"的逻辑（`AnalysisWorkerRuntime._running_lock` 一次只执行一个任务，那会死锁）。

#### Scenario: 双路完成推进 fusion_ready

- **WHEN** cam_1 与 cam_2 两个 child 均已 completed
- **THEN** Coordinator SHALL 把 Parent 推进到 `orchestrationStatus=fusion_ready`
- **AND** Parent SHALL 随后可被 `claim_next` 领取

#### Scenario: 单路失败推进 fallback_ready

- **WHEN** 一个 child completed、另一个 failed 或 canceled
- **THEN** Coordinator SHALL 把 Parent 推进到 `orchestrationStatus=fallback_ready`
- **AND** Parent SHALL 仍可被 claim（按确定性单视角降级规则执行）

#### Scenario: 双路失败 Parent failed

- **WHEN** cam_1 与 cam_2 两个 child 均 failed
- **THEN** Parent SHALL 被置为 `canonicalStatus=failed`
- **AND** 不得声称存在任何可用轨迹来源

### Requirement: 应用启动 reconciliation

应用启动后，Coordinator MUST 对账扫描 `analysisKind=multiview AND canonicalStatus not terminal`，第一轮按 child 终态推进 Parent（双路完成 → `fusion_ready`；单路完成 → `fallback_ready`；双路失败 → `failed`；至少一路非终态 → 保持 `waiting_sources`，child 交给现有 zombie recovery）；第二轮把 `fusion_ready / fallback_ready` 且无 worker 所有者的 Parent 保持 `canonical queued` 等待 claim。

#### Scenario: 重启后 Parent 恢复

- **WHEN** 进程重启，Parent 处于 `waiting_sources` 且两个 child 已完成
- **THEN** reconciliation SHALL 把 Parent 推进到 `fusion_ready`
- **AND** 该 Parent SHALL 可被正常 claim 执行

#### Scenario: 职责分离

- **WHEN** reconciliation 处理 Parent/Child 依赖关系
- **THEN** 现有 `recover_zombie_jobs()` 仍只负责 Worker 执行状态恢复
- **AND** 两者 SHALL 相互独立、不揉成一个方法

### Requirement: 取消与删除级联

系统 MUST 支持 Parent 取消/删除的级联语义，并保护 Child 不被外部直接操作。

#### Scenario: 取消 waiting_sources Parent

- **WHEN** 用户取消 `waiting_sources` 的 Parent
- **THEN** Parent SHALL 置为 `canceled`
- **AND** Coordinator SHALL 级联取消其 owned 非终态 children

#### Scenario: 取消运行中的融合

- **WHEN** 用户取消 `fusing` 中的 Parent
- **THEN** Parent SHALL 记录 `cancelRequestedAt`
- **AND** MultiViewExecutor SHALL 检查取消令牌并在安全检查点终止为 `canceled`

#### Scenario: 删除 terminal Parent 级联

- **WHEN** 用户删除已 terminal 的 multiview Parent
- **THEN** 系统 SHALL 删除 Parent 分析产物 + owned child 分析产物 + fusion run 产物 + parent artifacts/report
- **AND** SHALL NOT 删除 CaptureTake 本身、源视频或 CaptureTrack（分析任务只是消费者，不拥有录制资产）

#### Scenario: Child 外部操作保护

- **WHEN** 普通用户 API 尝试取消或删除 internal child
- **THEN** 系统 SHALL 返回 `403 / blocked`（如 `internal source job cannot be canceled directly`）
- **AND** child 只能由 Coordinator 内部或 Parent cascade 操作

### Requirement: MultiView preflight

系统 MUST 在创建双摄任务前执行 preflight：`CaptureTake completed`、双视频 available、双 calibration available、双 orientation declared、`sync_calibration.json` available、两机位属 P0 axis-preserving 范围。不满足时 MUST 返回结构化失败原因，前端据此展示原因与操作，**不得静默退化**。

#### Scenario: sync 不可用

- **WHEN** preflight 检测到 `sync_calibration.json` 不可用
- **THEN** 创建请求 SHALL 返回明确的失败原因（双摄同步信息不可用）
- **AND** 前端 SHALL 展示「重新检查同步」「改用 A 机位单摄分析」等操作
- **AND** SHALL NOT 创建一个随后静默降级的假融合任务

#### Scenario: orientation 未声明

- **WHEN** 任一机位的 `court_orientation` 未声明
- **THEN** preflight SHALL 判定不通过
- **AND** 不得按 `cam_2` 自动推断 `rotate_180`（沿用 P0 硬断言）

### Requirement: Parent 视频源自含

multiview Parent 的 `videoId`/`calibrationId` MUST 在创建时从 reference child 继承；对历史 Parent（`videoId` 缺失），读取时 MUST 从 reference child 虚拟解析（只读、不落盘），确保前端无论 result 是否落盘都能确定视频源。

#### Scenario: 创建时继承

- **WHEN** `create_multiview_job` 创建 Parent
- **THEN** Parent 的 `videoId`/`calibrationId` SHALL 等于 reference child 的对应字段

#### Scenario: 历史 Parent 虚拟解析

- **WHEN** 读取一个 `videoId` 缺失的 multiview Parent
- **THEN** 返回的 job summary SHALL 携带从 reference child 解析出的 `videoId`
- **AND** 该解析 SHALL 只读、不落盘（不改动持久化记录）

### Requirement: 两套 orchestrationStatus 冻结

系统 SHALL 冻结两套编排状态枚举,进入 `is_runnable()` / reconciliation / cancel / restart / 前端进度:

```text
late_fusion_v1:    waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed
joint_tracking_v2: joint_ready / joint_tracking / composing / completed
共同:               none / composing / completed
```

`fusion_ready` SHALL NOT 在 joint 模式下表示"准备开始 tracking"。

#### Scenario: joint 状态

- **WHEN** joint Parent 通过 preflight
- **THEN** `orchestrationStatus` SHALL 进入 `joint_ready`
- **AND** 执行 tracking 期间 SHALL 为 `joint_tracking`

#### Scenario: late_fusion 状态不变

- **WHEN** late_fusion Parent 双路 child 完成
- **THEN** `orchestrationStatus` SHALL 推进 `fusion_ready`(与 P0 一致)

### Requirement: is_runnable() 按模式判定

`is_runnable(job)` SHALL 按 executionMode 判定:

```text
single_view:        canonicalStatus == queued
multiview/late:     canonicalStatus == queued AND orchestrationStatus ∈ {fusion_ready, fallback_ready}
multiview/joint:    canonicalStatus == queued AND orchestrationStatus == joint_ready
```

#### Scenario: joint 直接 runnable

- **WHEN** Parent 的 `executionMode=joint_tracking_v2` 且 `orchestrationStatus=joint_ready`
- **THEN** `is_runnable(job)` SHALL 返回 True,无需 AnalysisJob children
- **AND** 系统 SHALL 创建内部 `JointViewRuntime` A/B(不创建 dedicated child jobs)

#### Scenario: late_fusion 等待 child

- **WHEN** Parent 的 `executionMode=late_fusion_v1` 且 child 未完成
- **THEN** `is_runnable(job)` SHALL 返回 False
- **AND** 双路完成后 SHALL 推进 `fusion_ready` / `fallback_ready`

### Requirement: 双摄分析窗口传播与同步映射

双摄 Parent 的分析窗口 MUST 以 reference view 的公共 take 时间轴表示。`late_fusion_v1` 创建的每个 child MUST 持久化其实际媒体时间轴窗口；secondary child 的窗口 MUST 由权威 sync mapping 换算。`joint_tracking_v2` Parent MUST 保留公共窗口并在执行时交给 CanonicalAnalysisClock/JointRun，不得因没有 child 而丢失窗口。

#### Scenario: late fusion reference child

- **WHEN** 用户创建带 `[start_ms, end_ms)` 窗口的 `late_fusion_v1` 双摄任务
- **THEN** Parent SHALL 持久化该公共窗口
- **AND** reference child SHALL 使用相同的 reference 时间轴范围

#### Scenario: late fusion secondary child

- **WHEN** secondary view 存在有效 sync mapping
- **THEN** secondary child SHALL 持久化映射到自身媒体时间轴的起止范围
- **AND** 两路 child SHALL 表示同一个物理时间窗口

#### Scenario: joint Parent 窗口保留

- **WHEN** 用户创建带窗口的 `joint_tracking_v2` 双摄任务
- **THEN** Parent SHALL 持久化 `clipStartMs` 与 `clipEndMs`
- **AND** joint executor SHALL 使用该窗口建立有限的 reference canonical ticks

#### Scenario: 同步不可用时不伪造窗口映射

- **WHEN** secondary view 缺少有效 sync mapping
- **THEN** 系统 SHALL 保留 reference 窗口
- **AND** secondary SHALL 按既有同步不可用语义标记为 unavailable 或走既有降级路径
- **AND** SHALL NOT 以新的窗口映射逻辑伪造同步配对

### Requirement: 双摄窗口范围可追溯

双摄 Parent、child、fusion/joint run 和派生可视化结果 MUST 能追溯请求窗口、实际解码范围、实际处理帧数和源视频总帧数。`analysisScope` MUST NOT 被解释为时间范围的替代字段。

#### Scenario: 窗口结果诊断

- **WHEN** 带窗口的双摄任务完成
- **THEN** Parent 结果 SHALL 暴露 requested clip 与实际处理范围
- **AND** A/B view diagnostics SHALL 能区分源视频总帧数和窗口内处理帧数

#### Scenario: 任务进度使用窗口分母

- **WHEN** 带窗口的双摄任务正在运行
- **THEN** child 或 joint view progress SHALL 以窗口内计划处理帧/tick 为分母
- **AND** SHALL 仍保留源视频总帧数作为诊断信息

### Requirement: Sync authority preflight

多视角创建和执行前的 preflight SHALL 调用与 executor 一致的严格 sync authority validator，并以当前 Parent 的 reference/secondary view identity 验证 mapping。

#### Scenario: preflight 拒绝错误 mapping

- **WHEN** sync 文件存在但缺少当前 secondary mapping 或 mapping identity 不一致
- **THEN** preflight SHALL 返回结构化问题
- **AND** 系统 SHALL NOT 创建一个会静默使用错误 mapping 的多视角运行

### Requirement: Effective mode 编排传播

Parent 的结果、manifest、summary 和用户可见 message SHALL 传播同一个 effective mode。`fusion_performed`、orchestration status 和 effective mode SHALL 分别表示执行事实、生命周期状态和证据质量，不得互相替代。

#### Scenario: pipeline 执行但无双摄证据

- **WHEN** fusion pipeline 已执行但 `dual_evidence_samples == 0`
- **THEN** Parent SHALL 标记为 `single_view_fallback`
- **AND** summary/message SHALL 不得标记为正常 `multiview_fused`

