# multiview-offline-refinement Specification

## Purpose
F1 离线精修:F0 第一遍在线因果感知后,回看困难窗口,用 donor 视角 + forward/backward 状态做第二遍检测,再 re-fusion,经安全门判定。只扩展 joint_tracking_v2 的 JointRun 路径;late_fusion_v1 / MultiViewFusionRun 永不接触 F1。
## Requirements
### Requirement: RecoveryTickPlan 两级资格

系统 SHALL 从 F0 immutable evidence snapshot 挖掘 RecoveryWindow，并为每个 tick 生成不可变 `RecoveryTickPlan`。窗口级资格 SHALL 使用本次 F1 config snapshot 的 `min_donor_quality`；tick 可恢复 SHALL 同时满足：target source frame 存在、target observation 属于 `weak | missing | lost`、donor 在该 canonical tick 为 original/base observed 且质量达标。`source_frame_unavailable` SHALL NOT recoverable。

每个 plan 的 `take_timestamp_ms`、target/donor source frame index、source timestamp 和 mapped timestamp SHALL 直接来自 F0 canonical trace/snapshot，SHALL NOT 使用 `tick * 1000 / nominal_fps` 重新推导或重新执行 sync mapping。

#### Scenario: source frame 不存在不可恢复

- **WHEN** 某 canonical tick 的 target 视角没有 source frame
- **THEN** 该 tick SHALL 标记为 not recoverable
- **AND** 不生成该 tick 的 `RecoveryTickPlan`

#### Scenario: donor 必须是 per-tick 真实 base 观测

- **WHEN** 窗口整体 donor 强，但某 tick donor 为 predicted、guided 或缺失
- **THEN** 该 tick SHALL NOT 允许 recovery
- **AND** 仅 donor 为 original/base observed 且质量达到 F1 config threshold 时才生成 plan

#### Scenario: plan 使用 canonical timestamp

- **WHEN** F1 为某 tick 创建 `RecoveryTickPlan`
- **THEN** `take_timestamp_ms` SHALL 等于 F0 canonical snapshot 的 timestamp
- **AND** target/donor source timing provenance SHALL 被保留

### Requirement: F1 MUST NOT 修改 F0 状态

offline refinement SHALL 永不修改 F0 的 `ViewTrackingSession`、`MultiObjectTracker`、`PlayerLockManager`、`PlayerIdentityManager`、`GlobalPlayerState` 或 global identity mapping。F1 输出 SHALL 仅为冻结的 `RecoveredViewObservation` 和 candidate F1 artifact；连续多帧证明 SHALL 使用窗口内轻量 `RecoveryTracklet`。

#### Scenario: 只读 F0

- **WHEN** F1 对某 target tick 执行检测或 re-fusion
- **THEN** 系统 SHALL NOT 调用 F0 tracker、lock、identity 或 global registry 的 update
- **AND** F1 SHALL 读取 F0 snapshot 而不是回写 F0 runtime state

#### Scenario: 拒绝零副作用

- **WHEN** 一个 recovered candidate 被 pre-gate、donor gate 或 acceptance gate 拒绝
- **THEN** 该 candidate SHALL 被丢弃或保留为诊断 evidence
- **AND** 不得创建/改写任何 F0 state、track 或 global identity

### Requirement: 离线第二遍检测

系统 SHALL 对每个 eligible `RecoveryTickPlan` 使用 `target_view` 对应的 `RefinementViewContext` 执行：精确读取 target source frame → 以 donor canonical observation 为中心，结合 target 窗口两侧最近有效 F0 anchor 生成 envelope → target local image-space ROI → `detect_regions` → guided pre-gate → donor/motion strict gate → 生成 `RecoveredViewObservation`。

每个 view SHALL 拥有独立 detector、homography、inverse homography、orientation、frame geometry、frame provider 和 timing metadata。F1 SHALL 支持 Cam1 target 由 Cam2 donor 恢复，也支持 Cam2 target 由 Cam1 donor 恢复。

#### Scenario: target view 使用自身 context

- **WHEN** `RecoveryTickPlan.target_view` 为 Cam1 或 Cam2
- **THEN** 检测、投影、ROI 边界和 local-space pre-gate SHALL 使用该 target view 的 context
- **AND** SHALL NOT 使用另一 view 的 detector 或 transform 作为 fallback

#### Scenario: donor 中心化 ROI

- **WHEN** 系统为 eligible tick 合成 recovery ROI
- **THEN** ROI SHALL 以 donor canonical position 为中心
- **AND** forward/backward anchor SHALL 只用于 consistency 与 uncertainty envelope，不得替代 donor 中心证据

#### Scenario: 最近边界 anchor

- **WHEN** 某 tick 的 F0 position history 在窗口前后存在有效 anchor
- **THEN** before anchor SHALL 选择小于目标 tick 的最大 tick
- **AND** after anchor SHALL 选择大于目标 tick 的最小 tick

#### Scenario: 边界 anchor fallback

- **WHEN** 窗口位于视频开始或结尾，只有一侧 anchor 或两侧都没有
- **THEN** 系统 SHALL 使用 donor 加可用的一侧 anchor
- **AND** 两侧都无时 SHALL 使用更严格的 donor-only gate，donor 不合格时跳过 tick

### Requirement: Re-fusion(不是直接替换 sample)

F1 SHALL 分为 Recovery 和 Refusion 两个阶段。Recovery 阶段必须先冻结全部 `RecoveredViewObservation`；Refusion 阶段 SHALL 将 F0 original view observations 与 recovered observations 按 deterministic precedence 合并，再重新执行既有 `ViewIntrinsicQuality`、`PairConsistency`、`Conflict Gate`、`PlayerPositionFusion` 和完整 canonical 序列的 temporal filtering，生成 immutable F1 trajectory。

