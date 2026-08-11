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

系统 SHALL 验证当前 Parent 所需的 sync authority，而不是仅验证 artifact 文件存在或任意 mapping 的 quality。验证 SHALL 覆盖 schema version、top-level reference camera、当前 reference/secondary mapping、mapping camera identity、finite numeric fields、positive rate、quality 枚举和有效时间范围。

#### Scenario: 当前副摄 mapping 缺失

- **WHEN** sync artifact 缺少当前 secondary camera 的 mapping
- **THEN** 多视角运行 SHALL 进入 job-level single-view fallback
- **AND** 系统 SHALL NOT 使用其他 non-reference mapping 猜测副摄身份

#### Scenario: 非法 authority 被拒绝

- **WHEN** schema、camera identity、rate 或 mapping 数值不合法
- **THEN** sync authority SHALL 被判定为 unavailable
- **AND** 结果 SHALL 记录结构化失败原因

### Requirement: 真实 effective mode

系统 SHALL 根据实际融合证据计算 effective mode。没有任何 `dual_evidence` sample 时，effective mode SHALL 为 `single_view_fallback`；存在双摄证据但覆盖不足时 SHALL 为 `multiview_degraded`；只有覆盖满足策略时才可为 `multiview_fused`。

#### Scenario: 零副摄证据

- **WHEN** 整个运行没有 secondary available measurement
- **THEN** effective mode SHALL 为 `single_view_fallback`
- **AND** 用户可见 message SHALL NOT 声明正常双摄融合完成

### Requirement: 多视角可靠性诊断

系统 SHALL 在 diagnostics 中记录 `secondary_available_samples`、`dual_evidence_samples`、`single_view_fallback_samples`、`predicted_samples` 和 `effective_multiview_ratio`，并保留导致 job-level fallback 的 authority reason。

#### Scenario: 诊断覆盖统计

- **WHEN** 多视角运行完成或进入 fallback
- **THEN** diagnostics SHALL 包含上述计数和 effective mode
- **AND** 计数 SHALL 能与 fused samples 的状态相互校验

