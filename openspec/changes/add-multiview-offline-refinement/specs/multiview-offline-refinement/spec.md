# multiview-offline-refinement Specification

## Purpose
F1 离线精修:F0 第一遍在线因果感知后,回看困难窗口,用 donor 视角 + forward/backward 状态做第二遍检测,再 re-fusion,经安全门判定。只扩展 joint_tracking_v2 的 JointRun 路径;late_fusion_v1 / MultiViewFusionRun 永不接触 F1。

## Requirements
### Requirement: RecoveryTickPlan 两级资格

系统 SHALL 从 F0 诊断挖掘 RecoveryWindow(窗口级:target_view 存在 weak/missing/lost 段 且 donor 视角窗口整体强度 ≥ `donor_min_quality`),并为每个 tick 判定资格生成不可变 `RecoveryTickPlan`。tick 可恢复 SHALL 满足:`target source frame 存在` + `target observation ∈ {weak, missing, lost}` + `donor 当前 tick 为 original/base observed`(非 predicted、非 weak guided)+ `donor quality ≥ donor_min_quality`。`source_frame_unavailable` SHALL NOT recoverable。

#### Scenario: source frame 不存在不可恢复

- **WHEN** 某 canonical tick 的 target 视角没有 source frame
- **THEN** 该 tick SHALL 标记为 not recoverable
- **AND** 不生成该 tick 的 RecoveryTickPlan

#### Scenario: donor 必须是 per-tick 真实 base 观测

- **WHEN** 窗口整体 donor 强,但某 tick donor 为 predicted 或缺失
- **THEN** 该 tick SHALL NOT 允许 recovery
- **AND** 仅 donor 为 original/base observed 且 quality 达标时才生成 RecoveryTickPlan

### Requirement: F1 MUST NOT 修改 F0 状态

offline refinement SHALL 永不修改 F0 的 `ViewTrackingSession` / `MultiObjectTracker` / `PlayerLockManager` / `PlayerIdentityManager` / `GlobalPlayerState` F0 history。F1 输出 SHALL 仅为 `RecoveredViewObservation`;需要连续多帧证明时 SHALL 使用窗口内轻量 `RecoveryTracklet`(含 previous_bbox / previous_canonical_position / consecutive_hits),不使用 F0 tracker。

#### Scenario: 只读 F0

- **WHEN** F1 对某 target tick 执行检测
- **THEN** 系统 SHALL NOT 调用 F0 tracker / lock / identity 的 update
- **AND** 该 tick 的恢复证据经 RecoveryTracklet 在窗口内独立累积

#### Scenario: 拒绝零副作用

- **WHEN** 一个 recovered candidate 被拒绝
- **THEN** 该 candidate SHALL 被丢弃
- **AND** 不创建/改写任何 F0 状态或 track

### Requirement: 离线第二遍检测

系统 SHALL 对每个 RecoveryTickPlan 执行:re-open target source video 精确解帧 → 用 **donor canonical observation + forward boundary prediction + backward boundary prediction** 合成搜索 envelope → image-space ROI → `detect_regions` → guided pre-gate(bbox sanity → footpoint → projection → canonical residual)→ donor + motion strict gate → accepted 生成 `RecoveredViewObservation`(`observation_origin=offline_refinement`)。

#### Scenario: donor 中心化 ROI

- **WHEN** 合成 recovery ROI
- **THEN** ROI SHALL 以 donor canonical position 为中心,forward/backward 边界预测用于 consistency 与 uncertainty envelope
- **AND** SHALL NOT 仅依赖 forward/backward(快速跑动时会滞后)

#### Scenario: 边界 anchor fallback

- **WHEN** 窗口位于视频开始(无 before-state)或结尾(无 after-state)
- **THEN** 系统 SHALL 用 donor + 可用的一侧预测;两侧都无 → donor-only(要求更严 donor quality / 更小 max uncertainty);donor 当前 tick 也无 → skip tick

### Requirement: Re-fusion(不是直接替换 sample)

