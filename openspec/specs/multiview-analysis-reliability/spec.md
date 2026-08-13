# multiview-analysis-reliability Specification

## Purpose
TBD - created by archiving change multiview-reliability-hardening. Update Purpose after archive.
## Requirements
### Requirement: 权威 FramePairingPlan

系统 SHALL 为每次多视角运行生成唯一的 `FramePairingPlan`。计划 SHALL 以 reference canonical tick 为索引，每个 tick 最多选择一张 secondary source frame，并记录 source frame index、source timestamp、mapped take timestamp、selection error 和 status。

#### Scenario: 一个 tick 只选择一张副摄帧

- **WHEN** 一个 reference tick 的同步容差窗口包含多张 secondary source frame
- **THEN** `FramePairingPlan` SHALL 只选择误差最小的一张 source frame
- **AND** 该帧上的全部球员 observation SHALL 共享同一个 secondary source frame index

#### Scenario: 超出容差不可用

- **WHEN** secondary 最近 source frame 超过 `max_pairing_error_ms`
- **THEN** 该 tick 的 secondary decision SHALL 标记为 `unavailable`
- **AND** 下游 SHALL 使用既有 sample-level fallback 语义

### Requirement: Association 与 Fusion 共享配对计划

late-fusion 的 association pass、canonical timeline 和最终 fusion SHALL 只消费同一个 `FramePairingPlan`，不得各自重新执行 nearest frame selection。

#### Scenario: 关联与融合使用同一 source frame

- **WHEN** association 为 reference tick 处理副摄观测
- **THEN** association SHALL 使用 pairing plan 指定的 source frame 上的全部观测
- **AND** 最终 fused sample 的 secondary observation SHALL 使用相同 source frame index

### Requirement: 严格同步 authority

系统 SHALL 验证当前 Parent 所需的 sync authority，而不是仅验证 artifact 文件存在或任意 mapping 的 quality。验证 SHALL 覆盖 schema version、top-level reference camera、当前 reference/secondary mapping、mapping camera identity、finite numeric fields、positive rate、quality 枚举、有效时间范围和两路 timing authority。结构校验通过后，执行器 SHALL 再消费 quality gate；结构合法不得自动等价于 authoritative synchronized joint。

#### Scenario: 当前副摄 mapping 缺失

- **WHEN** sync artifact 缺少当前 secondary camera 的 mapping
- **THEN** 多视角运行 SHALL 进入 job-level `single_view_fallback`
- **AND** 系统 SHALL NOT 使用其他 non-reference mapping 猜测副摄身份

#### Scenario: 非法 authority 被拒绝

- **WHEN** schema、camera identity、rate、mapping 数值、有效范围或 required timing authority 不合法
- **THEN** sync authority SHALL 被判定为 unavailable
- **AND** 结果 SHALL 记录结构化失败原因

#### Scenario: Quality gate 被实际执行

- **WHEN** structural validation 通过且 sync quality 分别为 `good`、`degraded` 或 `unknown`
- **THEN** execution mode SHALL 分别为 `joint_authoritative`、`joint_degraded` 或 `single_view_fallback`
- **AND** 执行器 SHALL NOT 只根据 `validate_sync_authority().valid` 决定是否进入 synchronized joint

### Requirement: 真实 effective mode

系统 SHALL 根据 sync authority、quality gate 和实际融合证据计算 effective mode。没有任何 `dual_evidence` sample 时，effective mode SHALL 为 `single_view_fallback`；存在双摄证据但 timing quality 或覆盖不足时 SHALL 为 `multiview_degraded`；只有 timing authority 为 source PTS、sync quality 为 good 且覆盖满足策略时才可为 `multiview_fused` 或 authoritative joint 等价模式。

#### Scenario: 零副摄证据

- **WHEN** 整个运行没有 secondary available measurement
- **THEN** effective mode SHALL 为 `single_view_fallback`
- **AND** 用户可见 message SHALL NOT 声明正常双摄融合完成

#### Scenario: degraded timing 有双路证据

- **WHEN** 运行存在 secondary evidence 但 sync quality 为 `degraded` 或任一路使用 nominal FPS
- **THEN** 结果 SHALL 标记为 degraded/compatibility mode
- **AND** SHALL NOT 声明 authoritative synchronized analysis

### Requirement: 多视角可靠性诊断

系统 SHALL 在 diagnostics 中记录 `secondary_available_samples`、`dual_evidence_samples`、`single_view_fallback_samples`、`predicted_samples`、`effective_multiview_ratio`、timing authority、sync quality、execution mode、authoritative eligible tick count 和各类 frame selection status，并保留导致 job-level fallback 的 authority reason。

#### Scenario: 诊断覆盖统计

- **WHEN** 多视角运行完成或进入 fallback
- **THEN** diagnostics SHALL 包含上述计数和 effective mode
- **AND** 计数 SHALL 能与 fused samples 的状态和 timing provenance 相互校验

#### Scenario: 结果可解释

- **WHEN** 研究者检查某个 canonical tick 的 secondary evidence
- **THEN** diagnostics 或 artifact SHALL 能定位 source frame、source timestamp、mapped take timestamp、selection error、timing authority 和不可用 reason

