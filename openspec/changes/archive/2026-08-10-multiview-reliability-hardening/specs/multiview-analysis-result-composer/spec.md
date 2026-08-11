## ADDED Requirements

### Requirement: Manifest 反映真实多视角证据

`MultiViewResultComposer` SHALL 根据 diagnostics 的有效证据计算并写入 effective mode。manifest 的 `analysis_source`、fused diagnostics 和 Parent result message SHALL 使用一致的模式语义。

#### Scenario: 零双摄证据不标正常融合

- **WHEN** fused artifact 只有 reference single-view fallback samples
- **THEN** manifest 的 mode SHALL 为 `single_view_fallback`
- **AND** manifest SHALL 保留 fallback reason 与 evidence counters

#### Scenario: 部分覆盖标 degraded

- **WHEN** 运行包含双摄证据但 secondary 覆盖低于正常融合阈值
- **THEN** manifest SHALL 为 `multiview_degraded`
- **AND** diagnostics SHALL 暴露 effective ratio
