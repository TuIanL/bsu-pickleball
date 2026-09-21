## MODIFIED Requirements

### Requirement: AnalysisJob 编排字段

系统 MUST 为 `AnalysisJobSummary` 保留现有编排字段，并允许 `canonicalStatus` 使用 `queued / running / succeeded / failed / canceled / interrupted`。`interrupted` 表示 Parent、segmentation prerequisite 或 child 的 Worker 执行失联；等待正式切分的 Parent 保持 `canonicalStatus=queued` 和 `orchestrationStatus=waiting_segmentation`，等待 late-fusion child 的 Parent 保持 `canonicalStatus=queued` 和 `orchestrationStatus=waiting_sources`。任务摘要的 `stages` MUST 根据 `executionMode` 使用规范化阶段图；`viewRuns` 只有在存在真实 dedicated child 或内部 `ViewRun` 时才返回非空内容。Parent SHALL 记录 internal segmentation prerequisite reference；成功后 SHALL 记录 `segmentation_run_id` 和 `window_plan_hash`。

#### Scenario: 历史任务读取兼容
- **WHEN** 读取不含新字段的历史 `AnalysisJobSummary`
- **THEN** 系统 SHALL 按 `analysisKind=single_view`、`visibility=public`、`orchestrationStatus=none` 缺省解析
- **AND** 不得因缺字段而解析失败或改变既有渲染

#### Scenario: 正式双摄任务创建
- **WHEN** 用户发起一次需要正式回合切分的双摄协同分析
- **THEN** 系统 SHALL 创建一个 `analysisKind=multiview` 的 public Parent，初始 `canonicalStatus=queued, orchestrationStatus=waiting_segmentation`
- **AND** SHALL 创建仅供 Coordinator 使用的 internal segmentation prerequisite job
- **AND** Parent SHALL 根据其 `executionMode` 选择含切分阶段的顶层阶段图，而不是复用单摄阶段后追加双摄阶段

#### Scenario: interrupted child is represented
- **WHEN** 一个 multiview child 因 Worker heartbeat 超时进入 `canonicalStatus=interrupted`
- **THEN** Parent 的 `viewRuns` SHALL 暴露该机位的 interrupted/lost 状态和最后已知进度
- **AND** Parent SHALL NOT 继续把该 child 当作普通 running child

### Requirement: Child 恒 dedicated/owned

系统 MUST 保证一个 `late_fusion_v1` multiview Parent 在成功固定正式窗口计划后拥有两个 dedicated internal child jobs（`child.parentJobId = parent.id`、`child.visibility = internal`、`child.analysisScope = full`）。即使两个 Parent 的输入签名相同，MUST NOT 复用另一个 Parent 的 child。Child 不跨 Parent 共享，使级联删除语义成为所有权清理而非引用计数。Parent 侧 MUST 以 `sourceJobs: [{cameraSlot, jobId}]` 数组记录所有权映射，MUST NOT 采用 `childJob1 / childJob2` 双字段。

#### Scenario: 切分成功后创建 late-fusion child
- **WHEN** Coordinator 收到 late-fusion Parent 的成功或 `valid_no_rallies` segmentation prerequisite 结果并已绑定窗口计划
- **THEN** 系统 SHALL 创建两个 dedicated child（`cam_1` / `cam_2`）
- **AND** 每个 child SHALL 记录 `parentJobId=parent.id`、`visibility=internal`、`cameraSlot` 与同一 run/plan 引用
- **AND** Parent 的 `sourceJobs` SHALL 以数组记录 `[{cameraSlot: "cam_1", jobId}, {cameraSlot: "cam_2", jobId}]`

#### Scenario: 切分尚未成功
- **WHEN** Parent 处于 `waiting_segmentation`、切分失败、取消或 interrupted
- **THEN** 系统 SHALL 不创建任何 late-fusion source child
- **AND** Parent SHALL 不进入 `waiting_sources`

#### Scenario: 相同输入不复用
- **WHEN** 两个 multiview Parent 引用相同视频/标定输入
- **THEN** 第二个 Parent 在其自身切分成功后 SHALL 仍创建自己的两个新 child
- **AND** SHALL NOT 复用第一个 Parent 的任何 child

### Requirement: 两套 orchestrationStatus 冻结

系统 SHALL 冻结两套含 prerequisite 的编排状态枚举，并使其进入 `is_runnable()` / reconciliation / cancel / restart / 前端进度：

```text
late_fusion_v1:    waiting_segmentation / waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed
joint_tracking_v2: waiting_segmentation / joint_ready / joint_tracking / composing / completed
共同:               none / composing / completed
```

`fusion_ready` SHALL NOT 在 joint 模式下表示“准备开始 tracking”；`waiting_segmentation` SHALL NOT 表示 Parent 可被视觉执行器领取。

#### Scenario: joint 状态
- **WHEN** joint Parent 的 segmentation prerequisite 成功并绑定计划
- **THEN** `orchestrationStatus` SHALL 从 `waiting_segmentation` 进入 `joint_ready`
- **AND** 执行 tracking 期间 SHALL 为 `joint_tracking`

#### Scenario: late_fusion 状态
- **WHEN** late-fusion Parent 的 segmentation prerequisite 成功
- **THEN** Coordinator SHALL 创建 child 并将 Parent 推进 `waiting_sources`
- **AND** 双路 child 完成后 SHALL 推进 `fusion_ready`（与现有融合语义一致）

### Requirement: is_runnable() 按模式判定

`is_runnable(job)` SHALL 按 role 与 executionMode 判定：segmentation prerequisite 在 `canonicalStatus == queued` 时可被其专用 executor 领取；`single_view` 保持既有规则；`multiview/late` 仅在 `canonicalStatus == queued AND orchestrationStatus ∈ {fusion_ready, fallback_ready}` 时可执行；`multiview/joint` 仅在 `canonicalStatus == queued AND orchestrationStatus == joint_ready` 时可执行。处于 `waiting_segmentation` 的 public Parent SHALL 不可领取。

#### Scenario: Parent 等待切分不可 claim
- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_segmentation` 的 public Parent
- **THEN** 该 Parent SHALL 被跳过且不占用 Worker
- **AND** internal segmentation prerequisite SHALL 由专用 executor 正常领取

#### Scenario: joint 切分成功后直接 runnable
- **WHEN** joint Parent 已绑定成功窗口计划且 `orchestrationStatus=joint_ready`
- **THEN** `is_runnable(job)` SHALL 返回 True
- **AND** 系统 SHALL 创建内部 `JointViewRuntime` A/B，而不创建 late-fusion dedicated child jobs
