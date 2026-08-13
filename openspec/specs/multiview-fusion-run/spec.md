# multiview-fusion-run Specification

## Purpose
TBD - created by archiving change add-multiview-player-trajectory-fusion. Update Purpose after archive.
## Requirements
### Requirement: 运行实体所有权

系统 MUST 提供 `MultiViewFusionRun` 作为多视角分析的所有者。`MultiViewFusionRun` MUST 记录 `capture_take_id / source_analysis_job_ids[] / view_inputs[] / sync_calibration_ref / canonical_frame_ref`，并 MUST 将融合产物（如 `fused_player_trajectory.v1`）挂在其自身产物目录，MUST NOT 挂到任一 cam_1/cam_2 AnalysisJob 或 CaptureTake 上。

#### Scenario: 产物归属

- **WHEN** `MultiViewFusionRun` 完成融合
- **THEN** `fused_player_trajectory.v1` SHALL 写入该 Run 的产物目录
- **AND** 产物 SHALL 归属于 Run 自身，而非 cam_1/cam_2 Job 或 CaptureTake

#### Scenario: Run 标识

- **WHEN** 系统需要引用一次多视角分析
- **THEN** 系统 SHALL 使用 `MultiViewFusionRun` 标识
- **AND** 该标识 SHALL 可追溯 `capture_take_id` 与 `source_analysis_job_ids`

### Requirement: 等待 source job 完成

`MultiViewFusionRun` MUST 在启动融合前等待全部 `source_analysis_job_ids` 对应 AnalysisJob 完成。任一路 source job 失败或不存在时，Run MUST 按 job-level fallback 处理，不生成融合产物。

#### Scenario: 双路就绪

- **WHEN** cam_1 与 cam_2 两个 AnalysisJob 均已 completed
- **THEN** `MultiViewFusionRun` SHALL 进入融合执行
- **AND** 输入 SHALL 基于两路真实单视角分析产物

#### Scenario: 单路未完成

- **WHEN** 任一 source job 未完成、失败或不存在
- **THEN** `MultiViewFusionRun` SHALL NOT 生成 fused artifact
- **AND** 下游 SHALL 继续消费原单视角 artifact

### Requirement: 融合执行管线

`MultiViewFusionRun` MUST 按固定顺序执行融合管线：Canonical Timeline → `GlobalTrackFilter.predict(t)` → `CrossViewPlayerAssociator` → `ViewIntrinsicQuality` → `PairConsistency` → `PlayerPositionFusion`（conflict gate）→ `GlobalTrackFilter.update()`。管线的全局预测 MUST 统一来自 `GlobalTrackFilter.predict(t)`。

#### Scenario: 管线顺序

- **WHEN** Run 执行一次融合
- **THEN** 各阶段 SHALL 按上述固定顺序执行
- **AND** 关联/融合所引用的 global prediction SHALL 来自 `GlobalTrackFilter.predict(t)`

#### Scenario: 单一预测来源

- **WHEN** 某时刻两路无有效观测
- **THEN** 是否输出预测点 SHALL 由 `GlobalTrackFilter` 决定
- **AND** `PlayerPositionFusion` SHALL NOT 独立产生预测状态

### Requirement: Job-level 与 Sample-level Fallback 分离

`MultiViewFusionRun` MUST 区分两种 fallback：**job-level**（Run 无法合法启动：任一 view `court_orientation=None` 或 sync authority `unavailable` → 不生成 fused artifact，下游继续消费单摄 artifact）；**sample-level**（Run 合法但某时刻某路 `unavailable` → 该 fused sample `fusion_status = single_view_fallback`，Run 继续）。两种语义 MUST NOT 混用。

#### Scenario: job-level 不生成产物

- **WHEN** 任一 view `court_orientation = None` 或 sync authority `unavailable`
- **THEN** Run SHALL 判定为 job-level fallback
- **AND** Run SHALL NOT 生成 fused artifact

#### Scenario: sample-level 继续运行

- **WHEN** Run 合法，但某时刻某路观测 `unavailable`
- **THEN** 该 fused sample SHALL 置 `fusion_status = single_view_fallback`
- **AND** Run SHALL 继续处理其余时刻

### Requirement: 可诊断与可回滚