F1 SHALL 分为 Recovery(冻结 RecoveredViewObservation)与 Refusion(original + recovered observations 重新执行既有 fusion math → final temporal filtering → immutable F1)两个阶段。SHALL NOT 将 recovered position 直接覆盖 F0 fused sample(否则绕过双摄质量加权 / inter-view consistency / conflict detection / metric eligibility)。

#### Scenario: 重新融合

- **WHEN** F1 需要纳入 recovered observation
- **THEN** 系统 SHALL 将该 recovered 与 original view observations 一起重新执行 `ViewIntrinsicQuality / PairConsistency / Conflict Gate / PlayerPositionFusion`
- **AND** 重新执行 final temporal filtering,产出统一生成的 F1 轨迹

#### Scenario: original 强观测优先

- **WHEN** original 观测与 recovered 观测冲突
- **THEN** original 强观测 SHALL 优先
- **AND** recovered 不覆盖原强观测

### Requirement: RefinementAcceptanceGate

系统 SHALL 提供 `RefinementAcceptanceGate`,在 F1 发布前比较 F0 vs F1 内部指标(eligible coverage / trajectory jump count / speed violations / conflict count / recovered residual P50/P90 / donor inconsistency / original-strong preservation)。F1 采用 SHALL 要求 `accepted_recovered_count > 0` 且 `eligible_coverage(F1) >= eligible_coverage(F0)` 且新增 jump/conflict ≤ allowed_delta 且无 original 强观测被降级/替换 且 residual 统计在门内;否则 SHALL 判 `rejected_by_safety_gate` 回退 F0。

#### Scenario: 门通过采用 F1

- **WHEN** F1 恢复 ≥1 条观测且全部安全指标达标
- **THEN** manifest SHALL 记录 `refinement.status=completed`、`final_source=refined_f1`
- **AND** 产品消费 F1

#### Scenario: 门拒绝回退 F0

- **WHEN** F1 正常执行但 jump/conflict 超标或覆盖 original 强观测
- **THEN** manifest SHALL 记录 `refinement.status=rejected_by_safety_gate`、`final_source=first_pass_f0`
- **AND** 用户仍得稳定 F0(区别于 failed_fallback:算法执行成功但结果不采用)

### Requirement: manifest 4 状态与 immutable artifacts

refinement manifest SHALL 支持四种状态:`skipped_no_windows / completed / rejected_by_safety_gate / failed_fallback`,对应 `final_source = first_pass_f0 | refined_f1`。产物 SHALL 独立文件:F0(`fused_player_trajectory.f0.v2.json`)、recovered(`recovered_view_observations.v1.json`)、F1(`fused_player_trajectory.f1.v2.json`,若生成)、诊断(`refinement_diagnostics.json`)。SHALL NOT 用 F1 覆盖 F0。Parent `canonicalStatus` 在 refinement 完成前保持 `running`。

#### Scenario: 无窗口跳过

- **WHEN** F0 无任何 donor 强 + target 弱窗口
- **THEN** manifest SHALL 记录 `refinement.status=skipped_no_windows`、`final_source=first_pass_f0`

#### Scenario: 异常回退

- **WHEN** F1 第二遍抛异常(解码/检测失败)
- **THEN** manifest SHALL 记录 `refinement.status=failed_fallback`、`final_source=first_pass_f0`
- **AND** 用户仍得稳定 F0

#### Scenario: F0 不可变

- **WHEN** F1 生成
- **THEN** `fused_player_trajectory.f0.v2.json` SHALL 保持原样,不被 F1 覆盖
- **AND** F0 vs F1 A/B 始终可对比

### Requirement: recovered 可参与 metric-eligible fused sample

accepted recovered observation 是真实图像证据,MAY contribute to a metric-eligible fused sample;最终 fused sample 的 `metric_eligible` 由既有 fusion / metric eligibility policy 统一决定。`predicted` SHALL 永不成为 metric evidence。

#### Scenario: recovered 经统一 policy 判定

- **WHEN** recovered 与 donor 重新 fusion 后触发 conflict
- **THEN** 最终 fused sample 的 metric_eligible SHALL 按正常 fusion policy 判定
- **AND** SHALL NOT 因 `offline_refinement` 来源而硬置 true