系统 SHALL NOT 将 recovered position 直接追加为 fused sample、覆盖 F0 sample 或跳过 pair consistency/quality/conflict/temporal policy。

#### Scenario: 重新融合

- **WHEN** F1 需要纳入一个 accepted recovered observation
- **THEN** 系统 SHALL 将其作为 target view evidence 与 donor/original evidence 一起重新 fusion
- **AND** SHALL 重新执行 final temporal filtering，产出统一生成的 F1 轨迹

#### Scenario: original 强观测优先

- **WHEN** original strong evidence 与 recovered evidence 在同一 global/tick/view 冲突
- **THEN** original strong evidence SHALL 优先
- **AND** recovered SHALL 被标记为 duplicate/suppressed，不得替换 original

#### Scenario: recovered 补充弱或缺失 view

- **WHEN** target view 原本 weak 或 missing 且 recovered evidence 通过 gate
- **THEN** recovered SHALL 作为该 view 的 measurement candidate 参与正常 pair/fusion policy
- **AND** F1 的融合状态 SHALL 由正常 fusion policy 决定

### Requirement: RefinementAcceptanceGate

系统 SHALL 提供真实的 `RefinementAcceptanceGate`，在 F1 发布前对相同 global/tick 范围的 F0 与 Candidate F1 计算并保存：eligible coverage、recovered count、original strong preservation、trajectory jump violations、speed violations、fusion conflicts、recovered residual P50/P90 和 donor consistency violations。

F1 采用 SHALL 要求 recovered count > 0、coverage 不下降、original strong evidence 未被降级、jump/conflict/speed 增量在配置门内、recovered residual P90 在阈值内且 donor inconsistency 为 0。否则 SHALL 判为 `rejected_by_safety_gate` 并回退 F0。算法异常 SHALL 判为 `failed_fallback`，不得伪装成安全门拒绝。

#### Scenario: 门通过采用 F1

- **WHEN** F1 恢复至少一条 observation 且全部 safety metrics 达标
- **THEN** manifest SHALL 记录 `refinement.status=completed`、`final_source=refined_f1`
- **AND** 产品消费 F1

#### Scenario: 门拒绝回退 F0

- **WHEN** F1 正常执行但 coverage、jump、speed、conflict、residual 或 preservation 不满足门限
- **THEN** manifest SHALL 记录 `refinement.status=rejected_by_safety_gate`、`final_source=first_pass_f0`
- **AND** 用户仍得稳定 F0，Candidate F1 与 metrics 保留供 A/B

#### Scenario: 执行异常回退

- **WHEN** F1 在解码、检测、re-fusion 或 artifact 写出阶段发生异常
- **THEN** manifest SHALL 记录 `refinement.status=failed_fallback`、`final_source=first_pass_f0`
- **AND** 不得将异常计为 safety gate rejection

### Requirement: manifest 4 状态与 immutable artifacts

refinement manifest SHALL 支持 `skipped_no_windows`、`completed`、`rejected_by_safety_gate`、`failed_fallback` 四种状态。产物 SHALL 独立保存为 F0 (`fused_player_trajectory.f0.v2.json`)、recovered (`recovered_view_observations.v1.json`)、Candidate F1 (`fused_player_trajectory.f1.v2.json`,若生成) 和 diagnostics (`refinement_diagnostics.json`)。F1 SHALL NOT 覆盖 F0；Parent SHALL 在 manifest coherent 后才完成。

#### Scenario: 无窗口跳过

- **WHEN** F0 没有 donor 强且 target weak/missing/lost 的 eligible window
- **THEN** manifest SHALL 记录 `skipped_no_windows`、`final_source=first_pass_f0`

#### Scenario: F0 不可变

- **WHEN** F1 生成或被安全门拒绝
- **THEN** F0 artifact 内容和 hash SHALL 保持不变
- **AND** F0 与 Candidate F1 SHALL 始终可 A/B 对比

#### Scenario: 原子发布

- **WHEN** F1 refinement 完成
- **THEN** 系统 SHALL 先写 F0/recovered/F1/diagnostics，再最后更新 Parent manifest
- **AND** 任一中间写出失败 SHALL 进入 `failed_fallback` 且最终产品指向 F0

### Requirement: recovered 可参与 metric-eligible fused sample

accepted recovered observation 是真实图像证据，MAY contribute to a metric-eligible fused sample；最终 fused sample 的 `metric_eligible` SHALL 由既有 fusion/metric policy 统一决定。`offline_refinement` SHALL 只表达 observation provenance，SHALL NOT 强制 `metric_eligible=true`；`predicted` SHALL 永不成为 metric evidence。

#### Scenario: recovered 经统一 policy 判定

- **WHEN** recovered 与 donor/original evidence 重新 fusion
- **THEN** 最终 sample 的 `metric_eligible` SHALL 由正常 quality、pair、conflict 和 prediction policy 决定
- **AND** SHALL NOT 因 `observation_origin=offline_refinement` 而硬置 true

#### Scenario: fusion status 与 origin 分离

- **WHEN** 一个 F1 sample 包含 offline recovered view evidence
- **THEN** `fusion_status` SHALL 继续使用 `dual_observed`、`single_view_fallback`、`conflict`、`unavailable` 或 `predicted`
- **AND** `offline_refinement` SHALL 出现在 observation provenance 而不是 fusion status