`MultiViewFusionRun` 的执行 MUST 可诊断（产出含 orientation normalization / frame mapping errors / association decisions / view quality scores / view disagreement / fallback & conflict counts 的 diagnostics），且删除 Run MUST 不改变任何现有单视角 artifact（可回滚）。

#### Scenario: 诊断产出

- **WHEN** Run 执行结束
- **THEN** Run SHALL 产出 diagnostics artifact
- **AND** diagnostics SHALL 记录归一化、映射、关联、质量、分歧与 fallback/conflict 计数

#### Scenario: 回滚不损单摄

- **WHEN** 删除某 `MultiViewFusionRun`
- **THEN** cam_1/cam_2 的现有单视角 AnalysisJob 与 artifact SHALL 保持不变

### Requirement: MultiViewJointRun 运行实体

`joint_tracking_v2` SHALL 使用 `MultiViewJointRun` 作为运行实体(区别于 `late_fusion_v1` 的 `MultiViewFusionRun`)。`MultiViewJointRun` SHALL 拥有 `JointViewRuntime` cam_1/cam_2、`CanonicalAnalysisClock`、`GlobalPlayerState` 集合与 fused artifact 产物归属。运行标识为 `jointRunId`(不复用 `fusionRunId`)。

#### Scenario: joint run 所有权

- **WHEN** 一个 `joint_tracking_v2` Parent 运行
- **THEN** `MultiViewJointRun` SHALL 拥有两个 `JointViewRuntime` 与全局状态
- **AND** 产物 SHALL 归属 JointRun,而非任一 ViewRun 或 CaptureTake

#### Scenario: 不等待 child job

- **WHEN** joint run 启动
- **THEN** SHALL NOT 等待 AnalysisJob children(无 children)
- **AND** 直接按 CanonicalAnalysisClock 推进双 view perception

### Requirement: jointRunId 持久化与原子 finalize

`jointRunId` SHALL 持久化于 Parent(`fusionRunId` 仅属 late_fusion_v1)。Parent 被 claim 后 SHALL 先持久化 `jointRunId`,再打开视频/模型。失败重试 SHALL 复用 `jointRunId`、清理 incomplete temp outputs、从头安全重跑(第一版无 checkpoint resume)。临时产物 SHALL atomic finalize,避免半成品被误认完成。

#### Scenario: 先持久化再执行

- **WHEN** joint Parent 被 claim
- **THEN** 系统 SHALL 先持久化 `jointRunId`
- **AND** 再打开视频/加载模型

#### Scenario: 重启复用幂等

- **WHEN** joint run 失败后同一 Parent 重试
- **THEN** 系统 SHALL 复用 `jointRunId`
- **AND** 清理 incomplete temp outputs 后从头安全重跑

### Requirement: MultiViewFusionRun 仅属 late_fusion_v1

`MultiViewFusionRun` SHALL 仅用于 `executionMode=late_fusion_v1`(等待两个 source AnalysisJob → artifact fusion)。`joint_tracking_v2` SHALL NOT 使用 `MultiViewFusionRun` 的等待/artifact-fusion 语义。

#### Scenario: late_fusion 保持 FusionRun

- **WHEN** Parent 的 `executionMode=late_fusion_v1`
- **THEN** 系统 SHALL 使用 `MultiViewFusionRun` 等待两个 source job 并执行 artifact fusion
- **AND** 行为与 P0 完全一致

### Requirement: FusionRun 消费唯一配对计划

`MultiViewFusionRun` SHALL 持有或可追溯本次运行唯一的 `FramePairingPlan`。late-fusion 的 association、canonical timeline 和 measurement fusion SHALL 使用该计划，不得在不同阶段重复选择 secondary source frame。

#### Scenario: 运行产物可追溯配对计划

- **WHEN** `MultiViewFusionRun` 完成或 fallback
- **THEN** run diagnostics SHALL 包含 pairing plan reference 或等价的 pairing summary
- **AND** 每个 secondary observation SHALL 可追溯其 source frame 与 selection error

### Requirement: 运行实体绑定 canonical frame

`MultiViewFusionRun` SHALL 持有与 Parent 一致的 `canonical_frame_ref`。`MultiViewJointRun` 也 SHALL 持有同一 canonical frame reference，两个运行实体不得为同一 take 创建独立 canonical world。

