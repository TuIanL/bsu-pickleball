## ADDED Requirements

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
