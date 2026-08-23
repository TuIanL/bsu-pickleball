## ADDED Requirements

### Requirement: Local slot 与 global 的全视图双射
`GlobalPlayerAssociator` SHALL 保证同一 tick 内每个 `(view_id, view_player_id, epoch)` 至多绑定一个 global，且每个 global 在同一 view 至多接受一个 local slot。duplicate、cross-side 或 ambiguity margin 不足的 challenger SHALL NOT 覆盖 incumbent。

#### Scenario: P2 尺度投影候选落在 P1 bbox
- **WHEN** P2 projected candidate 的 target bbox memory owner 为 P1 或其 local slot 已绑定另一 global
- **THEN** association SHALL 拒绝该候选或保持为 unresolved display evidence
- **AND** SHALL NOT 将 P2 global 绑定到 P1 local slot

### Requirement: 投影 provenance 不授予身份
`cross_view_projected` evidence SHALL 只用于展示/恢复候选排序，不得单独创建 local identity、global binding 或 canonical trajectory sample。其 provenance MUST 含 donor global、target slot、geometry residual、bbox memory owner 与 age。

#### Scenario: donor P2 有效但 target 无 detection
- **WHEN** donor view 确认 P2 而 target view 无真实/ROI detection
- **THEN** target view MAY 展示 P2 projected footpoint
- **AND** MUST NOT 因该投影修改 P1/P2 的 association mapping

### Requirement: 跨摄 appearance 只使用已校正软先验
Global association MAY 在 geometry/side/slot hard gate 后使用跨摄 appearance 排序，但 MUST 要求 donor/target descriptor 合格且 camera color profile confidence 达标。未经校正、non-discriminative 或低质量 appearance SHALL 权重归零；projected bbox 不得生成 descriptor。

#### Scenario: 跨摄颜色相似但 profile 不可靠
- **WHEN** cam_1/cam_2 的 candidate 颜色相似但 camera profile confidence 不达标
- **THEN** association SHALL 忽略跨摄 appearance cost
- **AND** SHALL 按 geometry、prediction、continuity 与一对一约束裁决