#### Scenario: 同一 take 复用 canonical frame

- **WHEN** 同一 CaptureTake 分别运行 late-fusion 和 joint-tracking A/B
- **THEN** 两个 run SHALL 引用同一个 canonical frame id
- **AND** 两个 artifact 的坐标 SHALL 使用同一 canonical frame version

### Requirement: MultiViewJointRun online recovery tick contract

`MultiViewJointRun` SHALL 按 `age bindings -> predict -> build all-view guidance snapshot -> all-view perception -> barrier -> association/fusion -> state update` 执行。每个 view 的 perception SHALL 仅消费同一 pre-tick snapshot；reference view SHALL NOT 被排除为 guidance target。

#### Scenario: perception 顺序不改变结果
- **WHEN** 运行时改变 Cam1/Cam2 的顺序执行
- **THEN** 同一 tick 生成的 guidance 与 association 输入 SHALL 保持基于相同 pre-tick state

### Requirement: per-view context 与 recovery artifact

joint run SHALL 为每路使用独立 timing provider、frame dimensions、orientation、homography/inverse homography。v2 `view_observations` SHALL additive 地记录 local identity、source track、origin、guidance/donor/residual、intrinsic quality 与既有 timing provenance；run manifest/diagnostics SHALL 记录 P1 config snapshot 与 recovery funnel。

#### Scenario: v2 兼容 provenance
- **WHEN** 目标 view 通过 guided ROI 恢复 formal observation
- **THEN** 其 v2 view observation SHALL 包含 guided recovery provenance 及 P1-0 timing fields
- **AND** 历史 v2 reader SHALL 能读取缺少新增字段的 artifact

#### Scenario: P1 target geometry 不得 fallback
- **WHEN** online recovery target 缺少其 own geometry context
- **THEN** joint run SHALL 跳过该 recovery attempt 并记录 structured reason
- **AND** SHALL NOT 以 reference view geometry 代替

### Requirement: Joint debug trace ownership

`joint_tracking_v2` 的 `joint_debug_trace.v1.json` SHALL 归属于 `jointRunId` 的 diagnostic artifact 目录，并 SHALL 与 `fused_player_trajectory.v2`、recovery diagnostics 和 refinement artifacts 分离。`late_fusion_v1` SHALL 不因该能力产生 debug trace。

#### Scenario: joint run 开启 debug trace
- **WHEN** `joint_tracking_v2` 的 debug trace 开关为 true
- **THEN** trace SHALL 写入当前 JointRun 目录
- **AND** manifest SHALL 记录 trace schema/version 和启用配置

#### Scenario: late fusion 运行
- **WHEN** Parent execution mode 为 `late_fusion_v1`
- **THEN** 系统 SHALL 保持原有 MultiViewFusionRun artifact 行为
- **AND** SHALL NOT 写入 joint debug trace

### Requirement: Trace uses canonical run decisions

debug trace SHALL 使用 `MultiViewJointRun` 已产生的 canonical tick、FrameSample、guidance snapshot、ViewFrameResult、association update 和 fused state。trace renderer 和 writer SHALL NOT 重新运行 tracker、重新调用 detector 或重新选择 source frame。

#### Scenario: renderer 重放已完成 run
- **WHEN** JointRun trace 与原视频可用
- **THEN** renderer SHALL 按 trace 中的 source frame index 读取两路视频
- **AND** 两路视频 SHALL 在同一 canonical tick 下展示

#### Scenario: trace 缺少 source decision
- **WHEN** trace 无法提供某 view 的 source frame/status decision
- **THEN** renderer SHALL 报告 trace schema/input error
- **AND** SHALL NOT 按相同 frame number 进行隐式配对

### Requirement: Diagnostic deletion isolation

删除或重新生成 debug trace、debug MP4 和 summary report SHALL 不删除、不覆盖、不改变 `fused_player_trajectory.v2`、existing recovery diagnostics、原视频或单视角 artifacts。

#### Scenario: 清理 debug 输出
- **WHEN** 开发者删除某次 Visual Acceptance Run 的 debug directory
- **THEN** 业务 trajectory、diagnostics、CaptureTake 和原始 media SHALL 保持不变

