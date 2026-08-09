# multiview-analysis-result-composer Delta

## ADDED Requirements

### Requirement: refinement manifest 生命周期

`joint_tracking_v2` 的 fused manifest SHALL 记录离线精修(refinement)生命周期。Parent `canonicalStatus` 在 refinement 完成前 SHALL 保持 `running`(F0 是中间态)。manifest 的 `refinement` 字段 SHALL 包含 `status`(`skipped_no_windows | completed | rejected_by_safety_gate | failed_fallback`)、`firstPassArtifact`、`recoveredObservations`、`refinedArtifact` 与 `final_source`(`refined_f1 | first_pass_f0`)。产物 SHALL 独立文件,F0 永不覆盖。

#### Scenario: F1 完成

- **WHEN** joint run 完成 F1 且通过 RefinementAcceptanceGate
- **THEN** manifest SHALL 记录 `refinement.status=completed`、`final_source=refined_f1`
- **AND** `refinedArtifact` 指向 `fused_player_trajectory.f1.v2.json`

#### Scenario: 门拒绝回退

- **WHEN** F1 正常执行但被 RefinementAcceptanceGate 拒绝
- **THEN** manifest SHALL 记录 `refinement.status=rejected_by_safety_gate`、`final_source=first_pass_f0`
- **AND** 产品消费 F0,`refinedArtifact` 仍保留供 A/B

#### Scenario: 无窗口跳过

- **WHEN** F0 无任何 donor 强 + target 弱窗口
- **THEN** manifest SHALL 记录 `refinement.status=skipped_no_windows`、`final_source=first_pass_f0`

#### Scenario: 异常回退

- **WHEN** F1 第二遍抛异常
- **THEN** manifest SHALL 记录 `refinement.status=failed_fallback`、`final_source=first_pass_f0`

#### Scenario: F0 不可变 + 历史产物兼容

- **WHEN** F1 生成或消费历史 v2 产物
- **THEN** `fused_player_trajectory.f0.v2.json` SHALL 保持原样
- **AND** 无 `refinement` 字段的历史产物 SHALL 视为 F0-only(`final_source=first_pass_f0`)
