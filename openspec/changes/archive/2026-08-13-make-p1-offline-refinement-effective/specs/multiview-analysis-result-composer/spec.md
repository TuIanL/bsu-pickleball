## MODIFIED Requirements

### Requirement: refinement manifest 生命周期

`joint_tracking_v2` 的 fused manifest SHALL 记录 F1 offline refinement 的完整生命周期。Parent `canonicalStatus` 在 F1 recovery、re-fusion、safety gate 和 artifact publication 完成前 SHALL 保持 `running`；F0 是中间态，不得在 F1 尚未判定时被宣称为最终结果。

manifest 的 `refinement` 字段 SHALL 包含：

```text
status: skipped_no_windows | completed | rejected_by_safety_gate | failed_fallback
firstPassArtifact: fused_player_trajectory.f0.v2.json
recoveredObservations: recovered_view_observations.v1.json | null
refinedArtifact: fused_player_trajectory.f1.v2.json | null
final_source: refined_f1 | first_pass_f0
metrics: F0/F1 acceptance metrics and thresholds
```

产物 SHALL 独立写入 JointRun 目录，F1 SHALL 由 formal re-fusion 和完整 temporal filtering 生成，SHALL NOT 由 append recovered fused samples 生成。Composer 的最终产品引用 SHALL 按 `final_source` 选择 F1 或 F0；Candidate F1 即使被 safety gate 拒绝，也 SHALL 保留供 A/B 和诊断。

#### Scenario: F1 完成并采用

- **WHEN** joint run 完成 recovery、formal re-fusion 且通过 `RefinementAcceptanceGate`
- **THEN** manifest SHALL 记录 `refinement.status=completed`、`final_source=refined_f1`
- **AND** `refinedArtifact` SHALL 指向 `fused_player_trajectory.f1.v2.json`
- **AND** Parent 产品轨迹 SHALL 消费 F1

#### Scenario: 门拒绝回退

- **WHEN** F1 正常执行但被 `RefinementAcceptanceGate` 拒绝
- **THEN** manifest SHALL 记录 `refinement.status=rejected_by_safety_gate`、`final_source=first_pass_f0`
- **AND** Parent 产品 SHALL 消费 F0
- **AND** Candidate F1、recovered evidence 和 F0/F1 metrics SHALL 保留供 A/B

#### Scenario: 无窗口跳过

- **WHEN** F0 没有任何符合 donor、target availability 和 target weak/missing/lost 条件的窗口
- **THEN** manifest SHALL 记录 `refinement.status=skipped_no_windows`、`final_source=first_pass_f0`
- **AND** SHALL 明确区分“无 eligible window”与“F1 执行失败”

#### Scenario: 异常回退

- **WHEN** F1 在第二遍解码、检测、re-fusion、metrics 或 artifact publication 阶段抛出异常
- **THEN** manifest SHALL 记录 `refinement.status=failed_fallback`、`final_source=first_pass_f0`
- **AND** Parent SHALL 保持可消费的 F0 结果

#### Scenario: F0 不可变与原子发布

- **WHEN** F1 生成、被采用或被拒绝
- **THEN** `fused_player_trajectory.f0.v2.json` SHALL 保持原样且可通过 hash/内容比较验证
- **AND** 系统 SHALL 在 F0、recovered、Candidate F1 和 diagnostics 写出完成后最后更新 Parent manifest
- **AND** manifest coherent 之前 Parent SHALL NOT 标记为 completed

#### Scenario: 历史产物兼容

- **WHEN** Composer 消费没有 `refinement` 字段的历史 joint v2 产物
- **THEN** 系统 SHALL 将其视为 F0-only
- **AND** 默认 `final_source=first_pass_f0`，不得假设 F1 artifact 存在
