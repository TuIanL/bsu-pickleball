## ADDED Requirements

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
