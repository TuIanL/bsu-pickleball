# multiview-analysis-orchestration Delta

## ADDED Requirements

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
